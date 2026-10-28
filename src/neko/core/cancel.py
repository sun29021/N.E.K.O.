"""Cooperative cancellation shared by tasks, model streams, tools and speech.

Cancellation is cooperative: long operations must call ``raise_if_cancelled``
between steps. A side effect that already happened cannot be undone by
cancelling, which is why tools record what they did before returning.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .errors import CancelledError


class CancelToken:
    """Thread-safe cancellation flag with optional deadline and child tokens."""

    def __init__(self, timeout_s: float | None = None, parent: CancelToken | None = None) -> None:
        self._event = threading.Event()
        self._reason = ""
        self._deadline = time.monotonic() + timeout_s if timeout_s else None
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._parent = parent
        if parent is not None:
            parent.on_cancel(lambda: self.cancel(parent.reason or "parent cancelled"))

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def cancelled(self) -> bool:
        if self._event.is_set():
            return True
        if self._deadline is not None and time.monotonic() >= self._deadline:
            self.cancel("timeout")
            return True
        return False

    def remaining(self) -> float | None:
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - time.monotonic())

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._reason = reason
            self._event.set()
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001 - a callback must never break cancellation
                pass

    def on_cancel(self, callback: Callable[[], None]) -> None:
        with self._lock:
            already = self._event.is_set()
            if not already:
                self._callbacks.append(callback)
        if already:
            callback()

    def child(self, timeout_s: float | None = None) -> CancelToken:
        return CancelToken(timeout_s=timeout_s, parent=self)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError(self._reason or "cancelled")

    def wait(self, seconds: float) -> bool:
        """Sleep up to ``seconds``; returns True if cancelled meanwhile."""
        return self._event.wait(seconds) or self.cancelled


class EmergencyStop:
    """Global kill switch. Tripping it cancels every registered token and
    disables computer control until explicitly reset by the user."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: list[CancelToken] = []
        self._tripped = False
        self._listeners: list[Callable[[bool], None]] = []

    @property
    def tripped(self) -> bool:
        return self._tripped

    def register(self, token: CancelToken) -> CancelToken:
        """Track a task so trip() can cancel it. While tripped, NEW requests still run (you can keep
        talking), but the permission policy blocks every action until reset() - previously every new
        message was cancelled at once, which looked like N.E.K.O. was broken ("Stopped.")."""
        with self._lock:
            self._tokens = [t for t in self._tokens if not t.cancelled]
            self._tokens.append(token)
        return token

    def subscribe(self, listener: Callable[[bool], None]) -> None:
        self._listeners.append(listener)

    def trip(self) -> int:
        with self._lock:
            self._tripped = True
            tokens, self._tokens = self._tokens, []
        for t in tokens:
            t.cancel("emergency stop")
        for listener in self._listeners:
            listener(True)
        return len(tokens)

    def reset(self) -> None:
        with self._lock:
            self._tripped = False
        for listener in self._listeners:
            listener(False)
