"""Conversation and message persistence, retention and rolling summaries."""

from __future__ import annotations

import re
import time

from ..core.types import ChatMessage, Role, new_id
from ..database.db import Database
from .context import estimate_tokens


_STOP = {"the", "and", "you", "what", "that", "this", "with", "for", "are", "was", "did", "can", "have",
         "about", "when", "where", "how", "why", "tell", "me", "my", "your", "neko", "please", "from",
         "there", "they", "them", "then", "just", "like", "know", "remember", "said", "told", "earlier"}


class ConversationStore:
    def __init__(self, db: Database, *, store_messages: bool = True) -> None:
        self.db = db
        self.store_messages = store_messages
        self._ephemeral: dict[str, list[ChatMessage]] = {}

    def create(self, title: str = "") -> str:
        cid = new_id("c_")
        now = time.time()
        self.db.execute("INSERT INTO conversations(id, title, started_at, updated_at) VALUES (?,?,?,?)",
                        (cid, title, now, now))
        return cid

    def latest_or_create(self) -> str:
        r = self.db.one("SELECT id FROM conversations WHERE archived=0 ORDER BY updated_at DESC LIMIT 1")
        return r["id"] if r else self.create()

    def add(self, conversation_id: str, msg: ChatMessage, *, model: str | None = None,
            location: str | None = None) -> str | None:
        if not self.store_messages:
            self._ephemeral.setdefault(conversation_id, []).append(msg)
            return None
        mid = new_id("msg_")
        now = time.time()
        with self.db.transaction() as c:
            c.execute(
                """INSERT INTO messages(id, conversation_id, role, content, created_at, model, location, token_estimate)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (mid, conversation_id, msg.role.value, msg.content, now, model, location, estimate_tokens(msg.content)),
            )
            c.execute("UPDATE conversations SET updated_at=?, title=CASE WHEN title='' THEN ? ELSE title END WHERE id=?",
                      (now, msg.content[:60] if msg.role == Role.USER else "", conversation_id))
        return mid

    def history(self, conversation_id: str, limit: int = 40) -> list[ChatMessage]:
        if not self.store_messages:
            return self._ephemeral.get(conversation_id, [])[-limit:]
        rows = self.db.query(
            """SELECT role, content FROM (SELECT role, content, created_at FROM messages WHERE conversation_id=?
               AND role IN ('user','assistant') ORDER BY created_at DESC LIMIT ?) ORDER BY created_at""",
            (conversation_id, limit),
        )
        return [ChatMessage(Role(r["role"]), r["content"]) for r in rows]

    def recent_requests(self, conversation_id: str, limit: int = 12) -> list[tuple[float, str]]:
        """(timestamp, text) of the user's latest messages, oldest first - for "what did I ask earlier?"."""
        if not self.store_messages:
            return []
        rows = self.db.query(
            "SELECT created_at, content FROM messages WHERE conversation_id=? AND role='user' "
            "ORDER BY created_at DESC LIMIT ?", (conversation_id, limit))
        return [(r["created_at"], r["content"]) for r in reversed(rows)]

    def count(self, conversation_id: str) -> int:
        r = self.db.one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id=?", (conversation_id,))
        return int(r["n"]) if r else 0

    def summary(self, conversation_id: str) -> str:
        r = self.db.one("SELECT summary FROM conversations WHERE id=?", (conversation_id,))
        return r["summary"] if r else ""

    def set_summary(self, conversation_id: str, text: str, upto: float | None = None) -> None:
        if upto is None:
            self.db.execute("UPDATE conversations SET summary=? WHERE id=?", (text.strip()[:6000], conversation_id))
        else:
            self.db.execute("UPDATE conversations SET summary=?, summary_upto=? WHERE id=?",
                            (text.strip()[:6000], upto, conversation_id))

    # ------------------------------------------------------------------ compaction + recall
    def summary_upto(self, conversation_id: str) -> float:
        r = self.db.one("SELECT summary_upto FROM conversations WHERE id=?", (conversation_id,))
        return float(r["summary_upto"]) if r else 0.0

    def unsummarised(self, conversation_id: str) -> list[tuple[float, str, str]]:
        """(time, role, text) of user/assistant messages not yet folded into the summary, oldest first."""
        if not self.store_messages:
            return []
        rows = self.db.query(
            "SELECT created_at, role, content FROM messages WHERE conversation_id=? AND role IN ('user','assistant') "
            "AND created_at > ? ORDER BY created_at", (conversation_id, self.summary_upto(conversation_id)))
        return [(r["created_at"], r["role"], r["content"]) for r in rows]

    def history_since_summary(self, conversation_id: str, limit: int = 60, keep_min: int = 6) -> list[ChatMessage]:
        """Recent messages not covered by the summary (at least ``keep_min``, so there is always context)."""
        if not self.store_messages:
            return self.history(conversation_id, limit)
        upto = self.summary_upto(conversation_id)
        rows = self.db.query(
            """SELECT role, content, created_at FROM (SELECT role, content, created_at FROM messages
               WHERE conversation_id=? AND role IN ('user','assistant') ORDER BY created_at DESC LIMIT ?)
               ORDER BY created_at""", (conversation_id, limit))
        newer = [r for r in rows if r["created_at"] > upto]
        chosen = newer if len(newer) >= keep_min else rows[-keep_min:]
        return [ChatMessage(Role(r["role"]), r["content"]) for r in chosen]

    def search(self, query: str, *, exclude_after: float | None = None, limit: int = 4) -> list[dict[str, object]]:
        """Full-text search over ALL stored conversations (newest relevant first)."""
        if not self.store_messages:
            return []
        words = [w for w in re.findall(r"[^\W_]{3,}", query.lower()) if w not in _STOP][:8]
        if not words:
            return []
        match = " OR ".join(f'"{w}"' for w in words)
        sql = ("SELECT m.created_at, m.role, m.content FROM messages_fts f JOIN messages m ON m.rowid = f.rowid "
               "WHERE messages_fts MATCH ? AND m.role IN ('user','assistant')")
        args: list[object] = [match]
        if exclude_after is not None:
            sql += " AND m.created_at < ?"
            args.append(exclude_after)
        sql += " ORDER BY bm25(messages_fts), m.created_at DESC LIMIT ?"
        args.append(limit)
        try:
            return [dict(r) for r in self.db.query(sql, tuple(args))]
        except Exception:  # noqa: BLE001 - FTS syntax edge cases must never break a reply
            return []

    def list(self, limit: int = 50) -> list[dict[str, object]]:
        return [dict(r) for r in self.db.query(
            "SELECT id, title, started_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))]

    def clear_all(self) -> int:
        n = self.db.execute("DELETE FROM conversations").rowcount
        self.db.audit("memory", "clear_conversations", count=n)
        return n

    def apply_retention(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        return self.db.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,)).rowcount
