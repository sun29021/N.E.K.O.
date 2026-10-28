"""Free cloud "brains" next to the local model: Groq (fast, smart everyday brain) and Google Gemini
(huge ~1M-token context for long documents and deep thinking). OpenAI-compatible APIs, stdlib only.

* Off unless ``privacy.allow_cloud_models`` is on AND a key exists. Keys come from the environment
  (``GROQ_API_KEY``, ``GEMINI_API_KEY``) or from ``secrets.toml`` in the data folder, which you fill in
  yourself in Command Center > Settings. Keys are never logged or put in the repository.
* Free tiers have per-minute/day limits: on a limit (HTTP 429), an outage or no internet the router
  puts that cloud model on a short cooldown and the local model answers instead.
* Requests marked sensitive stay on this computer (router rule). Free tiers may use what you send to
  improve the provider's products.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import ssl
import threading
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import CancelledError, ModelTimeoutError, ModelUnavailableError
from ..core.types import Capability, GenerationRequest, GenerationResult
from .base import ModelInfo, ProviderHealth


@dataclass(frozen=True)
class CloudSpec:
    name: str
    host: str
    path: str
    key_env: str
    key_name: str                 # name inside secrets.toml [cloud]
    prefer: tuple[str, ...]       # model id patterns, best first
    context: int                  # tokens we let ourselves use (free-tier per-minute limits, not the max)
    signup: str


CLOUDS: dict[str, CloudSpec] = {
    # Measured 2026-10-28 with the owner's keys: llama-3.3-70b is retired on Groq; gpt-oss-120b answers in
    # 0.2 s. On Gemini the newest 3.8-flash timed out while 3.6/3.5-flash answered in ~2 s - so candidates
    # are probed (see choose_model), not just picked by version number.
    "groq": CloudSpec("groq", "api.groq.com", "/openai/v1", "GROQ_API_KEY", "groq_key",
                      (r"^openai/gpt-oss-120b$", r"^llama-3\.3-70b", r"^qwen/qwen3[\d.]*-\d+b$", r"^moonshotai/kimi",
                       r"^openai/gpt-oss-20b$"), 8000, "https://console.groq.com/keys"),
    "gemini": CloudSpec("gemini", "generativelanguage.googleapis.com", "/v1beta/openai", "GEMINI_API_KEY",
                        "gemini_key", (r"^(models/)?gemini-[\d.]+-flash$", r"^(models/)?gemini-flash-latest$",
                                       r"^(models/)?gemini-[\d.]+-flash-lite$"),
                        200_000, "https://aistudio.google.com/apikey"),
}


def secrets_path(data_dir: Path) -> Path:
    return Path(data_dir) / "secrets.toml"


def read_key(spec: CloudSpec, data_dir: Path) -> str:
    env = os.environ.get(spec.key_env, "").strip()
    if env:
        return env
    try:
        data = tomllib.loads(secrets_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str((data.get("cloud") or {}).get(spec.key_name, "")).strip()


def save_keys(data_dir: Path, keys: dict[str, str]) -> Path:
    """Write keys the user typed into Settings (only non-empty ones replace existing values)."""
    p = secrets_path(data_dir)
    try:
        current = (tomllib.loads(p.read_text(encoding="utf-8")).get("cloud") or {}) if p.exists() else {}
    except (OSError, tomllib.TOMLDecodeError):
        current = {}
    for k, v in keys.items():
        if v.strip():
            current[k] = v.strip()
    lines = ["# N.E.K.O. cloud keys - private. Never share this file.", "[cloud]"]
    lines += [f'{k} = "{v}"' for k, v in current.items() if re.fullmatch(r"[\w\-.:]+", v)]  # (":" - Telegram bot keys)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class CloudProvider:
    supports_native_tools = True    # OpenAI-style function calling

    def __init__(self, spec: CloudSpec, data_dir: Path, *, timeout_s: float = 60.0) -> None:
        self.spec = spec
        self.id = f"cloud:{spec.name}"
        self.location = f"cloud:{spec.name}"
        self.data_dir = Path(data_dir)
        self.timeout_s = timeout_s
        self._ctx = ssl.create_default_context()
        self._models: list[str] | None = None
        self._models_at = 0.0
        self._last: GenerationResult | None = None
        self._lock = threading.Lock()
        self._chosen: str | None = None   # set by warm_up() / choose_model()
        self._warming = False

    # ------------------------------------------------------------------ plumbing
    def key(self) -> str:
        return read_key(self.spec, self.data_dir)

    def _request(self, method: str, path: str, body: dict[str, Any] | None, timeout: float) -> Any:
        key = self.key()
        if not key:
            raise ModelUnavailableError(f"no {self.spec.name} key", user_message=(
                f"The {self.spec.name} cloud brain has no API key yet (Command Center > Settings)."))
        conn = http.client.HTTPSConnection(self.spec.host, 443, timeout=timeout, context=self._ctx)
        conn.request(method, self.spec.path + path, body=json.dumps(body).encode() if body is not None else None,
                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        return conn

    def health(self, timeout_s: float = 3.0) -> ProviderHealth:
        try:
            return ProviderHealth(bool(self._model_ids(timeout_s)), "reachable")
        except ModelUnavailableError as exc:
            return ProviderHealth(False, str(exc))

    def _model_ids(self, timeout: float = 8.0) -> list[str]:
        with self._lock:
            if self._models is not None and time.time() - self._models_at < (3600 if self._models else 300):
                return self._models  # failures are remembered for 5 min, so offline routing stays fast
        try:
            conn = self._request("GET", "/models", None, timeout)
            r = conn.getresponse()
            data = r.read()
            conn.close()
        except OSError as exc:
            self._models, self._models_at = [], time.time()
            raise ModelUnavailableError(f"{self.id} unreachable: {exc}") from exc
        if r.status >= 400:
            self._models, self._models_at = [], time.time()
            raise ModelUnavailableError(f"{self.id} models HTTP {r.status}")
        ids = [str(m.get("id", "")) for m in json.loads(data).get("data", [])]
        with self._lock:
            self._models, self._models_at = ids, time.time()
        return ids

    def candidates(self) -> list[str]:
        ids, out = self._model_ids(), []
        for pat in self.spec.prefer:
            out += [i for i in sorted((i for i in ids if re.search(pat, i)), reverse=True) if i not in out]
        return out

    def _probe(self, model: str, timeout: float = 15.0) -> bool:
        body = {"model": model, "max_tokens": 50, "temperature": 0, "reasoning_effort": "low",
                "messages": [{"role": "user", "content": "Reply with just: OK"}]}
        try:
            conn = self._request("POST", "/chat/completions", body, timeout)
            r = conn.getresponse()
            data = r.read()
            conn.close()
        except (OSError, ModelUnavailableError):
            return False
        if r.status != 200:
            return False
        try:
            return bool(json.loads(data)["choices"][0]["message"].get("content"))
        except (ValueError, KeyError, IndexError, TypeError):
            return False

    def choose_model(self) -> str | None:
        """First candidate that really answers (probed once a day, cached in the data folder)."""
        cache = self.data_dir / "cloud_models.json"
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        hit = saved.get(self.spec.name) or {}
        if hit.get("model") and time.time() - float(hit.get("at", 0)) < 86400:
            return str(hit["model"])
        for m in self.candidates()[:5]:
            if self._probe(m):
                saved[self.spec.name] = {"model": m, "at": time.time()}
                try:
                    cache.write_text(json.dumps(saved), encoding="utf-8")
                except OSError:
                    pass
                return m
        return None

    def warm_up(self) -> None:
        """Pick the model in the background at start-up, so the first reply isn't delayed by probing."""
        if self._warming:
            return
        self._warming = True

        def run() -> None:
            try:
                if self.key():
                    self._chosen = self.choose_model()
            except ModelUnavailableError:
                self._chosen = None
            finally:
                self._warming = False
        threading.Thread(target=run, daemon=True, name=f"neko-cloud-{self.spec.name}").start()

    def best_model(self) -> str | None:
        return self._chosen
    # ------------------------------------------------------------------ provider API
    def list_models(self) -> list[ModelInfo]:
        if not self.key():
            return []
        best = self.best_model()
        if not best:
            self.warm_up()  # e.g. a key was just added in Settings: choose a model in the background
            return []
        caps = {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.TOOLS}
        return [ModelInfo(name=best, provider=self.id, location=self.location, capabilities=caps,
                          context_length=self.spec.context, family=self.spec.name)]

    def loaded_models(self) -> list[ModelInfo]:
        return []

    @property
    def last_result(self) -> GenerationResult | None:
        return self._last

    def chat_stream(self, req: GenerationRequest, token: CancelToken) -> Iterator[str]:
        body: dict[str, Any] = {
            "model": req.model, "stream": True, "temperature": req.temperature, "max_tokens": req.max_tokens,
            "reasoning_effort": "medium" if req.think else "low",  # short private thinking = fast replies
            "messages": to_openai_messages(req.messages)}
        if req.tools:  # real function calling (seen live: a text tool protocol made gpt-oss fake or go silent)
            body["tools"], body["tool_choice"] = req.tools, "auto"
        start, first, parts = time.perf_counter(), None, []
        calls: dict[int, dict[str, str]] = {}
        conn = None
        try:
            conn = self._request("POST", "/chat/completions", body, min(req.timeout_s, self.timeout_s))
            token.on_cancel(conn.close)
            r = conn.getresponse()
            if r.status >= 400:
                detail = r.read()[:300].decode("utf-8", "replace")
                raise ModelUnavailableError(f"{self.id} HTTP {r.status}: {detail}", user_message=(
                    f"The {self.spec.name} cloud brain refused ({'free limit reached' if r.status == 429 else r.status})."))
            while True:
                if token.cancelled:
                    raise CancelledError(token.reason)
                line = r.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                try:
                    choices = json.loads(payload).get("choices") or [{}]
                except ValueError:
                    continue
                d = choices[0].get("delta") or {}
                for tc in d.get("tool_calls") or []:  # streamed in pieces: name first, arguments in chunks
                    slot = calls.setdefault(int(tc.get("index", 0)), {"name": "", "arguments": ""})
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["arguments"] += fn.get("arguments") or ""
                delta = d.get("content") or ""
                # gpt-oss likes narrow no-break spaces / non-breaking hyphens - the voice stumbles on them
                delta = delta.replace("\u202f", " ").replace("\u00a0", " ").replace("\u2011", "-")
                if delta:
                    first = first or (time.perf_counter() - start) * 1000
                    parts.append(delta)
                    yield delta
        except socket.timeout as exc:
            raise ModelTimeoutError(str(exc)) from exc
        except OSError as exc:
            if token.cancelled:
                raise CancelledError(token.reason) from exc
            raise ModelUnavailableError(f"{self.id} connection lost: {exc}") from exc
        finally:
            if conn is not None:
                conn.close()
            total = (time.perf_counter() - start) * 1000
            parsed = []
            for _i, c in sorted(calls.items()):
                try:
                    args = json.loads(c["arguments"] or "{}")
                except ValueError:
                    args = {}
                if c["name"]:
                    parsed.append({"name": c["name"], "arguments": args if isinstance(args, dict) else {}})
            self._last = GenerationResult("".join(parts), req.model, self.id, self.location, first_token_ms=first,
                                          total_ms=total, cancelled=token.cancelled, tool_calls=parsed,
                                          completion_tokens=sum(len(p) for p in parts) // 4)

    def chat(self, req: GenerationRequest, token: CancelToken) -> GenerationResult:
        for _ in self.chat_stream(req, token):
            pass
        assert self._last is not None
        return self._last

    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]:
        raise ModelUnavailableError("cloud embeddings are not used (memory search stays local)")

    def unload(self, model: str) -> None:
        return None


def to_openai_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Neko's messages -> OpenAI chat format, pairing each tool result with the call that asked for it."""
    out: list[dict[str, Any]] = []
    open_calls: list[tuple[str, str]] = []  # (call id, tool name) waiting for a result
    for i, m in enumerate(messages):
        role = m.role.value
        if role == "assistant" and m.tool_calls:
            ids = [(f"call_{i}_{k}", c["name"]) for k, c in enumerate(m.tool_calls)]
            open_calls = list(ids)
            out.append({"role": "assistant", "content": m.content or None, "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": c["name"],
                                                             "arguments": json.dumps(c.get("arguments") or {})}}
                for (cid, _n), c in zip(ids, m.tool_calls, strict=False)]})
        elif role == "tool" and open_calls:
            k = next((j for j, (_cid, n) in enumerate(open_calls) if n == m.name), 0)
            cid, _n = open_calls.pop(k)
            out.append({"role": "tool", "tool_call_id": cid, "content": m.content})
        else:
            out.append({"role": role if role in ("system", "assistant") else "user", "content": m.content})
    return out


def cloud_providers(data_dir: Path, *, warm: bool = True) -> list[CloudProvider]:
    providers = [CloudProvider(spec, data_dir) for spec in CLOUDS.values()]
    if warm:
        for p in providers:
            p.warm_up()
    return providers


__all__ = ["CLOUDS", "CloudProvider", "CloudSpec", "cloud_providers", "read_key", "save_keys", "secrets_path"]
