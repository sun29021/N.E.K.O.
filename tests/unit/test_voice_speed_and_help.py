"""Fast voice replies (spoken sentence by sentence), finding files by name, honest settings help."""

import threading
import unittest
import zipfile

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.cancel import CancelToken
from neko.orchestration.coordinator import self_help
from neko.ui.live_speech import SentenceFeeder
from neko.voice.base import TextStream

TICKS = "`" * 3


class SentenceFeederTests(unittest.TestCase):
    def test_sentences_come_out_as_they_finish(self):
        f = SentenceFeeder()
        out = []
        for tok in ["Tokyo is the ", "capital of Japan. It has ", "about 14 million people", "! Want more?"]:
            out += f.feed(tok)
        self.assertEqual(out, ["Tokyo is the capital of Japan.", "It has about 14 million people!"])
        self.assertEqual(f.flush(), "Want more?")

    def test_code_is_never_read_aloud(self):
        f = SentenceFeeder()
        out = f.feed(f"Here you go.\n{TICKS}python\nprint(1)\n{TICKS}\nDone.")
        self.assertEqual(out, ["Here you go."])
        self.assertTrue(f.stopped)
        self.assertIsNone(f.flush())

    def test_markdown_is_cleaned_and_long_answers_stop(self):
        f = SentenceFeeder(max_chars=60)
        out = f.feed("## Steps\n1. **Mix** the flour.\n2. Add water slowly to the bowl.\n3. Knead it for ten minutes.\n")
        self.assertEqual(out[:2], ["Steps", "Mix the flour."])
        self.assertTrue(f.stopped)  # the rest stays on screen


class TextStreamTests(unittest.TestCase):
    def test_pieces_until_closed(self):
        s = TextStream()
        got = []
        t = threading.Thread(target=lambda: got.extend(s.pieces(CancelToken())))
        t.start()
        s.put("One.")
        s.put("Two.")
        s.close()
        t.join(3)
        self.assertEqual(got, ["One.", "Two."])

    def test_stop_ends_waiting(self):
        s, tok = TextStream(), CancelToken()
        t = threading.Thread(target=lambda: list(s.pieces(tok)))
        t.start()
        tok.cancel("stop")
        t.join(2)
        self.assertFalse(t.is_alive())


class SelfHelpTests(unittest.TestCase):
    def test_internet_help_reflects_real_setting(self):
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": False})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("how can I give you internet access")
        self.assertIn("Allow internet", r.text)
        self.assertNotIn("Allowed Apps", r.text)
        n.settings.privacy.allow_network = True
        self.assertIn("already on", self_help("hey I added the internet access in you where it gone?", n.settings)[0])
        self.assertIsNone(self_help("what's the capital of France?", n.settings))

    def test_prompt_states_facts_about_herself(self):
        p = FakeProvider(responses=["ok"])
        n = build_test_neko(temp_dir(), p, privacy={"allow_network": False})
        self.addCleanup(n.shutdown)
        n.coordinator.handle("can you read images?")
        system = p.requests[0].messages[0].content
        self.assertIn("internet access is OFF", system)
        self.assertIn("never needs internet", system)


class FindByNameTests(unittest.TestCase):
    def test_named_document_is_found_and_read(self):
        tmp = temp_dir()
        dl = tmp / "Downloads"
        (dl / "old").mkdir(parents=True)
        doc = dl / "old" / "Hisab-Manual.docx"
        with zipfile.ZipFile(doc, "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                       '2006/main"><w:body><w:p><w:r><w:t>Hisab tracks shop sales and stock.</w:t></w:r></w:p>'
                       '</w:body></w:document>')
        (dl / "holiday.docx").write_bytes(b"x")
        p = FakeProvider(responses=["It's the user guide for Hisab, a shop sales and stock tracker."])
        n = build_test_neko(tmp, p, tools={"allowed_roots": [str(dl)]})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("can you read hisab manual document and summurize it?")
        sent = "\n".join(m.content for m in p.requests[0].messages)
        self.assertIn("Hisab tracks shop sales and stock.", sent)
        self.assertIn("Hisab", r.text)

    def test_two_different_matches_ask(self):
        tmp = temp_dir()
        for sub, size in (("a", 10), ("b", 20)):
            (tmp / sub).mkdir()
            (tmp / sub / "Physics Notes.pdf").write_bytes(b"%PDF" + b"x" * size)
        n = build_test_neko(tmp, FakeProvider(), tools={"allowed_roots": [str(tmp)]})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("summarize my physics notes pdf")
        self.assertIn("more than one", r.text)


if __name__ == "__main__":
    unittest.main()


class RealConversationReplayTests(unittest.TestCase):
    """2026-10-28 live: 'Dishab Manual from the download and summarize it' -> she never searched."""

    def setUp(self):
        self.tmp = temp_dir()
        self.dl = self.tmp / "Downloads"
        self.dl.mkdir()
        with zipfile.ZipFile(self.dl / "Hisab-Manual.docx", "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                       '2006/main"><w:body><w:p><w:r><w:t>Hisab splits flat expenses.</w:t></w:r></w:p>'
                       '</w:body></w:document>')

    def test_misheard_name_and_word_order_still_find_the_file(self):
        p = FakeProvider(responses=["It's a guide to Hisab, an app that splits flat expenses."])
        n = build_test_neko(self.tmp, p, tools={"allowed_roots": [str(self.dl)]})
        self.addCleanup(n.shutdown)
        n.coordinator.handle("Dishab Manual from the download and summarize it.")
        self.assertIn("Hisab splits flat expenses.", "\n".join(m.content for m in p.requests[0].messages))

    def test_not_found_asks_then_the_answer_completes_the_request(self):
        p = FakeProvider(responses=["It explains how Hisab splits expenses."])
        n = build_test_neko(self.tmp, p, tools={"allowed_roots": [str(self.dl)]})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("summarize the zorblax manual pdf")
        self.assertIn("couldn't find", r.text)
        self.assertEqual(p.requests, [])  # asked instead of letting the model guess
        conv = n.conversations.latest_or_create()
        n.coordinator.handle("sorry, it's called Hisab, H-I-S-A-B", conversation_id=conv)
        self.assertIn("Hisab splits flat expenses.", "\n".join(m.content for m in p.requests[0].messages))


class CloudToolFormatTests(unittest.TestCase):
    def test_tool_results_are_paired_with_their_calls(self):
        from neko.core.types import ChatMessage, Role
        from neko.models.cloud import to_openai_messages

        msgs = to_openai_messages([
            ChatMessage(Role.SYSTEM, "sys"), ChatMessage(Role.USER, "open spotify"),
            ChatMessage(Role.ASSISTANT, "", tool_calls=[{"name": "open_anything", "arguments": {"target": "spotify"}}]),
            ChatMessage(Role.TOOL, "Opening Spotify", name="open_anything")])
        call = msgs[2]["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "open_anything")
        self.assertEqual(msgs[3], {"role": "tool", "tool_call_id": call["id"], "content": "Opening Spotify"})
