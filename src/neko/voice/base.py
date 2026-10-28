"""Voice contracts (docs/VOICE_DESIGN.md section 3)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..core.cancel import CancelToken


@dataclass
class Transcript:
    text: str
    language: str
    duration_s: float
    avg_logprob: float | None = None
    elapsed_ms: float | None = None

    @property
    def low_confidence(self) -> bool:
        return self.avg_logprob is not None and self.avg_logprob < -1.0


@runtime_checkable
class SpeechRecognizer(Protocol):
    def available(self) -> tuple[bool, str]: ...

    def transcribe(self, pcm16: bytes, sample_rate: int, *, language: str | None, token: CancelToken) -> Transcript: ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    def available(self) -> tuple[bool, str]: ...

    def speak(self, text: str, token: CancelToken) -> None:
        """Blocking playback; must stop promptly when ``token`` is cancelled."""
        ...


@runtime_checkable
class WakeWordDetector(Protocol):
    def available(self) -> tuple[bool, str]: ...

    def start(self, on_detect: Callable[[str, float], None], token: CancelToken) -> None: ...


class TextStream:
    """Text that arrives while the model is still writing: sentences are ``put`` as they complete and
    the voice starts speaking the first one immediately (instead of waiting for the whole reply)."""

    def __init__(self) -> None:
        import queue

        self._q: queue.Queue[str | None] = queue.Queue()
        self._parts: list[str] = []
        self.closed = False

    def put(self, text: str) -> None:
        if text.strip() and not self.closed:
            self._parts.append(text)
            self._q.put(text)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._q.put(None)

    def pieces(self, token: CancelToken, timeout_s: float = 180.0):  # noqa: ANN201 - generator
        """Yield pieces until closed (or cancelled / nothing arrives for ``timeout_s``)."""
        import queue

        idle = 0.0
        while not token.cancelled and idle < timeout_s:
            try:
                item = self._q.get(timeout=0.2)  # short waits, so Stop is noticed at once
            except queue.Empty:
                idle += 0.2
                continue
            if item is None:
                return
            idle = 0.0
            yield item

    def full_text(self, token: CancelToken) -> str:
        """For engines that can't stream: wait for the end and return everything."""
        return " ".join(self.pieces(token))


class NullSynthesizer:
    def available(self) -> tuple[bool, str]:
        return True, "speech output disabled"

    def speak(self, text: str, token: CancelToken) -> None:
        return None
