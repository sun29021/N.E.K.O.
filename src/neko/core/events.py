"""A tiny synchronous publish/subscribe bus.

The UI subscribes to engine events (state changes, tokens, approvals) and
marshals them onto the Qt thread itself; the engine never imports Qt.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Well-known topics
STATE = "state"                  # payload: {"state": AssistantState, "detail": str}
TOKEN = "token"                  # payload: {"task_id": str, "text": str}
MESSAGE = "message"              # payload: {"role": str, "content": str, ...}
TASK = "task"                    # payload: task status dict
TOOL_CALL = "tool_call"          # payload: tool invocation summary
APPROVAL_REQUEST = "approval"    # payload: ApprovalRequest
ROUTING = "routing"              # payload: routing decision dict
RESOURCES = "resources"          # payload: ResourceSnapshot dict
ERROR = "error"                  # payload: {"message": str}
SETTINGS = "settings"            # payload: changed settings (e.g. voice gender) - the UI applies them live
EMOTION = "emotion"              # payload: {"emotion": str} - her mood, known as soon as she starts answering
VISUAL = "visual"                # payload: {"title", "markdown", "image": bytes|None, "source", "kind"}


@dataclass
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._subs[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._subs[topic]:
                    self._subs[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, **payload: Any) -> None:
        with self._lock:
            handlers = list(self._subs.get(topic, ())) + list(self._subs.get("*", ()))
        event = Event(topic, payload)
        for h in handlers:
            try:
                h(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not break the engine
                log.exception("event handler failed for topic %s", topic)
