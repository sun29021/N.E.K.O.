"""Hybrid memory retrieval with explainable scores.

Pipeline (docs/MEMORY_DESIGN.md section 4):
 1. normalise the query
 2. lexical candidates via SQLite FTS5 (BM25)
 3. semantic candidates via cosine similarity, when an embedder is available
 4. score = relevance * trust weight * confidence + recency bonus + preference bonus
 5. deduplicate near-identical content
 6. flag contradictions (same topic, conflicting values) instead of silently merging
 7. enforce a token budget
 8. record why every memory was retrieved
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.types import TRUST_WEIGHT
from .context import estimate_tokens
from .store import Memory, MemoryStore, normalize

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass
class RetrievedMemory:
    memory: Memory
    score: float
    reasons: list[str]

    @property
    def explanation(self) -> str:
        return f"score {self.score:.2f}: " + ", ".join(self.reasons)


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if len(t) > 2}


def jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class MemoryRetriever:
    def __init__(
        self,
        store: MemoryStore,
        *,
        embedder: Embedder | None = None,
        embed_model: str = "",
        semantic_threshold: float = 0.45,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.embed_model = embed_model
        self.semantic_threshold = semantic_threshold

    def retrieve(
        self,
        query: str,
        *,
        token_budget: int = 600,
        limit: int = 8,
        task_id: str | None = None,
        record: bool = True,
    ) -> list[RetrievedMemory]:
        query = query.strip()
        if not query:
            return []
        candidates: dict[str, RetrievedMemory] = {}

        # (2) lexical
        lexical = self.store.keyword_search(query, limit=limit * 3)
        for rank, m in enumerate(lexical):
            rel = 1.0 / (1 + rank * 0.35)
            candidates[m.id] = RetrievedMemory(m, rel, [f"keyword match (rank {rank + 1})"])

        # (3) semantic (optional; failures degrade to lexical only)
        stored = self.store.embeddings(self.embed_model) if (self.embedder is not None and self.embed_model) else []
        if stored:  # skip the embedding call entirely when there is nothing to compare against
            try:
                qvec = self.embedder([query])[0]  # type: ignore[misc]
                for mid, vec in stored:
                    sim = cosine(qvec, vec)
                    if sim < self.semantic_threshold:
                        continue
                    if mid in candidates:
                        candidates[mid].score = max(candidates[mid].score, sim) + 0.15
                        candidates[mid].reasons.append(f"semantic similarity {sim:.2f}")
                    else:
                        m = self.store.get(mid)
                        if m is not None:
                            candidates[mid] = RetrievedMemory(m, sim, [f"semantic similarity {sim:.2f}"])
            except Exception as exc:  # noqa: BLE001 - embedding is optional
                for c in candidates.values():
                    c.reasons.append(f"semantic search unavailable ({type(exc).__name__})")
                    break

        # always consider explicit preferences: they shape *how* to answer
        for m in self.store.list(kind="preference", limit=10):
            if m.id not in candidates:
                candidates[m.id] = RetrievedMemory(m, 0.35, ["standing user preference"])

        # (4) scoring
        now = time.time()
        for c in candidates.values():
            m = c.memory
            trust_w = TRUST_WEIGHT[m.trust]
            c.score *= trust_w * (0.5 + 0.5 * m.confidence)
            c.reasons.append(f"trust {m.trust.value} x{trust_w:.2f}")
            age_days = (now - m.updated_at) / 86400
            recency = 0.1 * math.exp(-age_days / 30)
            c.score += recency
            if m.kind == "preference":
                c.score += 0.1

        ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)

        # (5) dedupe + (6) contradiction flagging
        kept: list[RetrievedMemory] = []
        for c in ranked:
            dup = next((k for k in kept if normalize(k.memory.content) == normalize(c.memory.content)
                        or jaccard(k.memory.content, c.memory.content) > 0.85), None)
            if dup is not None:
                continue
            for k in kept:
                if _looks_contradictory(k.memory.content, c.memory.content):
                    c.reasons.append(f"may contradict {k.memory.id}")
                    k.reasons.append(f"may contradict {c.memory.id}")
            kept.append(c)

        # (7) budget
        out: list[RetrievedMemory] = []
        used = 0
        for c in kept:
            cost = estimate_tokens(c.memory.content) + 8
            if used + cost > token_budget or len(out) >= limit:
                break
            out.append(c)
            used += cost

        # (8) log usage
        if record and out:
            self.store.mark_used(
                [c.memory.id for c in out], task_id=task_id,
                scores={c.memory.id: (c.score, "; ".join(c.reasons)) for c in out},
            )
        return out


_NEGATIONS = {"not", "never", "no", "don't", "doesn't", "isn't", "dislike", "hate"}


def _looks_contradictory(a: str, b: str) -> bool:
    """Cheap heuristic: high topical overlap but opposite polarity."""
    if jaccard(a, b) < 0.4:
        return False
    na = bool(_NEGATIONS & set(a.lower().split()))
    nb = bool(_NEGATIONS & set(b.lower().split()))
    return na != nb
