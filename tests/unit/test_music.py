"""'Neko, play <song>': request parsing, routing through verified tools, and the Qt player."""

import math
import os
import struct
import time
import unittest
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko import media
from neko.orchestration.smart import music_request

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


class ParseTests(unittest.TestCase):
    def test_requests(self):
        self.assertEqual(music_request("Neko, play Blinding Lights by The Weeknd"), ("play", "Blinding Lights by The Weeknd"))
        self.assertEqual(music_request("play shape of you on youtube please"), ("play", "shape of you"))
        self.assertEqual(music_request("play the song Believer by Imagine Dragons"), ("play", "Believer by Imagine Dragons"))
        self.assertEqual(music_request("can you play some music"), ("ask", ""))
        self.assertEqual(music_request("pause the music"), ("pause", ""))
        self.assertEqual(music_request("turn it up"), ("louder", ""))
        self.assertEqual(music_request("stop the music"), ("stop", ""))
        self.assertEqual(music_request("let's play a game"), ("", ""))
        self.assertEqual(music_request("what time is it"), ("", ""))


class MusicListeningTests(unittest.TestCase):
    """While music plays, a bare 'pause' works without her name, but lyrics don't become commands."""

    def make(self, texts, playing=True):
        from neko.ui.voice_controller import music_shortcut
        from neko.voice.base import Transcript
        from neko.voice.listener import WakeNameListener

        class STT:
            def __init__(self, t):
                self.t = list(t)

            def transcribe(self, pcm, sr, *, language=None, token=None, hotwords=None):
                return Transcript(self.t.pop(0), "en", 1.0)

        self.sent = []
        return WakeNameListener(STT(texts), on_command=self.sent.append, music_active=lambda: playing,
                                direct_command=music_shortcut)

    def test_bare_commands_during_music(self):
        lst = self.make(["Pause.", "stop", "turn it up"])
        for _ in range(3):
            lst.handle_utterance(b"x")
        self.assertEqual(self.sent, ["pause", "stop the music", "turn it up"])

    def test_lyrics_are_ignored_even_right_after_she_spoke(self):
        lst = self.make(["I want to break free", "stop and stare at the sky tonight"])
        lst.arm_follow_up()  # she just said "Playing ..."
        lst.handle_utterance(b"x")
        lst.handle_utterance(b"x")
        self.assertEqual(self.sent, [])

    def test_without_music_pause_still_needs_her_name(self):
        lst = self.make(["pause", "Neko, pause"], playing=False)
        lst.handle_utterance(b"x")
        lst.handle_utterance(b"x")
        self.assertEqual(self.sent, ["pause"])
        self.assertEqual(len(self.sent), 1)


class FakePlayer:
    def __init__(self):
        self.state, self.title, self.calls = "stopped", "", []

    def play(self, url, title):
        self.calls.append(("play", url))
        self.state, self.title = "playing", title

    def control(self, action):
        self.calls.append((action,))
        self.state = {"pause": "paused", "resume": "playing", "stop": "stopped"}.get(action, self.state)

    def status(self):
        return {"state": self.state, "title": self.title}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.player = FakePlayer()
        old_player, old_find = media.player, media.find_songs
        self.addCleanup(setattr, media, "player", old_player)
        self.addCleanup(setattr, media, "find_songs", old_find)
        media.player = self.player
        media.find_songs = lambda q, timeout_s=20.0, n=5: [{"title": f"{q} (Official Audio)", "url": "https://x/a.m4a",
                                                      "page": "https://youtube.com/watch?v=1", "duration": 200,
                                                      "channel": "c"}]

    def test_play_pause_stop_without_the_model(self):
        p = FakeProvider()
        n = build_test_neko(temp_dir(), p, privacy={"allow_network": True})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("Neko, play Blinding Lights")
        self.assertEqual(r.text, "Playing Blinding Lights (Official Audio).")
        self.assertEqual(self.player.calls[0], ("play", "https://x/a.m4a"))
        self.assertEqual(n.coordinator.handle("pause the music").text, "Paused.")
        self.assertEqual(self.player.state, "paused")
        self.assertEqual(n.coordinator.handle("stop the music").text, "Music off.")
        self.assertEqual(p.requests, [])  # none of this needed the language model

    def test_muted_pc_is_unmuted_for_music(self):
        old = media.prepare_sound
        self.addCleanup(setattr, media, "prepare_sound", old)
        media.prepare_sound = lambda: "unmuted your PC's sound and turned the volume up to 25%"
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": True})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("play Believer")
        self.assertIn("Playing Believer", r.text)
        self.assertIn("Your sound was off, so I unmuted", r.text)

    def test_play_next_from_youtube_up_next(self):
        import time as _t

        for name in ("related_songs", "_stream", "_current"):
            self.addCleanup(setattr, media, name, getattr(media, name))
        self.addCleanup(media._queue.clear)
        self.addCleanup(media._played.clear)
        media._queue.clear()
        media._played.clear()
        media.find_songs = lambda q, timeout_s=20.0, n=5: [{"title": "Casa (Official)", "url": "https://x/1.m4a",
                                                           "page": "p", "duration": 200, "channel": "c", "id": "v1"}]
        media.related_songs = lambda vid, timeout_s=20.0, n=25: [
            {"id": x, "title": f"Song {x}", "duration": 200} for x in ("v2", "v3") if x not in media._played]
        media._stream = lambda vid, timeout_s=20.0: {"title": f"Song {vid}", "url": f"https://x/{vid}.m4a", "page": "",
                                                    "duration": 200, "channel": "c", "id": vid}
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": True})
        self.addCleanup(n.shutdown)
        self.assertIn("Casa", n.coordinator.handle("play casa casa").text)
        _t.sleep(0.2)  # the up-next list is fetched in the background
        self.assertEqual(n.coordinator.handle("play next").text, "Playing Song v2.")
        self.assertEqual(self.player.calls[-1], ("play", "https://x/v2.m4a"))
        self.assertEqual(n.coordinator.handle("skip").text, "Playing Song v3.")
        self.player.state = "stopped"          # the song ended by itself: "next" still works (autoplay path)
        self.assertTrue(media.has_up_next())
    def test_tests_never_touch_the_real_speakers(self):
        self.assertIsNone(media.prepare_sound)  # only the desktop app plugs it in
    def test_volume_words_are_chat_when_nothing_plays(self):
        p = FakeProvider(responses=["Sure, I'll speak up!"])
        n = build_test_neko(temp_dir(), p, privacy={"allow_network": True})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("louder please")
        self.assertEqual(len(p.requests), 1)
        self.assertNotIn(("louder",), self.player.calls)
        self.assertIn("speak up", r.text)

    def test_needs_internet(self):
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": False})
        self.addCleanup(n.shutdown)
        self.assertIn("internet", n.coordinator.handle("play Believer").text)
        self.assertEqual(self.player.calls, [])

    def test_play_unverified_is_reported(self):
        class Silent(FakePlayer):
            def play(self, url, title):
                self.state = "error"

            def status(self):
                return {"state": "error", "error": "network"}

        media.player = Silent()
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": True})
        self.addCleanup(n.shutdown)
        self.assertIn("wouldn't play", n.coordinator.handle("play Believer").text)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QtPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, player, state, seconds=6.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            if player.status()["state"] == state:
                return True
            time.sleep(0.02)
        return False

    def test_local_file_plays_pauses_stops_and_ducks(self):
        from PySide6.QtCore import QUrl

        from neko.ui.music_player import DUCK, MusicPlayer

        path = temp_dir() / "tone.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"".join(struct.pack("<h", int(800 * math.sin(i / 9))) for i in range(16000 * 4)))
        mp = MusicPlayer(volume=0.0)  # silent: tests must not make noise
        self.addCleanup(mp.shutdown)
        mp.play(QUrl.fromLocalFile(str(path)).toString(), "Test tone")
        self.assertTrue(self.wait_for(mp, "playing"))
        self.assertEqual(mp.status()["title"], "Test tone")
        mp.control("pause")
        self.assertTrue(self.wait_for(mp, "paused"))
        mp.control("resume")
        self.assertTrue(self.wait_for(mp, "playing"))
        mp._volume = 0.8
        mp.duck(True)
        self.wait_for(mp, "never", 0.2)
        self.assertAlmostEqual(mp._out.volume(), 0.8 * DUCK, places=2)
        mp.duck(False)
        self.wait_for(mp, "never", 0.2)
        self.assertAlmostEqual(mp._out.volume(), 0.8, places=2)
        mp.control("stop")
        self.assertTrue(self.wait_for(mp, "stopped"))


if __name__ == "__main__":
    unittest.main()
