"""Phone audio: whatever the phone recorded (Telegram OGG/Opus, browser WebM/Opus or MP4/AAC) -> 16 kHz
speech for Whisper, and her voice -> OGG/Opus voice notes or MP3/WAV clips for the call page.

Uses PyAV (already installed for the voices); imported lazily so the engine itself stays standard-library.
"""

from __future__ import annotations

import io
import wave
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError

MAX_SECONDS = 180


def _av() -> Any:
    try:
        import av
    except ImportError as exc:
        raise PeripheralUnavailableError("PyAV missing", user_message="Voice notes need the 'av' package "
                                         "(pip install av).") from exc
    return av


def to_pcm16(data: bytes, rate: int = 16000) -> bytes:
    """Any compressed recording -> mono 16-bit PCM at `rate` (at most MAX_SECONDS)."""
    av = _av()
    out = bytearray()
    try:
        with av.open(io.BytesIO(data)) as box:
            stream = next(s for s in box.streams if s.type == "audio")
            res = av.AudioResampler(format="s16", layout="mono", rate=rate)
            for frame in box.decode(stream):
                for f in res.resample(frame):
                    out += bytes(f.planes[0])[: f.samples * 2]
                if len(out) > MAX_SECONDS * rate * 2:
                    break
            for f in res.resample(None):
                out += bytes(f.planes[0])[: f.samples * 2]
    except (StopIteration, av.error.FFmpegError, ValueError) as exc:
        raise PeripheralUnavailableError(f"could not decode audio: {exc}",
                                         user_message="I couldn't play that recording.") from exc
    return bytes(out[: MAX_SECONDS * rate * 2])


def speech_audio(tts: Any, text: str, emotion: str = "neutral") -> tuple[Any, int]:
    """Her voice for `text` as (float32 mono numpy array, sample rate), using whatever voice is active."""
    import numpy as np

    token = CancelToken(timeout_s=120)
    gen = tts.pieces(text, emotion, token) if hasattr(tts, "pieces") else tts.utterances(text, emotion, token)
    parts = [u.audio for u in gen]
    if not parts:
        raise PeripheralUnavailableError("no speech produced")
    return np.concatenate(parts).astype("float32"), 24000


def ogg_opus(audio: Any, rate: int = 24000) -> bytes:
    """float32 mono -> OGG/Opus (what Telegram shows as a voice-note bubble)."""
    import numpy as np

    av = _av()
    buf = io.BytesIO()
    with av.open(buf, "w", format="ogg") as box:
        st = box.add_stream("libopus", rate=rate)
        st.layout = "mono"
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        step = rate // 50  # 20 ms frames
        for i in range(0, len(pcm), step):
            chunk = pcm[i:i + step]
            frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = rate
            for packet in st.encode(frame):
                box.mux(packet)
        for packet in st.encode(None):
            box.mux(packet)
    return buf.getvalue()


def wav(audio: Any, rate: int = 24000) -> bytes:
    import numpy as np

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def clip_for_call(tts: Any, sentence: str, emotion: str) -> tuple[bytes, str, list[tuple[str, float]]]:
    """One sentence for the call page: (audio bytes, mime type, word timings). The natural online voice is
    sent as the MP3 it arrives in (small, plays everywhere); the offline voice as WAV."""
    if hasattr(tts, "_synth") and hasattr(tts, "voice_for"):
        try:
            import asyncio

            from ..voice.tts_edge import STYLE, _Loop

            rate, pitch = STYLE.get(emotion, STYLE["neutral"])
            fut = asyncio.run_coroutine_threadsafe(tts._synth(sentence, tts.voice_for(sentence), rate, pitch),
                                                   _Loop.get())
            data, words = fut.result(timeout=getattr(tts, "timeout_s", 15))
            if data:
                return data, "audio/mpeg", words
        except Exception:  # noqa: BLE001 - offline: fall through to the local voice
            pass
    audio, rate = speech_audio(tts, sentence, emotion)
    from ..voice.playback import estimate_words

    return wav(audio, rate), "audio/wav", estimate_words(sentence, len(audio) / rate)
