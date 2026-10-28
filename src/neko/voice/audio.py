"""Microphone capture for push-to-talk and the voice session controller.

Echo control strategy: the microphone is *gated* - capture never runs while
N.E.K.O. is speaking, and wake-word detection is paused during playback plus a
short tail. This is simpler and more reliable on laptops than acoustic echo
cancellation, at the cost of not supporting "barge-in" by voice (use the
Stop button / hotkey to interrupt speech).

Raw audio is kept in memory only and discarded after transcription unless
``voice.keep_recordings`` is enabled.
"""

from __future__ import annotations

import threading
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError

SAMPLE_RATE = 16_000


class PushToTalkRecorder:
    """Call ``start()`` when the key/button goes down and ``stop()`` when it is
    released; ``stop`` returns 16-bit mono PCM bytes."""

    def __init__(self, device: str | int | None = None, max_seconds: float = 60) -> None:
        self.device = device or None
        self.max_seconds = max_seconds
        self._chunks: list[bytes] = []
        self._stream: Any = None
        self._lock = threading.Lock()
        self.level = 0.0  # for the HUD waveform (0..1)

    @staticmethod
    def available() -> tuple[bool, str]:
        try:
            import sounddevice as sd
        except ImportError:
            return False, "sounddevice is not installed (scripts\\setup.ps1 -WithVoice)"
        except OSError as exc:  # PortAudio missing
            return False, f"audio backend unavailable: {exc}"
        try:
            sd.query_devices(kind="input")
        except Exception as exc:  # noqa: BLE001
            return False, f"no microphone found: {exc}"
        return True, "microphone available"

    def start(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise PeripheralUnavailableError(str(exc), user_message="Voice input components are not installed.") from exc
        self._chunks = []
        max_bytes = int(self.max_seconds * SAMPLE_RATE * 2)

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            data = bytes(indata)
            with self._lock:
                if sum(len(c) for c in self._chunks) < max_bytes:
                    self._chunks.append(data)
            arr = np.frombuffer(data, dtype=np.int16)
            self.level = min(1.0, float(np.abs(arr).mean()) / 6000.0) if len(arr) else 0.0

        try:
            self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                             device=self.device, callback=callback, blocksize=1600)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            raise PeripheralUnavailableError(str(exc), user_message=(
                "I couldn't open the microphone. Check Windows Settings > Privacy > Microphone and "
                "that the right input device is selected.")) from exc

    def stop(self) -> bytes:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        self.level = 0.0
        with self._lock:
            data, self._chunks = b"".join(self._chunks), []
        return data


class SpeechGate:
    """Shared flag: True while N.E.K.O. is speaking. Capture and wake word
    detection check it to avoid transcribing the assistant's own voice."""

    def __init__(self) -> None:
        self._speaking = threading.Event()

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def speak_with_gate(self, synth: Any, text: str, token: CancelToken, emotion: str = "neutral") -> None:
        self._speaking.set()
        try:
            import inspect

            if "emotion" in inspect.signature(synth.speak).parameters:
                synth.speak(text, token, emotion)  # Kokoro: emotion-coloured voice
            else:
                synth.speak(text, token)           # engines without emotion support
        finally:
            token.wait(0.3)  # tail so room echo dies down
            self._speaking.clear()
