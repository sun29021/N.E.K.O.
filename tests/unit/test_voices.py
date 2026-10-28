"""Natural voices: language/gender choice, word timings for subtitles, voice & language commands."""

import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.configuration.settings import load_settings, update_user_setting
from neko.core import events as ev
from neko.orchestration.smart import voice_command
from neko.voice.playback import estimate_words
from neko.voice.tts_edge import EdgeSynthesizer, language_of


class VoiceChoiceTests(unittest.TestCase):
    def test_language_and_gender_pick_the_voice(self):
        self.assertEqual(language_of("Hello there, how are you?"), "en")
        self.assertEqual(language_of("আমি নেকো, তুমি কেমন আছো?"), "bn")
        f, m = EdgeSynthesizer("female"), EdgeSynthesizer("male")
        self.assertEqual(f.voice_for("Hi"), "en-US-AvaMultilingualNeural")
        self.assertEqual(m.voice_for("Hi"), "en-US-AndrewMultilingualNeural")
        self.assertEqual(f.voice_for("আমি ভালো"), "bn-BD-NabanitaNeural")
        self.assertEqual(m.voice_for("আমি ভালো"), "bn-BD-PradeepNeural")

    def test_estimated_word_times_are_ordered_and_inside_the_audio(self):
        words = estimate_words("Okay, playing Believer now.", 1.6)
        self.assertEqual([w for w, _t in words], ["Okay,", "playing", "Believer", "now."])
        times = [t for _w, t in words]
        self.assertEqual(times, sorted(times))
        self.assertLess(times[-1], 1.6)

    def test_offline_falls_back_and_never_fakes_bangla(self):
        import numpy as np

        from neko.core.cancel import CancelToken
        from neko.voice.playback import Utterance

        said = []

        class Kokoro:
            on_level = None

            def utterances(self, text, emotion, token):
                said.append(text)
                yield Utterance(np.zeros(10, dtype=np.float32), [])

        e = EdgeSynthesizer("female", fallback=Kokoro())
        e.synthesize_piece = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
        list(e.pieces("Hello there. আমি ভালো আছি।", "neutral", CancelToken()))
        self.assertEqual(said[0], "Hello there.")
        self.assertIn("internet to speak Bangla", said[1])


class CommandTests(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(voice_command("use a male voice"), ("gender", "male"))
        self.assertEqual(voice_command("switch to female voice"), ("gender", "female"))
        self.assertEqual(voice_command("speak in bangla"), ("language", "bn"))
        self.assertEqual(voice_command("bangla te kotha bolo"), ("language", "bn"))
        self.assertEqual(voice_command("বাংলায় বলো"), ("language", "bn"))
        self.assertEqual(voice_command("speak english please"), ("language", "en"))
        self.assertIsNone(voice_command("who is the best female singer"))
        self.assertIsNone(voice_command("translate this to bangla"))

    def test_switch_applies_now_and_tells_the_ui(self):
        p = FakeProvider(responses=["ok"])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        seen = []
        n.bus.subscribe(ev.SETTINGS, lambda e: seen.append(dict(e.payload)))
        r = n.coordinator.handle("use a male voice")
        self.assertEqual(n.settings.voice.gender, "male")
        self.assertEqual(seen[-1]["gender"], "male")
        self.assertIn("male voice", r.text)
        n.coordinator.handle("speak in bangla")
        self.assertEqual((n.settings.app.reply_language, n.settings.voice.stt_language), ("bn", ""))
        n.coordinator.handle("what's the capital of Japan?")
        self.assertIn("ALWAYS reply in natural, everyday Bangla", p.requests[-1].messages[0].content)
        self.assertEqual(len(p.requests), 1)  # the switches themselves needed no model

    def test_update_one_setting_keeps_the_rest(self):
        d = temp_dir()
        cfg = d / "config.toml"
        cfg.write_text('config_version = 1\n[app]\nuser_name = "sun"\n[voice]\nkokoro_speed = 0.92\n', encoding="utf-8")
        update_user_setting("voice", "gender", "male", cfg)
        s = load_settings(cfg)
        self.assertEqual((s.voice.gender, s.voice.kokoro_speed, s.app.user_name), ("male", 0.92, "sun"))


if __name__ == "__main__":
    unittest.main()


class BargeInTests(unittest.TestCase):
    def test_only_her_name_interrupts(self):
        from neko.voice.listener import DEFAULT_NAMES, barge_in_command, build_name_pattern

        p = build_name_pattern(DEFAULT_NAMES)
        self.assertIsNone(barge_in_command("The capital of Japan is Tokyo.", p))   # her own echo
        self.assertEqual(barge_in_command("Neko, stop!", p), "")
        self.assertEqual(barge_in_command("Nico wait", p), "")
        self.assertEqual(barge_in_command("Neko, wait, what time is it?", p), "what time is it?")
        self.assertEqual(barge_in_command("Neko play Believer instead", p), "play Believer instead")
