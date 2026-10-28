"""Natural neural voices (Microsoft Edge "Read aloud" voices via the free ``edge-tts`` package).

* English and **native Bangla**, female and male: chosen per sentence (Bengali script -> Bangla voice).
* Word-boundary timings come with the audio, so subtitles appear exactly as each word is spoken.
* Online only: the text she speaks is sent to Microsoft's speech service. When it can't be reached, the
  local Kokoro voice takes over for 10 minutes (Kokoro has no Bangla; she says so instead of mangling it).
* The next sentence is synthesised while the current one plays; mp3 is decoded locally with PyAV.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import threading
import time
from collections.abc import Iterator
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .playback import RATE, Utterance, play
from .tts import clean_for_speech

log = logging.getLogger("neko.voice.edge")

VOICES = {
    ("en", "female"): "en-US-AvaMultilingualNeural",
    ("en", "male"): "en-US-AndrewMultilingualNeural",
    ("bn", "female"): "bn-BD-NabanitaNeural",
    ("bn", "male"): "bn-BD-PradeepNeural",
}
# emotion -> (rate, pitch): small changes sound natural; big ones sound robotic
STYLE = {"happy": ("+4%", "+2Hz"), "excited": ("+8%", "+4Hz"), "playful": ("+5%", "+3Hz"), "caring": ("-6%", "-1Hz"),
         "sad": ("-10%", "-3Hz"), "calm": ("-4%", "+0Hz"), "curious": ("+2%", "+2Hz"), "serious": ("-3%", "-2Hz"),
         "surprised": ("+6%", "+4Hz"), "neutral": ("+0%", "+0Hz")}
_BENGALI = re.compile(r"[ঀ-৿]")
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")   # । = Bangla full stop (dari)


def language_of(text: str) -> str:
    return "bn" if len(_BENGALI.findall(text)) >= max(2, len(text) * 0.2) else "en"


class _Loop:
    """One background asyncio loop for all edge-tts requests."""

    _lock = threading.Lock()
    _loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get(cls) -> asyncio.AbstractEventLoop:
        with cls._lock:
            if cls._loop is None:
                cls._loop = asyncio.new_event_loop()
                threading.Thread(target=cls._loop.run_forever, daemon=True, name="neko-edge-tts").start()
            return cls._loop


def decode_mp3(data: bytes) -> Any:
    """mp3 bytes -> float32 mono 24 kHz numpy array (PyAV ships its own FFmpeg)."""
    import av
    import numpy as np

    out = []
    with av.open(io.BytesIO(data)) as box:
        res = av.AudioResampler(format="flt", layout="mono", rate=RATE)
        for frame in box.decode(audio=0):
            for f in res.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out).astype(np.float32) if out else np.zeros(0, dtype=np.float32)


class EdgeSynthesizer:
    supports_stream = True

    def __init__(self, gender: str = "female", fallback: Any = None, volume: float = 0.9,
                 voices: dict[tuple[str, str], str] | None = None, timeout_s: float = 12.0) -> None:
        self.gender = gender if gender in ("female", "male") else "female"
        self.fallback = fallback          # KokoroSynthesizer (offline)
        self.volume = volume
        self.voices = {**VOICES, **(voices or {})}
        self.timeout_s = timeout_s
        self.on_level: Any = None
        self.on_words: Any = None         # subtitle callback: words spoken so far in this sentence
        self._down_until = 0.0

    def available(self) -> tuple[bool, str]:
        try:
            import av  # noqa: F401
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts / PyAV not installed"
        return True, "Microsoft neural voices (online)"

    def voice_for(self, text: str) -> str:
        return self.voices[(language_of(text), self.gender)]

    # ------------------------------------------------------------------ synthesis
    async def _synth(self, text: str, voice: str, rate: str, pitch: str) -> tuple[bytes, list[tuple[str, float]]]:
        import edge_tts

        audio, words = bytearray(), []
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
        async for ch in c.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                words.append((str(ch["text"]), float(ch["offset"]) / 1e7))
        return bytes(audio), words

    def synthesize_piece(self, text: str, emotion: str = "neutral") -> Utterance:
        import numpy as np

        rate, pitch = STYLE.get(emotion, STYLE["neutral"])
        fut = asyncio.run_coroutine_threadsafe(self._synth(text, self.voice_for(text), rate, pitch), _Loop.get())
        data, words = fut.result(timeout=self.timeout_s)
        if not data:
            raise PeripheralUnavailableError("edge-tts returned no audio")
        audio = decode_mp3(data)
        pause = {"?": 0.32, "!": 0.26, ".": 0.28, "।": 0.28, ",": 0.14}.get(text.rstrip()[-1:], 0.22)
        return Utterance(np.concatenate([audio, np.zeros(int(RATE * pause), dtype=np.float32)]), words)

    def _offline_piece(self, text: str, emotion: str, token: CancelToken) -> Iterator[Utterance]:
        if self.fallback is None:
            return
        if language_of(text) == "bn":
            text = "Sorry, I need the internet to speak Bangla."
        yield from self.fallback.utterances(text, emotion, token)

    def pieces(self, text: Any, emotion: str, token: CancelToken) -> Iterator[Utterance]:
        from .base import TextStream

        chunks = text.pieces(token) if isinstance(text, TextStream) else [text]
        for chunk in chunks:
            for sentence in [s for s in _SENTENCE.split(clean_for_speech(str(chunk))) if s.strip()]:
                if token.cancelled:
                    return
                if time.monotonic() < self._down_until:
                    yield from self._offline_piece(sentence, emotion, token)
                    continue
                try:
                    yield self.synthesize_piece(sentence, emotion)
                except Exception as exc:  # noqa: BLE001 - offline, blocked, service change...
                    log.warning("online voice unavailable (%s); using the local voice for 10 min", str(exc)[:120])
                    self._down_until = time.monotonic() + 600
                    yield from self._offline_piece(sentence, emotion, token)

    def speak(self, text: Any, token: CancelToken, emotion: str = "neutral") -> None:
        if self.fallback is not None:
            self.fallback.on_level = self.on_level
        play(self.pieces(text, emotion, token), token, on_level=self.on_level, on_words=self.on_words,
             volume=self.volume / 0.9 if self.volume else 1.0)

    def synthesize(self, text: str) -> tuple[Any, int]:
        """Whole text -> (audio, rate). For tests/files."""
        import numpy as np

        parts = [p.audio for p in self.pieces(text, "neutral", CancelToken())]
        return (np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)), RATE


__all__ = ["STYLE", "VOICES", "EdgeSynthesizer", "decode_mp3", "language_of"]
