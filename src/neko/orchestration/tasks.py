"""Task state machine and verified-outcome recording (docs/MEMORY_DESIGN.md
section 6 "Verified learning loop")."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.types import Trust, new_id
from ..database.db import Database
from ..memory.store import MemoryStore

TRANSITIONS: dict[str, set[str]] = {
    "pending": {"planning", "running", "cancelled", "failed"},
    "planning": {"running", "cancelled", "failed"},
    "running": {"awaiting_approval", "verifying", "succeeded", "failed", "cancelled"},
    "awaiting_approval": {"running", "cancelled", "failed"},
    "verifying": {"succeeded", "failed", "cancelled"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}
TERMINAL = {"succeeded", "failed", "cancelled"}


class InvalidTransition(Exception):
    pass


@dataclass
class Task:
    id: str
    goal: str
    kind: str
    conversation_id: str | None
    status: str = "pending"
    steps: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class TaskManager:
    def __init__(self, db: Database, memory: MemoryStore | None = None) -> None:
        self.db = db
        self.memory = memory

    def create(self, goal: str, kind: str, conversation_id: str | None) -> Task:
        t = Task(new_id("t_"), goal[:2000], kind, conversation_id)
        now = time.time()
        self.db.execute(
            "INSERT INTO tasks(id, conversation_id, goal, kind, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (t.id, conversation_id, t.goal, kind, "pending", now, now),
        )
        return t

    def transition(self, task: Task, new_status: str, *, error: str | None = None) -> None:
        if new_status not in TRANSITIONS.get(task.status, set()):
            raise InvalidTransition(f"{task.status} -> {new_status}")
        task.status = new_status
        if error:
            task.error = error
        now = time.time()
        self.db.execute(
            "UPDATE tasks SET status=?, updated_at=?, finished_at=?, error=COALESCE(?, error) WHERE id=?",
            (new_status, now, now if new_status in TERMINAL else None, error, task.id),
        )

    def add_step(self, task: Task, description: str, status: str = "done") -> None:
        task.steps.append(description)
        self.db.execute(
            "INSERT INTO task_steps(task_id, seq, description, status, created_at) VALUES (?,?,?,?,?)",
            (task.id, len(task.steps), description[:500], status, time.time()),
        )

    def save_plan(self, task: Task, plan: list[str]) -> None:
        self.db.execute("UPDATE tasks SET plan_json=? WHERE id=?", (json.dumps(plan), task.id))

    def record_outcome(
        self,
        task: Task,
        *,
        succeeded: bool,
        failure_class: str | None = None,
        failure_reason: str | None = None,
        lesson: str | None = None,
        lesson_confidence: float | None = None,
    ) -> str | None:
        """Store the outcome. A *lesson* is only proposed (pending user approval)
        when the task used tools and at least one verification passed - an LLM
        saying "done" is never treated as evidence."""
        evidence = self.db.query(
            "SELECT passed FROM verification_evidence WHERE task_id=?", (task.id,)
        )
        verified = any(r["passed"] for r in evidence)
        lesson_status = "none"
        memory_id = None
        if lesson and self.memory is not None and (verified or not succeeded):
            m = self.memory.add(
                lesson, kind="lesson", trust=Trust.VERIFIED if verified and succeeded else Trust.OBSERVED,
                source_type="task_outcome", source_ref=task.id, confidence=lesson_confidence,
                require_approval=True,
            )
            memory_id, lesson_status = m.id, "proposed"
        self.db.execute(
            """INSERT OR REPLACE INTO outcomes(task_id, succeeded, failure_class, failure_reason, lesson,
                   lesson_confidence, lesson_status, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (task.id, int(succeeded), failure_class, failure_reason, lesson, lesson_confidence, lesson_status, time.time()),
        )
        return memory_id

    def add_feedback(self, task_id: str, feedback: str, *, succeeded: bool | None = None) -> None:
        self.db.execute("UPDATE outcomes SET user_feedback=? WHERE task_id=?", (feedback[:2000], task_id))
        if succeeded is not None:
            self.db.execute(
                """INSERT INTO verification_evidence(task_id, method, passed, detail, created_at)
                   VALUES (?, 'user_confirmed', ?, ?, ?)""",
                (task_id, int(succeeded), feedback[:500], time.time()),
            )
            self.db.execute("UPDATE outcomes SET succeeded=? WHERE task_id=?", (int(succeeded), task_id))

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT id, goal, kind, status, created_at, updated_at, error FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,))]
