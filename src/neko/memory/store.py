"""Persistent, inspectable memory with provenance, versioning and expiry.

Rules enforced here (see docs/MEMORY_DESIGN.md):
* Nothing becomes an *active* long-term memory without a provenance record.
* Model-inferred or untrusted content is stored as ``pending_approval`` and is
  only used for retrieval once the user approves it.
* Edits create a new version; the old row becomes ``superseded`` (auditable).
* Deletion is a hard delete of the row, its provenance, embedding and FTS
  entry. Backups taken earlier still contain it (documented in the manual).
"""

from __future__ import annotations

import json
import re
import struct
import time
from dataclasses import dataclass
from typing import Any

from ..core.errors import DatabaseError
from ..core.types import Trust, new_id
from ..database.db import Database

KINDS = ("preference", "fact", "project", "episode", "lesson", "assumption", "temporary")
_AUTO_ACTIVE_TRUST = {Trust.USER_STATED, Trust.VERIFIED}


@dataclass
class Memory:
    id: str
    kind: str
    content: str
    trust: Trust
    confidence: float
    status: str
    version: int
    tags: list[str]
    created_at: float
    updated_at: float
    last_used_at: float | None
    use_count: int
    expires_at: float | None
    sensitive: bool
    supersedes_id: str | None = None

    @classmethod
    def from_row(cls, r: Any) -> Memory:
        return cls(
            id=r["id"], kind=r["kind"], content=r["content"], trust=Trust(r["trust"]),
            confidence=r["confidence"], status=r["status"], version=r["version"],
            tags=[t for t in r["tags"].split(",") if t], created_at=r["created_at"],
            updated_at=r["updated_at"], last_used_at=r["last_used_at"], use_count=r["use_count"],
            expires_at=r["expires_at"], sensitive=bool(r["sensitive"]), supersedes_id=r["supersedes_id"],
        )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


class MemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ create
    def add(
        self,
        content: str,
        *,
        kind: str = "fact",
        trust: Trust = Trust.USER_STATED,
        source_type: str = "user_message",
        source_ref: str = "",
        confidence: float | None = None,
        tags: list[str] | None = None,
        ttl_hours: float | None = None,
        sensitive: bool = False,
        require_approval: bool | None = None,
    ) -> Memory:
        content = content.strip()
        if not content:
            raise ValueError("memory content is empty")
        if kind not in KINDS:
            raise ValueError(f"unknown memory kind {kind!r}")
        if kind == "temporary" and ttl_hours is None:
            ttl_hours = 24
        duplicate = self.find_duplicate(content)
        if duplicate is not None:
            self._add_provenance(duplicate.id, source_type, source_ref, "duplicate reinforced")
            self.db.execute(
                "UPDATE memories SET confidence = MIN(1.0, confidence + 0.05), updated_at=? WHERE id=?",
                (time.time(), duplicate.id),
            )
            return self.get(duplicate.id)  # type: ignore[return-value]
        if require_approval is None:
            require_approval = trust not in _AUTO_ACTIVE_TRUST or sensitive
        status = "pending_approval" if require_approval else "active"
        default_conf = {Trust.USER_STATED: 0.9, Trust.VERIFIED: 0.9, Trust.OBSERVED: 0.6,
                        Trust.INFERRED: 0.4, Trust.UNTRUSTED: 0.2}[trust]
        now = time.time()
        mid = new_id("m_")
        with self.db.transaction() as c:
            c.execute(
                """INSERT INTO memories(id, kind, content, trust, confidence, status, tags,
                       created_at, updated_at, expires_at, sensitive)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, kind, content, trust.value, confidence if confidence is not None else default_conf,
                 status, ",".join(tags or []), now, now,
                 now + ttl_hours * 3600 if ttl_hours else None, int(sensitive)),
            )
            c.execute(
                "INSERT INTO memory_provenance(memory_id, source_type, source_ref, note, created_at) VALUES (?,?,?,?,?)",
                (mid, source_type, source_ref, "created", now),
            )
        self.db.audit("memory", "add", memory_id=mid, kind=kind, trust=trust.value, status=status)
        return self.get(mid)  # type: ignore[return-value]

    def _add_provenance(self, memory_id: str, source_type: str, source_ref: str, note: str) -> None:
        self.db.execute(
            "INSERT INTO memory_provenance(memory_id, source_type, source_ref, note, created_at) VALUES (?,?,?,?,?)",
            (memory_id, source_type, source_ref, note, time.time()),
        )

    # ------------------------------------------------------------------ read
    def get(self, memory_id: str) -> Memory | None:
        r = self.db.one("SELECT * FROM memories WHERE id=?", (memory_id,))
        return Memory.from_row(r) if r else None

    def list(self, *, status: str | None = "active", kind: str | None = None, limit: int = 200) -> list[Memory]:
        sql, params = "SELECT * FROM memories WHERE 1=1", []
        if status:
            sql += " AND status=?"
            params.append(status)
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        return [Memory.from_row(r) for r in self.db.query(sql, tuple(params))]

    def provenance(self, memory_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT source_type, source_ref, note, created_at FROM memory_provenance WHERE memory_id=? ORDER BY id",
            (memory_id,))]

    def find_duplicate(self, content: str) -> Memory | None:
        norm = normalize(content)
        for m in self.keyword_search(content, limit=5, include_pending=True):
            if normalize(m.content) == norm:
                return m
        return None

    def keyword_search(self, query: str, *, limit: int = 20, include_pending: bool = False) -> list[Memory]:
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in terms[:16])
        statuses = ("active", "pending_approval") if include_pending else ("active",)
        placeholders = ",".join("?" * len(statuses))
        try:
            rows = self.db.query(
                f"""SELECT m.*, bm25(memories_fts) AS rank FROM memories_fts
                    JOIN memories m ON m.rowid = memories_fts.rowid
                    WHERE memories_fts MATCH ? AND m.status IN ({placeholders})
                    ORDER BY rank LIMIT ?""",  # noqa: S608 - placeholders only
                (fts_query, *statuses, limit),
            )
        except DatabaseError:
            return []
        return [Memory.from_row(r) for r in rows]

    # ------------------------------------------------------------------ update
    def approve(self, memory_id: str) -> None:
        self.db.execute("UPDATE memories SET status='active', updated_at=? WHERE id=? AND status='pending_approval'",
                        (time.time(), memory_id))
        self._add_provenance(memory_id, "manual_edit", "", "approved by user")
        self.db.audit("memory", "approve", memory_id=memory_id)

    def reject(self, memory_id: str) -> None:
        self.delete(memory_id, reason="rejected by user")

    def edit(self, memory_id: str, new_content: str, *, source_ref: str = "") -> Memory:
        old = self.get(memory_id)
        if old is None:
            raise KeyError(memory_id)
        now = time.time()
        nid = new_id("m_")
        with self.db.transaction() as c:
            c.execute(
                """INSERT INTO memories(id, kind, content, trust, confidence, status, version, supersedes_id,
                       tags, created_at, updated_at, expires_at, sensitive)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (nid, old.kind, new_content.strip(), Trust.USER_STATED.value, max(old.confidence, 0.9),
                 "active", old.version + 1, old.id, ",".join(old.tags), old.created_at, now,
                 old.expires_at, int(old.sensitive)),
            )
            c.execute("UPDATE memories SET status='superseded', updated_at=? WHERE id=?", (now, old.id))
            c.execute(
                "INSERT INTO memory_provenance(memory_id, source_type, source_ref, note, created_at) VALUES (?,?,?,?,?)",
                (nid, "manual_edit", source_ref, f"edited from {old.id} v{old.version}", now),
            )
        self.db.audit("memory", "edit", old_id=old.id, new_id=nid)
        return self.get(nid)  # type: ignore[return-value]

    def delete(self, memory_id: str, *, reason: str = "deleted by user") -> bool:
        cur = self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        self.db.audit("memory", "delete", memory_id=memory_id, reason=reason)
        return cur.rowcount > 0

    def record_contradiction(self, a: str, b: str, note: str) -> None:
        self.db.execute(
            "INSERT INTO memory_contradictions(memory_a, memory_b, note, created_at) VALUES (?,?,?,?)",
            (a, b, note, time.time()),
        )

    def mark_used(self, memory_ids: list[str], *, task_id: str | None, scores: dict[str, tuple[float, str]]) -> None:
        now = time.time()
        with self.db.transaction() as c:
            for mid in memory_ids:
                c.execute("UPDATE memories SET use_count=use_count+1, last_used_at=? WHERE id=?", (now, mid))
                score, reason = scores.get(mid, (0.0, ""))
                c.execute(
                    "INSERT INTO memory_retrievals(memory_id, task_id, score, reason, created_at) VALUES (?,?,?,?,?)",
                    (mid, task_id, score, reason, now),
                )

    # ------------------------------------------------------------------ embeddings
    def set_embedding(self, memory_id: str, model: str, vector: list[float]) -> None:
        self.db.execute(
            """INSERT INTO memory_embeddings(memory_id, model, dims, vector, created_at) VALUES (?,?,?,?,?)
               ON CONFLICT(memory_id) DO UPDATE SET model=excluded.model, dims=excluded.dims,
               vector=excluded.vector, created_at=excluded.created_at""",
            (memory_id, model, len(vector), pack_vector(vector), time.time()),
        )

    def embeddings(self, model: str) -> list[tuple[str, list[float]]]:
        rows = self.db.query(
            """SELECT e.memory_id, e.vector FROM memory_embeddings e JOIN memories m ON m.id=e.memory_id
               WHERE e.model=? AND m.status='active'""",
            (model,),
        )
        return [(r["memory_id"], unpack_vector(r["vector"])) for r in rows]

    def missing_embeddings(self, model: str, limit: int = 100) -> list[Memory]:
        rows = self.db.query(
            """SELECT m.* FROM memories m LEFT JOIN memory_embeddings e
               ON e.memory_id=m.id AND e.model=? WHERE m.status='active' AND e.memory_id IS NULL LIMIT ?""",
            (model, limit),
        )
        return [Memory.from_row(r) for r in rows]

    # ------------------------------------------------------------------ maintenance
    def expire(self) -> int:
        cur = self.db.execute(
            "UPDATE memories SET status='expired' WHERE expires_at IS NOT NULL AND expires_at < ? AND status IN ('active','pending_approval')",
            (time.time(),),
        )
        return cur.rowcount

    def purge_expired(self, older_than_days: float = 7) -> int:
        cutoff = time.time() - older_than_days * 86400
        cur = self.db.execute("DELETE FROM memories WHERE status IN ('expired','superseded') AND updated_at < ?", (cutoff,))
        return cur.rowcount

    def export(self, include_sensitive: bool = False) -> dict[str, Any]:
        mems = self.db.query("SELECT * FROM memories WHERE status IN ('active','pending_approval')")
        out = []
        for r in mems:
            if r["sensitive"] and not include_sensitive:
                continue
            m = dict(r)
            m["provenance"] = self.provenance(r["id"])
            out.append(m)
        return {"format": "neko-memory-export", "version": 1, "exported_at": time.time(), "memories": out}

    def import_export(self, data: dict[str, Any]) -> int:
        if data.get("format") != "neko-memory-export":
            raise ValueError("not a N.E.K.O. memory export")
        n = 0
        for m in data.get("memories", []):
            # Imported memories keep their trust label but re-enter as pending unless user-stated/verified.
            self.add(m["content"], kind=m["kind"], trust=Trust(m["trust"]), source_type="import",
                     source_ref=json.dumps({"original_id": m["id"]}), confidence=m["confidence"],
                     tags=[t for t in m.get("tags", "").split(",") if t], sensitive=bool(m.get("sensitive")))
            n += 1
        return n
