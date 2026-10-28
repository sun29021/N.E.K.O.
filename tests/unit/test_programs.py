"""Your own programs: found only in the projects folder, added with approval, run with approval (or an
approved standing rule), output returned, background apps tracked and stopped. Uses a temp projects folder."""

import sys
import time
import unittest
from pathlib import Path

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko import programs


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir()
        (self.root / "Reporter").mkdir()
        (self.root / "Reporter" / "main.py").write_text(
            '"""Makes the daily sales report."""\nimport sys\nprint("report for", " ".join(sys.argv[1:]) or "today")\n')
        (self.root / "Waiter").mkdir()
        (self.root / "Waiter" / "app.py").write_text("import time\ntime.sleep(60)\n")
        (self.root / "Web").mkdir()
        (self.root / "Web" / "package.json").write_text('{"description": "shop site", "scripts": {"web": "vite --port 5999"}}')
        self.n = build_test_neko(temp_dir(), FakeProvider(), tools={"programs_root": str(self.root)})
        self.addCleanup(self.n.shutdown)
        self.asked = []
        self.n.policy.set_approval_handler(lambda req: (self.asked.append(req.tool), req.resolve(True)))
        self.old_py = programs._python_for
        programs._python_for = lambda script, root: [sys.executable]   # the test machine's Python
        self.addCleanup(setattr, programs, "_python_for", self.old_py)

    def say(self, text):
        return self.n.coordinator.handle(text).text

    def test_list_learn_run(self):
        listing = self.say("what programs do I have?")
        self.assertIn("Reporter (python", listing)
        self.assertIn("Web (npm", listing)
        r = self.say("learn to use reporter")
        self.assertIn("Learned Reporter", r)
        self.assertIn("daily sales report", r)            # from the docstring, without running it
        r = self.say("run reporter with monday")
        self.assertIn("report for monday", r)
        self.assertEqual(self.asked, ["register_program", "run_program"])   # each asked you

    def test_learn_by_exact_path(self):
        (self.root / "Reporter" / "other.py").write_text('print("other one")\n')
        self.assertIn("Learned Reporter (other.py)", self.say(f"learn to use {self.root / 'Reporter' / 'other.py'}"))
        self.assertIn("other one", self.say("run reporter"))
        self.assertIn("only run your programs", self.say(r"learn to use C:\Windows\System32\cmd.exe"))

    def test_always_allow_makes_a_narrow_rule(self):
        self.say("learn to use reporter")
        self.say("always allow reporter")
        self.asked.clear()
        self.assertIn("report for today", self.say("run reporter"))
        self.assertEqual(self.asked, [])                  # covered by the standing rule for this one program

    def test_denied_run_does_nothing(self):
        self.say("learn to use reporter")
        self.n.policy.set_approval_handler(lambda req: req.resolve(False))
        self.assertNotIn("report for", self.say("run reporter"))

    def test_outside_the_projects_folder_is_refused(self):
        with self.assertRaises(Exception):
            programs.command_for({"name": "x", "kind": "exe", "path": r"C:\Windows\System32\cmd.exe"}, [],
                                 self.n.settings)

    def test_unknown_names_pass_through(self):
        self.assertIsNone(programs.Programs(self.n.settings).find("spotify"))
        self.assertNotIn("Started", self.say("open spotify"))

    def test_background_program_starts_and_stops(self):
        (self.root / "Waiter" / "app.py").write_text("import tkinter  # gui\nimport time\ntime.sleep(60)\n")
        self.say("learn to use waiter")
        self.assertIn("Started Waiter", self.say("start waiter"))
        self.assertIn("already running", self.say("start waiter"))
        self.assertIn("Stopped Waiter", self.say("stop waiter"))
        time.sleep(0.5)
        self.assertNotIn("Waiter", [k for k, p in programs._running.items() if p.poll() is None])

    def test_default_folder_on_a_one_drive_pc(self):
        from types import SimpleNamespace as N
        from unittest import mock

        no_setting = N(tools=N(programs_root=""))
        with mock.patch.object(programs.Path, "exists", lambda self: str(self) != "D:\\"):
            self.assertEqual(str(programs.projects_root(no_setting)), "C:\\PROJECT")
        with mock.patch.object(programs.Path, "exists", lambda self: True):
            self.assertEqual(str(programs.projects_root(no_setting)), "D:\\PROJECT")

    def test_npm_url_guess(self):
        web = [c for c in programs.candidates(self.n.settings) if c["kind"] == "npm"][0]
        self.assertEqual((web["script"], web["url"]), ("web", "http://localhost:5999"))
        self.assertTrue(Path(programs.command_for(web, [], self.n.settings)[0][0]).name.lower().startswith("npm"))


if __name__ == "__main__":
    unittest.main()
