"""Natural local speech with Kokoro-82M (Apache-2.0 weights) via kokoro-onnx (MIT).

Runs on the CPU (onnxruntime), fully offline, no account. espeak-ng is bundled by the
``espeakng-loader`` dependency, so nothing is installed system-wide.
Model files (~337 MB) are downloaded once by the user (docs/MODEL_GUIDE.md section 4):
  kokoro-v1.0.onnx (310 MB) and voices-v1.0.bin (27 MB) from the kokoro-onnx GitHub release.

Long replies are synthesised sentence by sentence and played as they become ready, so
speech starts after the first sentence instead of after the whole answer.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .tts import clean_for_speech

DEFAULT_DIR = Path(r"D:\NEKO-Data\voices\kokoro")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_LAUGH = re.compile(r"\b(?:ha(?:ha)+|he(?:he)+|hihi+|lol|lmao)\b[!.,]*\s*", re.IGNORECASE)


def prepare_spoken_text(text: str, emotion: str = "neutral") -> tuple[str, str]:
    """Make text sound natural when spoken by a TTS that cannot actually laugh:
    laughter words are removed (read aloud they sound like a robot saying "ha ha") and turn the
    delivery playful instead; "hmm"/"mm" get a little breathing room."""
    text = clean_for_speech(text)
    if _LAUGH.search(text):
        text = _LAUGH.sub("", text).strip()
        if emotion in ("neutral", "calm", "curious"):
            emotion = "playful"
    text = re.sub(r"\b(Hmm+|Mm+)\b[,.]?", r"\1...", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text, emotion


def _patched_kokoro_class() -> Any:
    from kokoro_onnx import MAX_PHONEME_LENGTH, SAMPLE_RATE, Kokoro
    import numpy as np

    class FixedKokoro(Kokoro):  # type: ignore[misc]
        """kokoro-onnx 0.4.9 passes ``speed`` as int32 to v1.0 models that expect float
        (measured: ONNXRuntime INVALID_ARGUMENT). Same logic, correct dtype."""

        def _create_audio(self, phonemes: str, voice: Any, speed: float) -> tuple[Any, int]:
            phonemes = phonemes[:MAX_PHONEME_LENGTH]
            tokens = np.array(self.tokenizer.tokenize(phonemes), dtype=np.int64)
            style = voice[len(tokens)]
            ids = [[0, *tokens, 0]]
            names = [i.name for i in self.sess.get_inputs()]
            inputs = ({"input_ids": ids, "style": np.array(style, dtype=np.float32),
                       "speed": np.array([speed], dtype=np.float32)} if "input_ids" in names else
                      {"tokens": ids, "style": style, "speed": np.ones(1, dtype=np.float32) * speed})
            return self.sess.run(None, inputs)[0], SAMPLE_RATE

    return FixedKokoro


class KokoroSynthesizer:
    supports_stream = True  # speak() also accepts a voice.base.TextStream

    def __init__(self, voice: str = "af_heart", speed: float = 0.92, volume: float = 0.9,
                 model_dir: str | Path = "") -> None:
        self.voice = voice
        self.speed = max(0.5, min(2.0, speed))
        self.volume = volume
        self.dir = Path(model_dir) if model_dir else DEFAULT_DIR
        self._k: Any = None
        self._lock = threading.Lock()
        # Called ~20x/s during playback with the loudness (0..1) of what is being spoken,
        # so the HUD core can pulse with the real voice.
        self.on_level: Any = None
        self.on_words: Any = None   # subtitle callback (words spoken so far in the current sentence)

    @property
    def lang(self) -> str:
        return "en-gb" if self.voice[:1] == "b" else "en-us"

    def available(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
            import sounddevice  # noqa: F401
        except (ImportError, OSError):
            return False, "kokoro-onnx / sounddevice not installed (setup.ps1 -Apply -WithVoice)"
        for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
            if not (self.dir / f).is_file():
                return False, f"Kokoro model file {f} missing in {self.dir} (see MODEL_GUIDE)"
        return True, f"Kokoro natural voice '{self.voice}' (local, CPU)"

    def _model(self) -> Any:
        with self._lock:
            if self._k is None:
                ok, why = self.available()
                if not ok:
                    raise PeripheralUnavailableError(why, user_message=f"Natural voice isn't ready: {why}.")
                cls = _patched_kokoro_class()
                self._k = cls(str(self.dir / "kokoro-v1.0.onnx"), str(self.dir / "voices-v1.0.bin"))
            return self._k

    def voices(self) -> list[str]:
        return sorted(self._model().get_voices())

    def synthesize(self, text: str) -> tuple[Any, int]:
        """Whole text -> (float32 samples, sample_rate). Used for files and tests."""
        return self._model().create(clean_for_speech(text), voice=self.voice, speed=self.speed, lang=self.lang)

    def style_for(self, emotion: str) -> tuple[Any, float]:
        """Voice style vector + speed for an emotion: the base voice blended with a brighter
        (af_bella) or softer (af_nicole) voice, and a faster or slower pace."""
        from ..core.emotion import STYLES

        k = self._model()
        st = STYLES.get(emotion, STYLES["neutral"])
        style: Any = k.get_voice_style(self.voice)
        voices = set(k.get_voices())
        for other, weight in st.blend:
            if other in voices and other != self.voice:
                style = style * (1 - weight) + k.get_voice_style(other) * weight
        return style, max(0.5, min(2.0, self.speed * st.speed))

    def render_speech(self, text: str, emotion: str = "neutral") -> tuple[Any, int]:
        """Whole utterance as ONE smooth buffer (used for tests/files): same shaping as speak()."""
        import numpy as np

        parts = [audio for audio, _pause in self._chunks(text, emotion, CancelToken())]
        sr = 24000
        return (np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)), sr

    def _sentence_audio(self, sentence: str, style: Any, speed: float) -> tuple[Any, Any]:
        """One sentence -> (audio, pause): faded edges (no clicks) + a natural pause after it."""
        import numpy as np

        samples, sr = self._model().create(sentence, voice=style, speed=speed, lang=self.lang)
        audio = np.asarray(samples, dtype=np.float32) * self.volume
        fade = min(len(audio) // 4, int(sr * 0.008))  # 8 ms fades
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            audio[:fade] *= ramp
            audio[-fade:] *= ramp[::-1]
        pause = {"?": 0.34, "!": 0.28, ".": 0.30, ",": 0.16}.get(sentence.rstrip()[-1:], 0.24)
        return np.clip(audio, -1, 1), np.zeros(int(sr * pause), dtype=np.float32)

    def _chunks(self, text: str, emotion: str, token: CancelToken):  # noqa: ANN202 - generator
        """Yield (audio, pause_after) per sentence."""
        for _sentence, audio, pause in self._sentences(text, emotion, token):
            yield audio, pause

    def _sentences(self, text: str, emotion: str, token: CancelToken):  # noqa: ANN202 - generator
        text, emotion = prepare_spoken_text(text, emotion)
        if not text:
            return
        style, speed = self.style_for(emotion)
        for sentence in [s for s in _SENTENCE.split(text) if s.strip()]:
            if token.cancelled:
                return
            audio, pause = self._sentence_audio(sentence, style, speed)
            yield sentence, audio, pause

    def utterances(self, text: Any, emotion: str, token: CancelToken):  # noqa: ANN202 - generator
        """Sentences as playback pieces with estimated word times (for word-by-word subtitles)."""
        import numpy as np

        from .base import TextStream
        from .playback import Utterance, estimate_words

        for chunk in (text.pieces(token) if isinstance(text, TextStream) else [text]):
            for sentence, audio, pause in self._sentences(str(chunk), emotion, token):
                yield Utterance(np.concatenate([audio, pause]), estimate_words(sentence, len(audio) / 24000))

    def speak(self, text: Any, token: CancelToken, emotion: str = "neutral") -> None:
        """Gap-free playback (one continuous output stream; the next sentence is synthesised while the
        current one plays) with word timings for subtitles. ``text`` may be a TextStream."""
        from .playback import play

        play(self.utterances(text, emotion, token), token, on_level=self.on_level,
             on_words=getattr(self, "on_words", None))