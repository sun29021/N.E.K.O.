"""Neural core simulation and voice-engine selection (Qt runs offscreen; skipped without PySide6)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.helpers import make_settings, temp_dir

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # core-only environments
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class NeuralCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self):
        from neko.ui.orb import CoreOrb

        o = CoreOrb(reduced_motion=True, size=150)
        o.resize(150, 150)
        return o

    def test_network_is_connected_to_core(self):
        o = self.make()
        self.assertEqual(len(o._core_links), 16)
        self.assertTrue(all(len(a) >= 1 for a in o._adj[: o.CORE]))

    def test_signals_travel_fire_and_settle(self):
        from neko.core.types import AssistantState as S

        o = self.make()
        o.set_state(S.THINKING)
        o.stimulate(1.0, "core")
        self.assertGreater(len(o._pulses), 0)
        self.assertGreater(o._act[o.CORE], 0.3)
        peak = 0.0
        for _ in range(40):
            o._advance(0.042)
            peak = max(peak, max(o._act[: o.CORE]))
        self.assertGreater(peak, 0.2)  # shell neurons fired when signals arrived
        o.set_state(S.OFFLINE)  # no spontaneous activity
        for _ in range(200):
            o._advance(0.083)
        self.assertEqual(o._pulses, [])
        self.assertLess(max(o._act), 0.01)

    def test_pulse_count_is_bounded(self):
        o = self.make()
        for _ in range(500):
            o.stimulate(1.2, "core")
            o._advance(0.01)
        self.assertLess(len(o._pulses), 260)

    def test_renders_every_state(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QImage, QPainter

        from neko.core.types import AssistantState

        o = self.make()
        img = QImage(150, 150, QImage.Format.Format_ARGB32)
        for st in AssistantState:
            o.set_state(st)
            o.stimulate(0.8, "core")
            o._advance(0.1)
            p = QPainter(img)
            o.render(p, QPoint(0, 0))
            p.end()


class VoiceSelectionTests(unittest.TestCase):
    def test_kokoro_missing_files_falls_back_to_sapi(self):
        from neko.voice.tts import SapiSynthesizer, build_synthesizer

        s = make_settings(temp_dir(), voice={"tts_engine": "kokoro", "kokoro_dir": str(temp_dir())})
        self.assertIsInstance(build_synthesizer(s.voice), SapiSynthesizer)

    def test_elevenlabs_requires_cloud_permission_and_key(self):
        from neko.voice.tts import SapiSynthesizer, build_synthesizer
        from neko.voice.tts_elevenlabs import ElevenLabsSynthesizer

        s = make_settings(temp_dir(), voice={"tts_engine": "elevenlabs", "elevenlabs_voice_id": "abc",
                                             "elevenlabs_key_env": "NEKO_TEST_NO_SUCH_KEY"})
        synth = build_synthesizer(s.voice, cloud_allowed=True)
        self.assertFalse(synth.primary.available()[0])  # no key -> ElevenLabs never used, local voice speaks
        self.assertNotIsInstance(synth.fallback, ElevenLabsSynthesizer)
        self.assertIsNotNone(SapiSynthesizer)
        os.environ["NEKO_TEST_KEY"] = "x"
        try:
            ok, _ = ElevenLabsSynthesizer("abc", "NEKO_TEST_KEY", cloud_allowed=False).available()
            self.assertFalse(ok)  # cloud disabled -> never used, even with a key
            ok, _ = ElevenLabsSynthesizer("abc", "NEKO_TEST_KEY", cloud_allowed=True).available()
            self.assertTrue(ok)
        finally:
            del os.environ["NEKO_TEST_KEY"]

    def test_settings_validation(self):
        from neko.configuration.settings import settings_from_dict
        from neko.core.errors import ConfigError

        for bad in ({"ui": {"theme": "pink"}}, {"voice": {"tts_engine": "robot"}}, {"voice": {"kokoro_speed": 5.0}}):
            with self.assertRaises(ConfigError):
                settings_from_dict(bad)
        self.assertEqual(settings_from_dict({}).ui.theme, "aurum")


if __name__ == "__main__":
    unittest.main()
