"""Optional ElevenLabs cloud voice. OFF by default; never required.

Privacy: every sentence N.E.K.O. speaks is sent to ElevenLabs' servers. It only works when ALL of
these are true: ``voice.tts_engine = "elevenlabs"``, ``privacy.allow_cloud_models = true``, and an
API key is stored in the environment variable named by ``voice.elevenlabs_key_env`` (never in a file).
Free plan (checked 2026-10-27): 10,000 credits/month, commercial use apparently not included.
Kokoro is the free, local default.

API: POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_22050
header ``xi-api-key``; returns raw 16-bit PCM at 22.05 kHz.
"""

from __future__ import annotations

import http.client
import json
import os

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .tts import clean_for_speech


class ElevenLabsSynthesizer:
    def __init__(self, voice_id: str, key_env: str = "ELEVENLABS_API_KEY", cloud_allowed: bool = False,
                 model_id: str = "eleven_flash_v2_5", volume: float = 0.9) -> None:
        self.voice_id = voice_id
        self.key_env = key_env
        self.cloud_allowed = cloud_allowed
        self.model_id = model_id
        self.volume = volume

    def available(self) -> tuple[bool, str]:
        if not self.cloud_allowed:
            return False, "cloud services are disabled (privacy.allow_cloud_models = false)"
        if not os.environ.get(self.key_env):
            return False, f"no ElevenLabs API key in environment variable {self.key_env}"
        if not self.voice_id:
            return False, "voice.elevenlabs_voice_id is empty"
        return True, "ElevenLabs cloud voice (text leaves this computer)"

    def speak(self, text: str, token: CancelToken) -> None:
        import numpy as np
        import sounddevice as sd

        ok, why = self.available()
        if not ok:
            raise PeripheralUnavailableError(why, user_message=f"ElevenLabs voice is not available: {why}.")
        text = clean_for_speech(text)
        if not text:
            return
        conn = http.client.HTTPSConnection("api.elevenlabs.io", timeout=30)
        token.on_cancel(conn.close)
        try:
            conn.request("POST", f"/v1/text-to-speech/{self.voice_id}?output_format=pcm_22050",
                         body=json.dumps({"text": text, "model_id": self.model_id}).encode(),
                         headers={"xi-api-key": os.environ[self.key_env], "Content-Type": "application/json"})
            r = conn.getresponse()
            data = r.read()
            if r.status >= 400:
                raise PeripheralUnavailableError(f"ElevenLabs HTTP {r.status}: {data[:200]!r}",
                                                 user_message=f"ElevenLabs refused the request (HTTP {r.status}).")
        except OSError as exc:
            if token.cancelled:
                return
            raise PeripheralUnavailableError(str(exc), user_message="Couldn't reach ElevenLabs.") from exc
        finally:
            conn.close()
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0 * self.volume
        sd.play(audio, 22050)
        token.wait(len(audio) / 22050)
        sd.stop()
