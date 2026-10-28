"""Text-to-speech adapters.

* ``SapiSynthesizer`` - built into Windows (System.Speech via PowerShell). Zero
  downloads, offline, English voices that ship with Windows. Default.
* ``PiperSynthesizer`` - higher quality neural voices. Piper (GPL-3.0) is run
  as a separate executable, not imported, and is never bundled with N.E.K.O.
  The user downloads piper and a voice (.onnx + .onnx.json) themselves.

Text is passed via stdin, never on a command line, so it cannot be
interpreted as PowerShell code.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError

_SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = {rate:d}
$s.Volume = {volume:d}
$text = [Console]::In.ReadToEnd()
$s.Speak($text)
"""


def clean_for_speech(text: str) -> str:
    from ..core.emotion import split_emotion, strip_emoji

    text = strip_emoji(split_emotion(text)[1])
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_#>|]+", " ", text)
    text = re.sub(r"https?://\S+", " link ", text)
    return re.sub(r"\s+", " ", text).strip()[:4000]


class SapiSynthesizer:
    def __init__(self, rate: float = 1.0, volume: float = 0.9) -> None:
        self.rate = max(-10, min(10, int(round((rate - 1.0) * 10))))
        self.volume = max(0, min(100, int(volume * 100)))

    def available(self) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "Windows SAPI is only available on Windows"
        return True, "Windows built-in speech (SAPI)"

    def speak(self, text: str, token: CancelToken) -> None:
        text = clean_for_speech(text)
        if not text:
            return
        # Only integers we computed are formatted into the script; the text goes via stdin.
        script = _SAPI_SCRIPT.replace("{rate:d}", str(int(self.rate))).replace("{volume:d}", str(int(self.volume)))
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        token.on_cancel(proc.kill)
        try:
            assert proc.stdin is not None
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        while proc.poll() is None:
            if token.wait(0.1):
                proc.kill()
                break


class PiperSynthesizer:
    def __init__(self, exe: str, voice: str, volume: float = 0.9) -> None:
        self.exe = exe
        self.voice = voice
        self.volume = volume

    def available(self) -> tuple[bool, str]:
        if not self.exe or not Path(self.exe).is_file():
            return False, "piper executable not configured (voice.piper_exe)"
        if not self.voice or not Path(self.voice).is_file():
            return False, "piper voice not configured (voice.piper_voice)"
        return True, f"Piper voice {Path(self.voice).stem}"

    def speak(self, text: str, token: CancelToken) -> None:
        ok, why = self.available()
        if not ok:
            raise PeripheralUnavailableError(why, user_message=f"Piper speech isn't set up: {why}.")
        text = clean_for_speech(text)
        if not text:
            return
        with tempfile.TemporaryDirectory(prefix="neko-tts-") as tmp:
            wav = Path(tmp) / "out.wav"
            proc = subprocess.Popen([self.exe, "--model", self.voice, "--output_file", str(wav)],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            token.on_cancel(proc.kill)
            assert proc.stdin is not None
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            while proc.poll() is None:
                if token.wait(0.05):
                    proc.kill()
                    return
            if proc.returncode != 0 or not wav.exists():
                raise PeripheralUnavailableError(f"piper exit {proc.returncode}")
            _play_wav(wav, token)


def _play_wav(path: Path, token: CancelToken) -> None:
    if sys.platform != "win32":
        return
    import wave
    import winsound

    with wave.open(str(path)) as w:
        duration = w.getnframes() / float(w.getframerate())
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    if token.wait(duration + 0.2):
        winsound.PlaySound(None, 0)  # stop playback


class FallbackSynthesizer:
    """Cloud voice first; when it fails (free credits used up, no internet, bad key) switch to the
    local voice for an hour instead of going silent."""

    def __init__(self, primary: object, fallback: object) -> None:
        self.primary, self.fallback = primary, fallback
        self._down_until = 0.0
        self.on_level = None

    def available(self) -> tuple[bool, str]:
        ok, why = self.primary.available()  # type: ignore[attr-defined]
        return (True, why) if ok else self.fallback.available()  # type: ignore[attr-defined]

    def speak(self, text: str, token: CancelToken, emotion: str = "neutral") -> None:
        import inspect
        import time

        for obj in (self.primary, self.fallback):
            if hasattr(obj, "on_level"):
                obj.on_level = self.on_level  # type: ignore[attr-defined]
        if time.monotonic() >= self._down_until and self.primary.available()[0]:  # type: ignore[attr-defined]
            try:
                self.primary.speak(text, token)  # type: ignore[attr-defined]
                return
            except PeripheralUnavailableError:
                self._down_until = time.monotonic() + 3600
        if "emotion" in inspect.signature(self.fallback.speak).parameters:  # type: ignore[attr-defined]
            self.fallback.speak(text, token, emotion)  # type: ignore[attr-defined]
        else:
            self.fallback.speak(text, token)  # type: ignore[attr-defined]


def _kokoro_for(v: object) -> object:
    from .tts_kokoro import KokoroSynthesizer

    male = getattr(v, "gender", "female") == "male"
    voice = getattr(v, "kokoro_voice_male", "am_michael") if male else getattr(v, "kokoro_voice", "af_heart")
    return KokoroSynthesizer(voice, getattr(v, "kokoro_speed", 0.92), getattr(v, "tts_volume", 0.9),
                             getattr(v, "kokoro_dir", ""))


def build_synthesizer(voice_settings: object, *, cloud_allowed: bool = False, network_allowed: bool = False) -> object:
    """Pick the configured engine; if it can't run here, fall back to Windows SAPI (always offline)."""
    from .base import NullSynthesizer

    v = voice_settings
    engine = getattr(v, "tts_engine", "none")
    sapi = SapiSynthesizer(getattr(v, "tts_rate", 1.0), getattr(v, "tts_volume", 0.9))
    chosen: object | None = None
    if engine == "edge":
        # natural Microsoft neural voices online (English + native Bangla), Kokoro offline
        local = _kokoro_for(v)
        if network_allowed:
            from .tts_edge import EdgeSynthesizer

            overrides = {k: val for k, val in ((("en", getattr(v, "gender", "female")), getattr(v, "edge_voice_en", "")),
                                               (("bn", getattr(v, "gender", "female")), getattr(v, "edge_voice_bn", "")))
                         if val}
            edge = EdgeSynthesizer(getattr(v, "gender", "female"), fallback=local if local.available()[0] else None,
                                   volume=getattr(v, "tts_volume", 0.9), voices=overrides)
            if edge.available()[0]:
                return edge
        engine = "kokoro"  # no internet allowed / package missing: the local voice
    if engine == "kokoro":
        from .tts_kokoro import KokoroSynthesizer

        chosen = _kokoro_for(v)
    elif engine == "elevenlabs":
        from .tts_elevenlabs import ElevenLabsSynthesizer
        from .tts_kokoro import KokoroSynthesizer

        eleven = ElevenLabsSynthesizer(getattr(v, "elevenlabs_voice_id", ""),
                                       getattr(v, "elevenlabs_key_env", "ELEVENLABS_API_KEY"),
                                       cloud_allowed=cloud_allowed, volume=getattr(v, "tts_volume", 0.9))
        local = KokoroSynthesizer(getattr(v, "kokoro_voice", "af_heart"), getattr(v, "kokoro_speed", 0.92),
                                  getattr(v, "tts_volume", 0.9), getattr(v, "kokoro_dir", ""))
        chosen = FallbackSynthesizer(eleven, local if local.available()[0] else sapi)
    elif engine == "piper":
        chosen = PiperSynthesizer(getattr(v, "piper_exe", ""), getattr(v, "piper_voice", ""))
    elif engine == "sapi":
        return sapi
    else:
        return NullSynthesizer()
    ok, _why = chosen.available()  # type: ignore[attr-defined]
    return chosen if ok else sapi
