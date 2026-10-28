"""Speech-to-text with faster-whisper (CTranslate2). Optional dependency.

Model weights are downloaded by faster-whisper from Hugging Face on first use
*only if* the user runs the documented acquisition step; N.E.K.O. passes
``local_files_only=True`` so it never downloads silently.

Memory guide (int8): tiny ~75 MB, base ~145 MB, small ~490 MB, medium ~1.5 GB.
Measured 2026-10-28 on the RTX 3050 (4 GB) next to llama3.2:3b: small CPU int8 3.1 s/sentence, small GPU
0.3 s, large-v3-turbo GPU int8_float16 0.5 s using ~1.1 GB VRAM. CUDA needs the `nvidia-cublas-cu12` and
`nvidia-cudnn-cu12` packages; on any GPU problem it falls back to `fallback_model` on the CPU.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import sys
import threading
import time
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .base import Transcript

log = logging.getLogger("neko.voice.stt")


_DLL_DIRS_ADDED = False


def _add_cuda_dlls() -> None:
    """Make NVIDIA's cuBLAS/cuDNN from the venv's ``nvidia-*-cu12`` packages findable (Windows).
    Without them CUDA speech fails with 'cublas64_12.dll is not found'."""
    global _DLL_DIRS_ADDED
    if _DLL_DIRS_ADDED or sys.platform != "win32":
        return
    _DLL_DIRS_ADDED = True
    for d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
        try:
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        except OSError:
            continue


class FasterWhisperRecognizer:
    def __init__(self, model: str = "small", device: str = "auto", compute_type: str = "int8",
                 download_root: str | None = None, vram_free_mb: int | None = None,
                 fallback_model: str = "small") -> None:
        self.model_name = model
        self.device = device
        if device == "auto":
            self.device = "cuda" if (vram_free_mb or 0) > 1500 else "cpu"
        self.compute_type = compute_type if self.device == "cpu" else "int8_float16"
        self.download_root = download_root or None
        # GPU trouble (libraries missing, out of memory): use this model on the CPU instead. Big models
        # like large-v3-turbo are far too slow on a laptop CPU (measured: small CPU 3.1 s/sentence).
        self.fallback_model = fallback_model
        self._model: Any = None
        self._lock = threading.Lock()

    def _to_cpu_fallback(self, why: str) -> None:
        log.warning("GPU speech recognition unavailable (%s); using %s on the CPU", why, self.fallback_model)
        self._model, self.device, self.compute_type = None, "cpu", "int8"
        if self.model_name != self.fallback_model:
            self.model_name, self.download_root = self.fallback_model, None

    def available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed (scripts\\setup.ps1 -WithVoice)"
        return True, f"faster-whisper {self.model_name} on {self.device}"

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise PeripheralUnavailableError("faster-whisper missing", user_message=(
                        "Voice input needs the optional voice components. Run scripts\\setup.ps1 -WithVoice.")) from exc
                if self.device != "cpu":
                    _add_cuda_dlls()
                    try:
                        self._model = WhisperModel(self.model_name, device=self.device,
                                                   compute_type=self.compute_type,
                                                   download_root=self.download_root, local_files_only=True)
                        return self._model
                    except Exception as exc:  # noqa: BLE001 - CUDA/cuDNN/OOM errors vary
                        self._to_cpu_fallback(str(exc)[:160])
                try:
                    self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type,
                                               download_root=self.download_root, local_files_only=True)
                except Exception as exc:  # noqa: BLE001 - library raises various errors
                    raise PeripheralUnavailableError(str(exc), user_message=(
                        f"The speech model '{self.model_name}' isn't downloaded yet. See docs/MODEL_GUIDE.md "
                        "section 'Speech recognition' for the one-time download command.")) from exc
            return self._model

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def transcribe(self, pcm16: bytes, sample_rate: int, *, language: str | None, token: CancelToken,
                   hotwords: str | None = None, prompt: str | None = None) -> Transcript:
        import numpy as np

        model = self._load()
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate != 16000:
            # simple linear resample; capture is configured for 16 kHz so this is a fallback only
            n = int(len(audio) * 16000 / sample_rate)
            audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio)
        start = time.perf_counter()
        extra: dict[str, Any] = {"hotwords": hotwords} if hotwords else {}
        if prompt:  # personal vocabulary: spells names right ("up a Radhi" -> "Oporadhi", measured)
            extra["initial_prompt"] = prompt
        try:
            texts, logprobs, info = self._decode(model, audio, language, token, extra)
        except RuntimeError as exc:
            # Seen live: device "auto" chose CUDA but cuBLAS/cuDNN for CUDA 12 aren't installed.
            # Fall back to the CPU once instead of failing every utterance.
            if self.device == "cpu" or not re.search(r"cublas|cudnn|cuda|out of memory", str(exc), re.IGNORECASE):
                raise
            with self._lock:
                self._to_cpu_fallback(str(exc)[:160])
            texts, logprobs, info = self._decode(self._load(), audio, language, token, extra)
        return Transcript(
            text="".join(texts).strip(), language=info.language, duration_s=len(audio) / 16000,
            avg_logprob=sum(logprobs) / len(logprobs) if logprobs else None,
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )

    @staticmethod
    def _decode(model: Any, audio: Any, language: str | None, token: CancelToken,
                extra: dict[str, Any]) -> tuple[list[str], list[float], Any]:
        segments, info = model.transcribe(audio, language=language or None, beam_size=1, vad_filter=True,
                                          condition_on_previous_text=False, **extra)
        texts, logprobs = [], []
        for seg in segments:  # generator: decoding happens while iterating, so cancellation works here
            token.raise_if_cancelled()
            texts.append(seg.text)
            logprobs.append(seg.avg_logprob)
        return texts, logprobs, info
