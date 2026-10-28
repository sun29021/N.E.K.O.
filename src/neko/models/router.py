"""Task-aware, resource-aware model router with logged reasons.

Selection steps for a request:
 1. map the task kind to a role (fast/chat/reasoning/coding/vision)
 2. take the profile's preference list for that role, then any other
    installed model with the needed capability
 3. drop models that are not installed, remote when privacy forbids it, or
    that would not fit in currently free memory (with safety margins)
 4. prefer an already-loaded model when quality is comparable (avoids a
    multi-second reload and VRAM churn on a 4 GB GPU)
 5. penalise models with a poor recent success rate
 6. log the decision and every rejected candidate with its reason
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from ..core.errors import ModelUnavailableError
from ..core.types import Capability, TaskKind
from ..database.db import Database
from ..resources.monitor import ResourceSnapshot, assess
from .base import ModelInfo, ModelProvider
from .profiles import ModelProfile, office_rank

ROLE_FOR_TASK: dict[TaskKind, str] = {
    TaskKind.SMALL_TALK: "fast",
    TaskKind.QUESTION: "chat",
    TaskKind.MEMORY: "chat",
    TaskKind.COMMAND: "chat",
    TaskKind.PLANNING: "reasoning",
    TaskKind.CODING: "coding",
    TaskKind.VISION: "vision",
}
CAP_FOR_ROLE = {
    "fast": Capability.CHAT, "chat": Capability.CHAT, "reasoning": Capability.CHAT, "deep": Capability.CHAT,
    "coding": Capability.CHAT, "vision": Capability.VISION, "embedding": Capability.EMBEDDING,
}
FALLBACK_ROLE = {"deep": "reasoning", "reasoning": "chat", "coding": "chat", "fast": "chat", "chat": "fast"}


def same_model(a: str, b: str) -> bool:
    def norm(n: str) -> str:
        return n if ":" in n else n + ":latest"

    return norm(a.lower()) == norm(b.lower())


@dataclass
class Candidate:
    model: str
    score: float
    rejected: str = ""


@dataclass
class RoutingDecision:
    role: str
    model: ModelInfo | None
    provider: ModelProvider | None
    reason: str
    candidates: list[Candidate] = field(default_factory=list)
    gpu_fit: str = "unknown"
    slow_warning: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "model": self.model.name if self.model else None,
            "location": self.model.location if self.model else None,
            "reason": self.reason,
            "gpu_fit": self.gpu_fit,
            "slow_warning": self.slow_warning,
            "candidates": [c.__dict__ for c in self.candidates],
        }


class ModelRouter:
    def __init__(
        self,
        providers: list[ModelProvider],
        profile: ModelProfile,
        db: Database | None = None,
        *,
        ram_margin_mb: int = 2048,
        vram_margin_mb: int = 400,
        allow_remote: bool = False,
        inventory_ttl_s: float = 30.0,
    ) -> None:
        self.providers = providers
        self.profile = profile
        self.db = db
        self.ram_margin_mb = ram_margin_mb
        self.vram_margin_mb = vram_margin_mb
        self.allow_remote = allow_remote
        self.inventory_ttl_s = inventory_ttl_s
        self._inventory: list[tuple[ModelInfo, ModelProvider]] = []
        self._inventory_at = 0.0
        self._lock = threading.Lock()
        self.override: str | None = None   # user-pinned model from the UI
        # Cloud brains (Groq/Gemini): preferred over local models when enabled; a model that just failed
        # (free limit hit, offline) rests for a while and the local model takes over.
        self.cloud_first = False
        self.deep_cloud = "gemini"       # which cloud family to prefer for deep/long work
        self._cooldown: dict[str, float] = {}

    # ------------------------------------------------------------------ inventory
    def refresh(self, force: bool = False) -> list[tuple[ModelInfo, ModelProvider]]:
        with self._lock:
            if not force and time.time() - self._inventory_at < self.inventory_ttl_s and self._inventory:
                return self._inventory
            inv: list[tuple[ModelInfo, ModelProvider]] = []
            for p in self.providers:
                try:
                    for m in p.list_models():
                        inv.append((m, p))
                except ModelUnavailableError:
                    continue
            self._inventory, self._inventory_at = inv, time.time()
            return inv

    def installed(self) -> list[ModelInfo]:
        return [m for m, _ in self.refresh()]

    def _find(self, name: str) -> tuple[ModelInfo, ModelProvider] | None:
        for m, p in self.refresh():
            if same_model(m.name, name):
                return m, p
        return None

    def cooldown(self, model: str, seconds: float = 600) -> None:
        self._cooldown[model] = time.time() + seconds

    def resting(self, model: str) -> bool:
        return self._cooldown.get(model, 0) > time.time()

    # ------------------------------------------------------------------ stats
    def _success_rate(self, model: str) -> float | None:
        if self.db is None:
            return None
        r = self.db.one(
            """SELECT COUNT(*) AS n, SUM(CASE WHEN succeeded=1 THEN 1 ELSE 0 END) AS ok FROM
               (SELECT succeeded FROM routing_decisions WHERE chosen=? AND succeeded IS NOT NULL
                ORDER BY id DESC LIMIT 20)""",
            (model,),
        )
        if r is None or not r["n"] or r["n"] < 5:
            return None
        return (r["ok"] or 0) / r["n"]

    # ------------------------------------------------------------------ routing
    def route(self, kind: TaskKind, snapshot: ResourceSnapshot, *, num_ctx: int = 4096,
              sensitive: bool = False, task_id: str | None = None, deep: bool = False) -> RoutingDecision:
        role = "deep" if deep and self.profile.roles.get("deep") else ROLE_FOR_TASK.get(kind, "chat")
        decision = self._route_role(role, snapshot, num_ctx=num_ctx, sensitive=sensitive)
        if decision.model is None and role in FALLBACK_ROLE:
            fb = self._route_role(FALLBACK_ROLE[role], snapshot, num_ctx=num_ctx, sensitive=sensitive)
            if fb.model is not None:
                fb.reason = f"no suitable {role} model; fell back to {fb.role}: {fb.reason}"
                fb.candidates = decision.candidates + fb.candidates
                decision = fb
        self._log(kind, decision, task_id)
        return decision

    def _route_role(self, role: str, snap: ResourceSnapshot, *, num_ctx: int, sensitive: bool) -> RoutingDecision:
        cap = CAP_FOR_ROLE.get(role, Capability.CHAT)
        if self.override and role != "embedding":
            found = self._find(self.override)
            if found and cap in found[0].capabilities:
                return RoutingDecision(role, found[0], found[1], f"pinned by you in the model selector ({self.override})")

        prefs = self.profile.roles.get(role, [])
        names: list[str] = list(prefs)
        for m, _ in self.refresh():
            if cap in m.capabilities and not any(same_model(m.name, n) for n in names):
                names.append(m.name)

        # The inventory is cached, but "what is loaded right now" must be fresh (seen live: a stale
        # flag made the router pick a model it believed loaded, costing a 6 s reload). Memory held
        # by other loaded local models counts as available, because they are unloaded before use.
        live: dict[str, ModelInfo] = {}
        for p in self.providers:
            try:
                for lm in p.loaded_models():
                    live[lm.name] = lm
            except ModelUnavailableError:
                pass
        for m, _ in self.refresh():
            m.loaded = any(same_model(m.name, n) for n in live)

        cands: list[Candidate] = []
        best: tuple[float, ModelInfo, ModelProvider, str] | None = None
        for rank, name in enumerate(names):
            found = self._find(name)
            if found is None:
                cands.append(Candidate(name, 0, "not installed"))
                continue
            m, p = found
            if cap not in m.capabilities:
                cands.append(Candidate(m.name, 0, f"lacks {cap.value} capability"))
                continue
            if m.location != "local":
                if self.resting(m.name):
                    cands.append(Candidate(m.name, 0, "resting after a cloud error (free limit or offline)"))
                    continue
                if not self.allow_remote:
                    cands.append(Candidate(m.name, 0, "remote models disabled"))
                    continue
                if sensitive:
                    cands.append(Candidate(m.name, 0, "request marked sensitive; stays on this computer"))
                    continue
            score = 1.0 - rank * 0.12 if name in prefs else 0.5
            if m.location == "lan:office" and role != "embedding":
                # your own bigger GPU: private, unlimited - preferred over cloud and the laptop; among the
                # office's models, the best one for this job (qwen3:32b for chat, not its small qwen3:4b)
                orank = office_rank(role, m.name)
                score = 1.25 + (max(0.0, 0.06 - orank * 0.01) if orank is not None else -0.02)
            elif m.location.startswith("cloud:") and self.cloud_first and role != "embedding":
                deep_pick = role in ("deep", "reasoning") and m.family == self.deep_cloud
                score = 1.3 if deep_pick else (1.2 if m.family == "groq" else 1.1)
            fit = "remote"
            if m.location == "local":
                need = m.estimated_peak_ram_mb(num_ctx)
                freed_vram = sum((lm.vram_bytes or 0) for n, lm in live.items()
                                 if not same_model(n, m.name)) // 1_048_576
                eff = snap
                if freed_vram and snap.vram_used_mb is not None:
                    from dataclasses import replace
                    eff = replace(snap, vram_used_mb=max(0, snap.vram_used_mb - freed_vram))
                # a loaded model already holds its memory
                f = assess(0 if m.loaded else need, eff, ram_margin_mb=self.ram_margin_mb,
                           vram_margin_mb=self.vram_margin_mb)
                if not f.ok:
                    cands.append(Candidate(m.name, 0, f.reason))
                    continue
                fit = "full" if m.loaded else f.gpu_fit
                if fit == "partial":
                    score -= 0.05
                elif fit == "none":
                    score -= 0.25
                if m.loaded:
                    # Avoiding a reload matters most for quick chat; for planning/coding/vision the
                    # better-suited model should win even if it costs a few seconds to load.
                    score += 0.15 if role in ("fast", "chat") else 0.03
            rate = self._success_rate(m.name)
            if rate is not None and rate < 0.6:
                score -= 0.3
            cands.append(Candidate(m.name, round(score, 3)))
            if best is None or score > best[0]:
                best = (score, m, p, fit)

        if best is None:
            missing = ", ".join(prefs) or "any model with this capability"
            return RoutingDecision(role, None, None, f"no installed {role} model fits right now (wanted: {missing})", cands)
        score, m, p, fit = best
        why = [f"best {role} candidate (score {score:.2f})"]
        if m.loaded:
            why.append("already loaded")
        slow = ""
        if fit == "partial":
            slow = "Part of this model runs on the CPU, so replies will be slower."
        elif fit == "none":
            slow = "This model will run on the CPU only; expect slow replies."
        return RoutingDecision(role, m, p, "; ".join(why), cands, gpu_fit=fit, slow_warning=slow)

    def _log(self, kind: TaskKind, d: RoutingDecision, task_id: str | None) -> None:
        if self.db is None:
            return
        self.db.execute(
            "INSERT INTO routing_decisions(task_id, task_kind, chosen, candidates, reason, created_at) VALUES (?,?,?,?,?,?)",
            (task_id, kind.value, d.model.name if d.model else None,
             json.dumps([c.__dict__ for c in d.candidates]), d.reason, time.time()),
        )

    def record_outcome(self, model: str, succeeded: bool, latency_ms: float | None) -> None:
        if self.db is None:
            return
        self.db.execute(
            """UPDATE routing_decisions SET succeeded=?, latency_ms=? WHERE id =
               (SELECT id FROM routing_decisions WHERE chosen=? ORDER BY id DESC LIMIT 1)""",
            (int(succeeded), latency_ms, model),
        )


class ModelLifecycle:
    """Keeps the number of resident models within ``max_loaded``. With one
    4 GB GPU the default is 1: before a different model is used, the others
    are unloaded so Ollama does not spill both into system RAM."""

    def __init__(self, max_loaded: int = 1) -> None:
        self.max_loaded = max_loaded
        self._lock = threading.Lock()   # serialises model use: one inference at a time

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def prepare(self, model: ModelInfo, provider: ModelProvider, keep: set[str] | None = None) -> list[str]:
        """``keep``: models that stay resident regardless (the CPU-only embedder)."""
        unloaded: list[str] = []
        if model.location != "local":
            return unloaded
        keep = keep or set()
        loaded = [m for m in provider.loaded_models()
                  if not same_model(m.name, model.name) and not any(same_model(m.name, k) for k in keep)]
        excess = len(loaded) + 1 - self.max_loaded
        for m in loaded[: max(0, excess)]:
            try:
                provider.unload(m.name)
                unloaded.append(m.name)
            except ModelUnavailableError:
                pass
        return unloaded
