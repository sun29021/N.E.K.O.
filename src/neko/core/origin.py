"""Where the request being handled on this thread came from: "" (the PC itself) or "phone".

Phone conversations run through the same engine and safety rules, but the PC's orb must not show or
speak them, and approvals for them go to the phone too. The engine runs one request per thread and
asks for approvals on that same thread, so a thread-local is enough.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_local = threading.local()

PHONE = "phone"


def current() -> str:
    return getattr(_local, "origin", "")


@contextmanager
def from_origin(origin: str) -> Iterator[None]:
    previous = current()
    _local.origin = origin
    try:
        yield
    finally:
        _local.origin = previous
