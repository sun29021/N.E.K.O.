"""0.5.0: 'show me' side panel, reading documents, study notes, two-lane multitasking, orb fade."""

import os
import threading
import time
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko import documents
from neko.core import events as ev
from neko.core.errors import ToolError
from neko.orchestration.smart import (document_request, is_long_job, pick_named_file, visual_request,
                                      visual_topic)

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


class SmartTests(unittest.TestCase):
    def test_visual_requests(self):
        self.assertEqual(visual_request("Can you show me how a jet engine works?"), "show")
        self.assertEqual(visual_request("what does a black hole look like"), "show")
        self.assertEqual(visual_request("show me again"), "again")
        self.assertEqual(visual_request("open the panel again"), "again")
        self.assertEqual(visual_request("what is the capital of France"), "")
        self.assertEqual(visual_request("show me what is on my screen"), "")  # that's the screen, not a panel
        self.assertEqual(visual_topic("show me a picture of the Eiffel Tower"), "Eiffel Tower")
        self.assertEqual(visual_topic("Can you show me how a jet engine works?"), "jet engine")

    def test_document_requests(self):
        self.assertEqual(document_request("hey can you tell me whats this file"), (True, False, ""))
        about, study, _ = document_request("can you analysis this pdf I have exam tomorrow based on that, and "
                                           "can you make a simpler 3/4 page of easy to read pdf and cheat sheet")
        self.assertTrue(about and study)
        self.assertEqual(document_request(r"summarize E:\JOB Materials\Suite.pdf")[2], r"E:\JOB Materials\Suite.pdf")
        self.assertFalse(document_request("what's the weather tomorrow")[0])
        self.assertFalse(document_request("analyse my HISAB project")[0])
        self.assertEqual(pick_named_file("notes from the physics pdf", [r"D:\a\Physics Ch3.pdf", r"D:\a\Chem.pdf"]),
                         [r"D:\a\Physics Ch3.pdf"])

    def test_long_jobs(self):
        self.assertTrue(is_long_job("in D drive project folder analyse my HISAB project"))
        self.assertTrue(is_long_job("make me a cheat sheet from this pdf for my exam"))
        self.assertFalse(is_long_job("what time is it?"))


def _office(path: Path, member: str, xml: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, xml)
    return path


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


class DocumentTests(unittest.TestCase):
    def test_extract_docx_pptx_txt(self):
        tmp = temp_dir()
        docx = _office(tmp / "a.docx", "word/document.xml",
                       f'<w:document {W}><w:body><w:p><w:r><w:t>Cells are </w:t></w:r><w:r><w:t>small.</w:t>'
                       '</w:r></w:p><w:p><w:r><w:t>DNA lives in the nucleus.</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(documents.extract_text(docx)[0], "Cells are small.\nDNA lives in the nucleus.")
        pptx = _office(tmp / "s.pptx", "ppt/slides/slide1.xml",
                       f'<p:sld xmlns:p="x" {A}><a:p><a:r><a:t>Photosynthesis</a:t></a:r></a:p></p:sld>')
        text, slides = documents.extract_text(pptx)
        self.assertEqual((slides, text), (1, "[slide 1]\nPhotosynthesis"))
        (tmp / "n.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(documents.extract_text(tmp / "n.txt")[0], "hello")
        (tmp / "x.exe").write_bytes(b"MZ\x00\x00")
        with self.assertRaises(ToolError):
            documents.extract_text(tmp / "x.exe")

    def test_make_pdf_is_verified_and_needs_renderer(self):
        tmp = temp_dir()
        n = build_test_neko(tmp, FakeProvider(), tools={"writable_roots": [str(tmp)]})
        self.addCleanup(n.shutdown)
        from neko.core.cancel import CancelToken
        from neko.tools.base import ToolContext

        ctx = ToolContext(token=CancelToken(), paths=n.coordinator.paths, settings=n.settings)
        args = {"path": str(tmp / "out.pdf"), "title": "T", "markdown": "# hi"}
        old = documents.pdf_renderer
        self.addCleanup(setattr, documents, "pdf_renderer", old)
        documents.pdf_renderer = None
        self.assertFalse(n.coordinator.executor.run("make_pdf", args, ctx).ok)
        documents.pdf_renderer = lambda md, title, out: out.write_bytes(b"%PDF-1.4\n" + b"x" * 600)
        res = n.coordinator.executor.run("make_pdf", args, ctx)
        self.assertTrue(res.ok and res.verified)
        args["path"] = str(tmp / "out.txt")
        self.assertFalse(n.coordinator.executor.run("make_pdf", args, ctx).ok)  # PDFs only


class CoordinatorV05Tests(unittest.TestCase):
    def test_show_me_opens_panel_and_show_again_reuses_it(self):
        tmp = temp_dir()
        p = FakeProvider(responses=["A jet engine pushes air out fast to move forward.\n\n## Steps\n1. Suck\n"
                                    "2. Squeeze\n3. Bang\n4. Blow"])
        n = build_test_neko(tmp, p)
        self.addCleanup(n.shutdown)
        seen = []
        n.bus.subscribe(ev.VISUAL, lambda e: seen.append(dict(e.payload)))
        r = n.coordinator.handle("Can you show me how a jet engine works?")
        self.assertIn("VISUAL PANEL", p.requests[0].messages[0].content)
        self.assertEqual(len(seen), 1)
        self.assertIn("## Steps", seen[0]["markdown"])
        self.assertTrue(r.speech.startswith("A jet engine pushes air out fast"))
        self.assertIn("panel", r.speech)
        r2 = n.coordinator.handle("show me again")
        self.assertEqual(len(p.requests), 1)  # no model call needed
        self.assertEqual(len(seen), 2)
        self.assertIn("again", r2.text)

    def test_visual_answer_drops_filler_and_speaks_the_answer(self):
        p = FakeProvider(responses=["I can try to explain, but I'm not a scientist, okay?\n1. Sunlight bends "
                                    "inside raindrops.\n2. The colours split apart."])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("show me how a rainbow forms")
        self.assertTrue(r.text.startswith("1. Sunlight"))
        self.assertTrue(r.speech.startswith("Sunlight bends inside raindrops."))

    def test_this_file_reads_explorer_selection(self):
        tmp = temp_dir()
        f = tmp / "lecture.txt"
        f.write_text("Mitochondria are the powerhouse of the cell.", encoding="utf-8")
        p = FakeProvider(responses=["It's a short biology note about mitochondria."])
        n = build_test_neko(tmp, p, tools={"allowed_roots": [str(tmp)]})
        self.addCleanup(n.shutdown)
        n.coordinator.explorer = lambda: [{"folder": str(tmp), "selected": [str(f)]}]
        r = n.coordinator.handle("hey can you tell me what's this file?")
        sent = "\n".join(m.content for m in p.requests[0].messages)
        self.assertIn("powerhouse of the cell", sent)
        self.assertIn("lecture.txt", sent)
        self.assertIn("mitochondria", r.text)

    def test_this_file_without_explorer_asks(self):
        n = build_test_neko(temp_dir(), FakeProvider())
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("what's in this pdf?")
        self.assertIn("Which file", r.text)

    def test_several_files_asks_which(self):
        tmp = temp_dir()
        for name in ("Physics.pdf", "Chemistry.pdf"):
            (tmp / name).write_bytes(b"%PDF-1.4")
        n = build_test_neko(tmp, FakeProvider(), tools={"allowed_roots": [str(tmp)]})
        self.addCleanup(n.shutdown)
        n.coordinator.explorer = lambda: [{"folder": str(tmp), "selected": []}]
        r = n.coordinator.handle("summarise this pdf for me")
        self.assertIn("Which one", r.text)
        self.assertIn("Physics.pdf", r.text)

    def test_study_notes_and_cheat_sheet_pdfs(self):
        tmp = temp_dir()
        src = tmp / "docs"
        src.mkdir()
        f = src / "Biology Ch1.txt"
        f.write_text("Cells are the basic unit of life. " * 40, encoding="utf-8")
        p = FakeProvider(responses=["- cells are basic units", "## Cells\n**Cell**: unit of life",
                                    "## Cheat\n- cell = unit of life"])
        n = build_test_neko(tmp, p, tools={"allowed_roots": [str(src)], "writable_roots": [str(tmp / "notes")],
                                           "claude_code": False})
        self.addCleanup(n.shutdown)
        old = documents.pdf_renderer
        self.addCleanup(setattr, documents, "pdf_renderer", old)
        documents.pdf_renderer = lambda md, title, out: out.write_bytes(b"%PDF-1.4\n" + md.encode() + b" " * 600)
        n.coordinator.explorer = lambda: [{"folder": str(src), "selected": [str(f)]}]
        seen = []
        n.bus.subscribe(ev.VISUAL, lambda e: seen.append(dict(e.payload)))
        r = n.coordinator.handle("I have an exam tomorrow, make simpler notes and a cheat sheet from this file")
        made = sorted(os.listdir(tmp / "notes" / "Study"))
        self.assertEqual(made, ["Biology Ch1 - cheat sheet.pdf", "Biology Ch1 - study notes.pdf"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]["files"]), 2)
        self.assertIn("cell = unit of life", seen[0]["markdown"])
        self.assertIn("Good luck", r.speech)
        for req in p.requests:  # the document only ever reaches the model fenced as untrusted
            self.assertNotIn("Cells are the basic unit of life. Cells", req.messages[0].content)
        r2 = n.coordinator.handle("I have an exam tomorrow, make simpler notes and a cheat sheet from this file")
        self.assertIn("Biology Ch1 - study notes (2).pdf", os.listdir(tmp / "notes" / "Study"))  # never overwrites
        self.assertTrue(r2.succeeded)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QtV05Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def test_orb_fades_when_idle_and_returns_on_activity(self):
        from neko.core.types import AssistantState
        from neko.ui.orb_window import OrbWindow

        w = OrbWindow(always_on_top=False, opacity=0.9, reduced_motion=True, name="Neko", idle_hide_s=1)
        self.addCleanup(w.deleteLater)
        w.show()
        self.pump(2.6)
        self.assertFalse(w.isVisible())
        w.set_state(AssistantState.LISTENING, "")
        self.pump(0.9)
        self.assertTrue(w.isVisible())
        self.assertAlmostEqual(w.windowOpacity(), 0.9, places=1)

    def test_orb_does_not_vanish_while_busy(self):
        from neko.core.types import AssistantState
        from neko.ui.orb_window import OrbWindow

        w = OrbWindow(always_on_top=False, opacity=0.9, reduced_motion=True, name="Neko", idle_hide_s=1)
        self.addCleanup(w.deleteLater)
        w.show()
        w.set_state(AssistantState.THINKING, "")
        self.pump(1.6)
        self.assertTrue(w.isVisible())

    def test_bridge_two_lanes_and_queue(self):
        from neko.ui.bridge import UiBridge

        n = build_test_neko(temp_dir(), FakeProvider())
        self.addCleanup(n.shutdown)
        gate = threading.Event()
        started = []

        def handle(text, **kw):
            started.append(text)
            gate.wait(5)
            from neko.orchestration.coordinator import Reply

            return Reply(text, "t", "c")

        n.coordinator.handle = handle
        b = UiBridge(n)
        replies = []
        b.reply.connect(replies.append)
        self.assertEqual(b.send("analyse my HISAB project in D drive"), "started")   # long job
        self.assertEqual(b.send("what time is it?"), "parallel")                     # chat beside it
        self.assertEqual(b.send("and the date?"), "queued")                          # waits its turn
        self.assertTrue(b.foreground_busy)
        gate.set()
        deadline = time.monotonic() + 5
        while len(replies) < 3 and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(sorted(started), sorted(["analyse my HISAB project in D drive", "what time is it?",
                                                  "and the date?"]))
        self.assertEqual(len(replies), 3)
        self.assertFalse(b.is_busy)

    def test_panel_shows_and_closes_itself(self):
        from neko.ui.visual_panel import VisualPanel

        p = VisualPanel(always_on_top=False, close_after_s=1)
        self.addCleanup(p.deleteLater)
        p.show_visual({"title": "Jet engine", "markdown": "## Steps\n1. a", "files": ["D:\\x - cheat sheet.pdf"]})
        self.pump(0.6)
        self.assertTrue(p.isVisible())
        self.assertEqual(p.title.text(), "Jet engine")
        self.assertEqual(p.buttons.count(), 2)  # "Open cheat sheet PDF" + stretch
        self.pump(1.8)
        self.assertFalse(p.isVisible())


if __name__ == "__main__":
    unittest.main()
