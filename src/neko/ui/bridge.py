"""Thread bridge between the engine (plain Python threads) and Qt.

Engine events arrive on worker threads; emitting a Qt signal from there is
safe - Qt queues it to the GUI thread because the receiving QObject lives
there. Up to two requests run at once (a long background job such as Claude Code or study notes,
plus normal chat); more wait in a queue. Local model calls still take turns via ModelLifecycle's lock.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..app.bootstrap import Neko
from ..core import events as ev
from ..core.cancel import CancelToken
from ..core.types import AssistantState
from ..orchestration.smart import is_long_job
from ..security.policy import ApprovalRequest

log = logging.getLogger("neko.ui")


class UiBridge(QObject):
    state = Signal(object, str)            # AssistantState, detail
    token = Signal(str)
    reply = Signal(object)                 # coordinator.Reply
    routing = Signal(dict)
    resources = Signal(dict)
    tool = Signal(dict)
    task = Signal(dict)
    approval = Signal(object)              # ApprovalRequest
    error = Signal(str)
    busy = Signal(bool)
    need_capture = Signal()                # engine asks the GUI thread for a screenshot
    visual = Signal(object)                # side-panel content (title, markdown, image bytes, source)
    emotion = Signal(str)                  # her mood for the reply being written
    settings_changed = Signal(dict)        # e.g. voice gender / language switched by voice command
    reminder = Signal(dict)                # a reminder is due (routines/)

    def __init__(self, neko: Neko) -> None:
        super().__init__()
        self.neko = neko
        self._token: CancelToken | None = None
        self._lock = threading.Lock()
        self._busy = False
        self._jobs: dict[int, dict[str, Any]] = {}
        self._queue: deque[tuple[str, list[bytes] | None, str | None]] = deque()
        self._seq = 0
        bus = neko.bus
        # Requests from your phone run quietly: the PC's orb doesn't show, stream or speak them.
        bus.subscribe(ev.STATE, lambda e: e.origin or self.state.emit(e.payload["state"], e.payload.get("detail", "")))
        bus.subscribe(ev.TOKEN, lambda e: e.origin or self.token.emit(e.payload["text"]))
        bus.subscribe(ev.ROUTING, lambda e: self.routing.emit(dict(e.payload)))
        bus.subscribe(ev.RESOURCES, lambda e: self.resources.emit(dict(e.payload)))
        bus.subscribe(ev.TOOL_CALL, lambda e: self.tool.emit(dict(e.payload)))
        bus.subscribe(ev.TASK, lambda e: self.task.emit(dict(e.payload)))
        bus.subscribe(ev.VISUAL, lambda e: e.origin or self.visual.emit(dict(e.payload)))
        bus.subscribe(ev.SETTINGS, lambda e: self.settings_changed.emit(dict(e.payload)))
        bus.subscribe(ev.REMINDER, lambda e: self.reminder.emit(dict(e.payload)))
        bus.subscribe(ev.EMOTION, lambda e: e.origin or self.emotion.emit(str(e.payload.get("emotion", "neutral"))))
        neko.policy.set_approval_handler(self._on_approval_needed)
        self._shot: bytes | None = None
        self._shot_ready = threading.Event()
        neko.coordinator.screen_capturer = self.capture_blocking
        from .. import documents
        from .pdf_render import render_markdown_pdf

        documents.pdf_renderer = render_markdown_pdf

    def capture_blocking(self, timeout_s: float = 6.0) -> bytes | None:
        """Called on the request thread; the screenshot itself is taken on the GUI thread."""
        self._shot, self._shot_ready = None, threading.Event()
        self.need_capture.emit()
        self._shot_ready.wait(timeout_s)
        return self._shot

    def deliver_capture(self, png: bytes | None) -> None:
        self._shot = png
        self._shot_ready.set()

    # Called on the worker thread by the policy; the dialog resolves it on the GUI thread.
    def _on_approval_needed(self, req: ApprovalRequest) -> None:
        self.state.emit(AssistantState.AWAITING_APPROVAL, req.summary)
        self.approval.emit(req)

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def foreground_busy(self) -> bool:
        with self._lock:
            return any(not j["long"] for j in self._jobs.values())

    # Multitasking: two lanes. A long job (Claude Code on a project, study notes from a PDF) runs in
    # the background while normal chat keeps working; anything else waits in a short queue.
    def send(self, text: str, images: list[bytes] | None = None, conversation_id: str | None = None) -> str:
        """Returns "started", "parallel" (another job is still running) or "queued"."""
        long = is_long_job(text) and not images
        with self._lock:
            running_long = [j for j in self._jobs.values() if j["long"]]
            running_fg = [j for j in self._jobs.values() if not j["long"]]
            if not self._jobs:
                status = "started"
            elif len(self._jobs) == 1 and ((long and not running_long) or (not long and not running_fg)):
                status = "parallel"
            else:
                self._queue.append((text, images, conversation_id))
                return "queued"
            self._start(text, images, conversation_id, long)
        return status

    def _start(self, text: str, images: list[bytes] | None, conv: str | None, long: bool) -> None:
        """Caller holds self._lock."""
        self._seq += 1
        job = {"id": self._seq, "token": CancelToken(), "long": long, "goal": text[:60]}
        self._jobs[job["id"]] = job
        self._token = job["token"]
        if not self._busy:
            self._busy = True
            self.busy.emit(True)
        threading.Thread(target=self._run, args=(text, images, conv, job), daemon=True,
                         name=f"neko-request-{job['id']}").start()

    def _run(self, text: str, images: list[bytes] | None, conv: str | None, job: dict[str, Any]) -> None:
        try:
            r = self.neko.coordinator.handle(text, images=images, conversation_id=conv, token=job["token"])
            with self._lock:
                # finished while another request was in progress: the UI must not mix it into that one
                r.background = job["long"] and len(self._jobs) > 1
            r.goal = job["goal"]
            r.job_id = job["id"]
            self.reply.emit(r)
        except Exception as exc:  # noqa: BLE001 - never let the worker die silently
            log.exception("request failed")
            self.error.emit(f"Unexpected error: {exc}")
            self.state.emit(AssistantState.ERROR, str(exc))
        finally:
            with self._lock:
                self._jobs.pop(job["id"], None)
                if self._queue and not job["token"].cancelled:
                    q_text, q_images, q_conv = self._queue.popleft()
                    self._start(q_text, q_images, q_conv, is_long_job(q_text) and not q_images)
                idle = not self._jobs
                if idle:
                    self._busy = False
            if idle:
                self.busy.emit(False)

    @property
    def queued(self) -> int:
        return len(self._queue)

    def cancel(self) -> int | None:
        """Stop: cancels the newest job (the one being talked about) and anything queued. Returns its id."""
        with self._lock:
            self._queue.clear()
            newest = max(self._jobs.values(), key=lambda j: j["id"], default=None)
        if newest is not None:
            newest["token"].cancel("stopped by user")
            return int(newest["id"])
        return None

    def emergency_stop(self) -> int:
        with self._lock:
            self._queue.clear()
        n = self.neko.estop.trip()
        for req in list(self.neko.policy.pending.values()):
            req.resolve(False)
        return n

    def resume_after_stop(self) -> None:
        self.neko.estop.reset()
        self.state.emit(AssistantState.IDLE, "")

    def poll_resources(self) -> dict[str, Any]:
        snap = self.neko.monitor.snapshot()
        d = snap.as_dict()
        self.resources.emit(d)
        return d
