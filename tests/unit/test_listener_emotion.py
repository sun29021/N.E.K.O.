import math
import struct
import time
import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core import events as ev
from neko.core.emotion import looks_like_tag_prefix, split_emotion, strip_emoji
from neko.voice.base import Transcript
from neko.voice.listener import DEFAULT_NAMES, EnergyVAD, WakeNameListener, build_name_pattern, split_wake


class WakeNameTests(unittest.TestCase):
    def setUp(self):
        self.p = build_name_pattern(DEFAULT_NAMES)

    def test_split(self):
        self.assertEqual(split_wake("Neko, what time is it?", self.p), (True, "what time is it?"))
        self.assertEqual(split_wake("Hey Nico open notepad", self.p), (True, "open notepad"))
        self.assertEqual(split_wake("What's the weather, Neko?", self.p), (True, "What's the weather"))
        self.assertEqual(split_wake("Neko.", self.p), (True, ""))
        self.assertEqual(split_wake("I watched a movie yesterday", self.p)[0], False)
        self.assertEqual(split_wake("necktie shopping", self.p)[0], False)  # whole words only


class FakeSTT:
    def __init__(self, texts):
        self.texts = list(texts)

    def transcribe(self, pcm, sr, *, language=None, token=None, hotwords=None):
        return Transcript(self.texts.pop(0), "en", 1.0)


class ListenerTests(unittest.TestCase):
    def make(self, texts):
        self.commands, self.wakes = [], []
        return WakeNameListener(FakeSTT(texts), on_command=self.commands.append,
                                on_wake=lambda: self.wakes.append(1), follow_up_s=5)

    def test_name_required_then_follow_up(self):
        lst = self.make(["just chatting with a friend", "Neko, how much RAM is free?", "and the disk?"])
        self.assertIsNone(lst.handle_utterance(b"x"))           # no name: ignored
        self.assertEqual(lst.handle_utterance(b"x"), "how much RAM is free?")
        self.assertIsNone(lst.handle_utterance(b"x"))           # follow-up window not armed yet
        lst.texts = None
        lst2 = self.make(["and the disk?"])
        lst2.arm_follow_up()                                    # armed after she answered
        self.assertEqual(lst2.handle_utterance(b"x"), "and the disk?")
        self.assertEqual(self.commands, ["and the disk?"])

    def test_name_alone_waits_for_command(self):
        lst = self.make(["Neko!", "tell me a joke"])
        lst.handle_utterance(b"x")
        self.assertEqual(len(self.wakes), 1)
        self.assertEqual(lst.handle_utterance(b"x"), "tell me a joke")

    def test_unfinished_sentence_is_joined(self):
        lst = self.make(["Neko, can you just show me the last time when...", "I asked about the weather?"])
        self.assertIsNone(lst.handle_utterance(b"x"))  # sounds cut off -> waits
        self.assertEqual(lst.handle_utterance(b"x"),
                         "can you just show me the last time when I asked about the weather?")

    def test_unfinished_sentence_sent_after_timeout(self):
        lst = self.make(["Neko, tell me about the"])
        lst.handle_utterance(b"x")
        lst._pending_until = 0
        self.assertEqual(lst.flush_pending(), "tell me about the")

    def test_timings_are_configurable(self):
        lst = WakeNameListener(FakeSTT(["Neko, can you tell me about the"]), on_command=lambda c: None,
                               wait_rest_s=6.0, pause_s=1.6, addressed_pause_s=2.5, max_speech_s=60.0)
        lst.handle_utterance(b"x")
        self.assertAlmostEqual(lst._pending_until - time.monotonic(), 6.0, delta=0.3)
        self.assertTrue(lst.addressed)

    def test_early_end_only_for_complete_requests(self):
        lst = self.make([])
        self.assertIsNotNone(lst.end_check("Neko, what time is it?"))
        self.assertIsNotNone(lst.end_check("Neko, play Believer."))
        self.assertIsNone(lst.end_check("Neko, can you tell me about the"))     # sounds unfinished
        self.assertIsNone(lst.end_check("I watched a movie yesterday."))        # not meant for her
        self.assertEqual(lst.caption_for("Neko, play some"), "play some")
        self.assertIsNone(lst.caption_for("just chatting here"))

    def test_continuing_right_after_an_early_end_revises_the_request(self):
        revised = []
        lst = WakeNameListener(FakeSTT(["Dhaka tomorrow?"]), on_command=self.commands.append if hasattr(self, "commands") else None,
                               on_revise=revised.append)
        self.commands = []
        lst.on_command = self.commands.append
        lst.handle_utterance(b"x", "Neko, tell me the weather?", early=True)
        lst.handle_utterance(b"x", started_at=time.monotonic())
        self.assertEqual(self.commands, ["tell me the weather?"])
        self.assertEqual(revised, ["tell me the weather Dhaka tomorrow?"])

    def test_follow_up_expires(self):
        lst = self.make(["what about tomorrow"])
        lst.arm_follow_up(0.01)
        time.sleep(0.05)
        self.assertIsNone(lst.handle_utterance(b"x"))


def tone(seconds, amp):
    n = int(16000 * seconds)
    return struct.pack(f"<{n}h", *(int(amp * math.sin(i / 8)) for i in range(n)))


class VADTests(unittest.TestCase):
    def feed(self, vad, pcm):
        out = []
        for i in range(0, len(pcm), 960):
            frame = pcm[i:i + 960]
            if len(frame) < 960:
                break
            vals = struct.unpack(f"<{len(frame) // 2}h", frame)
            rms = math.sqrt(sum(v * v for v in vals) / len(vals))
            r = vad.feed(frame, rms)
            if r:
                out.append(r)
        return out

    def test_detects_one_utterance_and_ignores_quiet(self):
        vad = EnergyVAD()
        quiet, speech = tone(1.0, 60), tone(1.2, 5000)
        self.assertEqual(self.feed(vad, quiet), [])
        got = self.feed(vad, quiet + speech + tone(2.0, 60))  # end-of-speech needs 1.3 s of quiet now
        self.assertEqual(len(got), 1)
        self.assertGreater(len(got[0]) / 32000, 1.0)

    def test_click_is_too_short(self):
        vad = EnergyVAD()
        self.assertEqual(self.feed(vad, tone(0.5, 60) + tone(0.12, 6000) + tone(2.0, 60)), [])

    def test_short_pause_does_not_end_utterance(self):
        vad = EnergyVAD()
        speech = tone(0.8, 5000)
        got = self.feed(vad, tone(0.5, 60) + speech + tone(0.9, 60) + speech + tone(2.0, 60))
        self.assertEqual(len(got), 1)  # a 0.9 s thinking pause stays inside one sentence

    def test_long_pause_while_addressed(self):
        vad = EnergyVAD(max_speech_s=60.0)
        vad.end_frames = int(2.5 / 0.03)  # what the listener uses while she is being talked to
        speech = tone(0.8, 5000)
        got = self.feed(vad, tone(0.5, 60) + speech + tone(2.1, 60) + speech + tone(3.0, 60))
        self.assertEqual(len(got), 1)  # a 2.1 s pause to think no longer splits the request


class EmotionTests(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(split_emotion("[happy] Hi there!"), ("happy", "Hi there!"))
        self.assertEqual(split_emotion("No tag here"), ("neutral", "No tag here"))
        self.assertEqual(split_emotion("[angry] unknown tag stays"), ("neutral", "[angry] unknown tag stays"))
        self.assertTrue(looks_like_tag_prefix("[hap"))
        self.assertFalse(looks_like_tag_prefix("[happy]"))
        self.assertFalse(looks_like_tag_prefix("[1] first item"))
        self.assertEqual(strip_emoji("Hi 😊 there ✨"), "Hi  there ")
        # bare-word style that llama3.2 actually produced in live testing
        self.assertEqual(split_emotion("happy! That's amazing news!"), ("happy", "That's amazing news!"))
        self.assertEqual(split_emotion("Calm. The capital of Japan is Tokyo."), ("calm", "The capital of Japan is Tokyo."))
        self.assertEqual(split_emotion("(sad) Sorry to hear that."), ("sad", "Sorry to hear that."))
        self.assertEqual(split_emotion("Happy birthday to you!"), ("neutral", "Happy birthday to you!"))
        self.assertEqual(split_emotion("Caring I'm so sorry to hear that."), ("caring", "I'm so sorry to hear that."))
        self.assertEqual(split_emotion("Calm Mm-hm, it's Tokyo."), ("calm", "Mm-hm, it's Tokyo."))
        self.assertEqual(split_emotion("Happy New Year to you!"), ("neutral", "Happy New Year to you!"))
        self.assertEqual(split_emotion("happy Oh my goodness!"), ("happy", "Oh my goodness!"))
        self.assertEqual(split_emotion("calm Mm-hm, that's Tokyo."), ("calm", "Mm-hm, that's Tokyo."))
        from neko.core.emotion import infer_emotion, resolve_emotion

        self.assertEqual(resolve_emotion("caring", "Congratulations, that's amazing!"), "excited")
        self.assertEqual(resolve_emotion("neutral", "Aw, sorry to hear that. I'm here to listen."), "caring")
        self.assertEqual(resolve_emotion("calm", "The capital is Tokyo."), "calm")
        self.assertEqual(infer_emotion("What would you like to do?"), "curious")
        from neko.core.emotion import strip_inline_tags

        self.assertEqual(strip_inline_tags("Let me search again. [caring] Okay, I found it."),
                         "Let me search again. Okay, I found it.")
        self.assertEqual(strip_inline_tags("See item [1] here"), "See item [1] here")
        self.assertTrue(looks_like_tag_prefix("happy!"))
        self.assertTrue(looks_like_tag_prefix("cal"))
        self.assertFalse(looks_like_tag_prefix("Hello"))

    def test_bare_word_tag_hidden_while_streaming(self):
        n = build_test_neko(temp_dir(), FakeProvider(responses=["happy! That's amazing news!"]))
        self.addCleanup(n.shutdown)
        tokens = []
        n.bus.subscribe(ev.TOKEN, lambda e: tokens.append(e.payload["text"]))
        r = n.coordinator.handle("I passed my exam")
        self.assertEqual((r.emotion, r.text), ("happy", "That's amazing news!"))
        self.assertNotIn("happy", "".join(tokens).lower())

    def test_tag_hidden_from_stream_and_reply(self):
        tmp = temp_dir()
        n = build_test_neko(tmp, FakeProvider(responses=["[excited] Oh! That's wonderful news!"]))
        self.addCleanup(n.shutdown)
        tokens = []
        n.bus.subscribe(ev.TOKEN, lambda e: tokens.append(e.payload["text"]))
        r = n.coordinator.handle("I passed my exam today")
        self.assertEqual(r.emotion, "excited")
        self.assertEqual(r.text, "Oh! That's wonderful news!")
        self.assertNotIn("[", "".join(tokens))
        self.assertEqual("".join(tokens).strip(), r.text)

    def test_expressive_prompt_toggle(self):
        tmp = temp_dir()
        p = FakeProvider(responses=["ok", "ok"])
        n = build_test_neko(tmp, p, voice={"expressive": True})
        self.addCleanup(n.shutdown)
        n.coordinator.handle("hello there friend")
        self.assertIn("emotion tag", p.requests[0].messages[0].content)
        p2 = FakeProvider(responses=["ok"])
        n2 = build_test_neko(temp_dir(), p2, voice={"expressive": False})
        self.addCleanup(n2.shutdown)
        n2.coordinator.handle("hello there friend")
        self.assertNotIn("emotion tag", p2.requests[0].messages[0].content)


if __name__ == "__main__":
    unittest.main()
