"""Optional wake word via openWakeWord (Apache-2.0 code).

Feasibility (checked 2026-10-27): openWakeWord ships a pre-trained
``hey_jarvis`` model, so "Hey Jarvis" works without training. Its pre-trained
models are licensed CC BY-NC-SA 4.0 (non-commercial) - fine for personal use,
but they must not be bundled in a commercial redistribution. A custom phrase
(e.g. "Hey Neko") requires training a model with the project's notebook on a
machine with a GPU; see docs/VOICE_DESIGN.md section 5.

Off by default. When enabled, the microphone stream is processed locally in
80 ms frames; no audio is stored. The HUD shows a persistent "wake word
listening" indicator while it runs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .audio import SAMPLE_RATE, SpeechGate


class OpenWakeWordDetector:
    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.6, gate: SpeechGate | None = None,
                 device: str | int | None = None) -> None:
        self.model_name = model
        self.threshold = threshold
        self.gate = gate
        self.device = device or None
        self._thread: threading.Thread | None = None

    def available(self) -> tuple[bool, str]:
        try:
            import openwakeword  # noqa: F401
            import sounddevice  # noqa: F401
        except (ImportError, OSError):
            return False, "openwakeword/sounddevice not installed (scripts\\setup.ps1 -WithWakeWord)"
        return True, f"openWakeWord '{self.model_name}'"

    def start(self, on_detect: Callable[[str, float], None], token: CancelToken) -> None:
        ok, why = self.available()
        if not ok:
            raise PeripheralUnavailableError(why, user_message="Wake word components are not installed.")
        self._thread = threading.Thread(target=self._run, args=(on_detect, token), daemon=True, name="neko-wakeword")
        self._thread.start()

    def _run(self, on_detect: Callable[[str, float], None], token: CancelToken) -> None:
        import numpy as np
        import sounddevice as sd
        from openwakeword.model import Model

        model: Any = Model(wakeword_models=[self.model_name], inference_framework="onnx")
        frame = 1280  # 80 ms at 16 kHz, as recommended by openWakeWord
        cooldown = 0
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame,
                            device=self.device) as stream:
            while not token.cancelled:
                data, _ = stream.read(frame)
                if self.gate is not None and self.gate.speaking:
                    continue
                scores = model.predict(np.asarray(data).reshape(-1))
                if cooldown:
                    cooldown -= 1
                    continue
                for name, score in scores.items():
                    if score >= self.threshold:
                        cooldown = 25  # ~2 s
                        on_detect(name, float(score))
