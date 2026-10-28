"""Brain map graph + tool armory statuses (+ the Qt views render offscreen)."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.types import Trust
from neko.diagnostics.armory import armory
from neko.memory.brain import build_brain
from neko.orchestration.coordinator import app_command

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


def neko_with_memories():
    n = build_test_neko(temp_dir(), FakeProvider())
    n.memory.add("Sun's exam is physics chapter 3", kind="fact", trust=Trust.USER_STATED, source_type="t",
                 tags=["study"], require_approval=False)
    n.memory.add("Physics notes are in Downloads", kind="fact", trust=Trust.USER_STATED, source_type="t",
                 tags=["study"], require_approval=False)
    n.memory.add("my bank pin is 1234", kind="fact", trust=Trust.USER_STATED, source_type="t", sensitive=True,
                 require_approval=False)
    return n


class BrainTests(unittest.TestCase):
    def test_graph_connects_everything_to_the_core(self):
        n = neko_with_memories()
        self.addCleanup(n.shutdown)
        g = build_brain(n)
        self.assertIn("core", g.nodes)
        self.assertIn("topic:study", g.nodes)                     # shared tag ties the two memories
        study = g.neighbours("topic:study")
        self.assertEqual(sum(1 for x in study if x.startswith("mem:")), 2)
        self.assertTrue(any(k.startswith("tool:") for k in g.nodes))
        self.assertTrue(all("1234" not in node.detail for node in g.nodes.values()))  # sensitive text hidden

    def test_voice_opens_brain_and_armory(self):
        self.assertEqual(app_command("show me your brain")[0], "open_brain")
        self.assertEqual(app_command("open your tool armory")[0], "open_armory")
        self.assertIsNone(app_command("show me a picture of the brain"))


class ArmoryTests(unittest.TestCase):
    def test_statuses_are_honest(self):
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": False, "allow_cloud_models": True},
                            tools={"computer_control_enabled": False})
        self.addCleanup(n.shutdown)
        items = {i.name: i for i in armory(n)}
        self.assertEqual(items["Groq"].status, "needs key")
        self.assertEqual(items["web search"].status, "off")         # internet off
        self.assertEqual(items["pc control"].status, "off")         # computer control off
        self.assertEqual(items["Local models"].status, "connected")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_build_and_select(self):
        from neko.ui.armory_view import ArmoryWindow
        from neko.ui.brain_view import BrainWindow

        n = neko_with_memories()
        self.addCleanup(n.shutdown)
        w = BrainWindow(n)
        self.addCleanup(w.deleteLater)
        w.show()
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            self.app.processEvents()
        self.assertGreater(len(w.canvas.ids), 20)
        w.canvas.select("topic:study")
        self.assertGreater(w.links.count(), 1)
        w.search.setText("physics")
        self.assertTrue(w.canvas.matches)
        a = ArmoryWindow(n)
        self.addCleanup(a.deleteLater)
        self.assertIn("ready", a.title.text())


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class StartHiddenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_started_with_windows_stays_hidden_until_her_name(self):
        from neko.core.types import AssistantState
        from neko.ui.orb_window import OrbWindow

        w = OrbWindow(always_on_top=False, opacity=0.9, reduced_motion=True, name="Neko", idle_hide_s=240)
        self.addCleanup(w.deleteLater)
        w.start_hidden()
        self.app.processEvents()
        self.assertFalse(w.isVisible())
        w.set_state(AssistantState.IDLE, "")           # background chatter / idle: stays hidden
        self.assertFalse(w.isVisible())
        w.set_state(AssistantState.LISTENING, "")      # "Neko" -> she appears
        end = time.monotonic() + 0.9
        while time.monotonic() < end:
            self.app.processEvents()
        self.assertTrue(w.isVisible())
