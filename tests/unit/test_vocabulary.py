"""Personal vocabulary for speech recognition, the 'learn the word' command, and song ranking."""

import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.media import _song_score
from neko.orchestration.coordinator import learn_request
from neko.voice.vocabulary import MAX_PROMPT_CHARS, Vocabulary


class VocabularyTests(unittest.TestCase):
    def test_prompt_lists_names_learned_words_and_projects(self):
        tmp = temp_dir()
        (tmp / "projects" / "HISAB").mkdir(parents=True)
        v = Vocabulary(tmp / "vocabulary.txt", seed=["Dhaka", "Bangla song"], folders=[str(tmp / "projects")],
                       names=["Neko", "sun"])
        v.add("Oporadhi")
        p = v.prompt()
        self.assertTrue(p.startswith("Neko. Words I use:"))
        for w in ("sun", "Oporadhi", "Dhaka", "Bangla song", "HISAB"):
            self.assertIn(w, p)
        self.assertLess(p.index("Oporadhi"), p.index("Dhaka"))  # learned words come first

    def test_add_is_clean_and_deduplicated(self):
        v = Vocabulary(temp_dir() / "v.txt")
        self.assertEqual(v.add('  "Arman Alif"!! '), "Arman Alif")
        v.add("arman alif")
        self.assertEqual(v.learned(), ["Arman Alif"])
        self.assertEqual(v.add("?"), "")

    def test_prompt_stays_short(self):
        v = Vocabulary(temp_dir() / "v.txt", seed=[f"Word{i}" for i in range(300)], names=["Neko"])
        self.assertLessEqual(len(v.prompt()), MAX_PROMPT_CHARS + 2)


class SpeechFallbackTests(unittest.TestCase):
    def test_gpu_failure_falls_back_to_small_on_cpu(self):
        import sys
        import types

        from neko.voice.stt_whisper import FasterWhisperRecognizer

        made = []

        class FakeModel:
            def __init__(self, name, device, compute_type, download_root=None, local_files_only=True):
                if device == "cuda":
                    raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                made.append((name, device, compute_type, download_root))

        fake = types.ModuleType("faster_whisper")
        fake.WhisperModel = FakeModel
        old = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = fake
        self.addCleanup(lambda: sys.modules.__setitem__("faster_whisper", old) if old else sys.modules.pop("faster_whisper"))
        r = FasterWhisperRecognizer("large-v3-turbo", "cuda", "int8", download_root=r"D:\models")
        r._load()
        self.assertEqual(made, [("small", "cpu", "int8", None)])
        self.assertEqual((r.device, r.model_name), ("cpu", "small"))


class LearnCommandTests(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(learn_request("learn the word Oporadhi"), "Oporadhi")
        self.assertEqual(learn_request("can you learn the name Arman Alif"), "Arman Alif")
        self.assertEqual(learn_request("add Tahsan to your vocabulary"), "Tahsan")
        self.assertIsNone(learn_request("add milk to the shopping list"))
        self.assertIsNone(learn_request("remember that I like tea"))

    def test_learning_writes_the_word_list_without_the_model(self):
        tmp = temp_dir()
        p = FakeProvider()
        n = build_test_neko(tmp, p)
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("Neko, learn the word Oporadhi")
        self.assertIn("Oporadhi", r.text)
        self.assertIn("Oporadhi", (n.settings.data_dir / "vocabulary.txt").read_text(encoding="utf-8"))
        self.assertEqual(p.requests, [])


class SongRankingTests(unittest.TestCase):
    def test_real_song_beats_lecture_and_reaction(self):
        lecture = {"title": "Conservatory Winter Term Opera (World Premiere)", "categories": ["Education"],
                   "duration": 182}
        reaction = {"title": "Oporadhi Reply | BOYS vs GIRLS reaction", "categories": ["People & Blogs"],
                    "duration": 358}
        song = {"title": "Arman Alif | Oporadhi | Bengali Song", "categories": ["Music"], "duration": 330}
        ranked = sorted([(0, lecture), (1, reaction), (2, song)], key=lambda ie: _song_score(ie[1], ie[0]),
                        reverse=True)
        self.assertIs(ranked[0][1], song)


if __name__ == "__main__":
    unittest.main()
