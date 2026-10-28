"""PC control: command parsing, and that risky actions always need approval (never run for real here)."""

import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.orchestration.smart import pc_command
from neko.tools import pc


class ParseTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(pc_command("open spotify"), ("open_anything", {"target": "spotify"}))
        self.assertEqual(pc_command("Neko, turn the volume up")[1], {"action": "volume_up"})
        self.assertEqual(pc_command("lock my pc")[1], {"action": "lock"})
        self.assertEqual(pc_command("unmute my PC")[1], {"action": "unmute"})
        self.assertEqual(pc_command("turn the sound on")[1], {"action": "unmute"})
        self.assertEqual(pc_command("mute")[1], {"action": "mute"})
        self.assertEqual(pc_command("shut down my computer")[1], {"action": "shutdown"})
        self.assertEqual(pc_command("cancel the shutdown")[1], {"action": "cancel_shutdown"})
        self.assertEqual(pc_command("close chrome"), ("window_control", {"name": "chrome", "action": "close"}))
        self.assertIn("q=best+biryani", pc_command("search google for best biryani")[1]["target"])
        self.assertIsNone(pc_command("close yourself"))
        self.assertIsNone(pc_command("what time is it"))
        self.assertIsNone(pc_command("go to sleep"))  # that's Neko quitting, not the PC sleeping

    def test_targets(self):
        class Ctx:
            paths = None
        self.assertEqual(pc.resolve_target("youtube", Ctx())[0:2], ("url", "https://www.youtube.com"))
        self.assertEqual(pc.resolve_target("github.com", Ctx())[1], "https://github.com")
        self.assertEqual(pc.resolve_target("bluetooth settings", Ctx())[1], "ms-settings:bluetooth")


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        old_run, old_press = pc.subprocess.run, pc._press
        self.addCleanup(setattr, pc.subprocess, "run", old_run)
        self.addCleanup(setattr, pc, "_press", old_press)
        pc.subprocess.run = lambda *a, **k: self.calls.append(("run", a[0])) or type("R", (), {"returncode": 0,
                                                                                             "stderr": ""})()
        pc._press = lambda vk, times=1: self.calls.append(("key", vk, times))

    def make(self, **tools):
        n = build_test_neko(temp_dir(), FakeProvider(), tools={"computer_control_enabled": True, **tools})
        self.addCleanup(n.shutdown)
        return n

    def test_shutdown_needs_approval_and_is_denied_without_one(self):
        n = self.make()  # tests have no approval dialog -> denied
        r = n.coordinator.handle("shut down my computer")
        self.assertIn("won't", r.text)
        self.assertEqual(self.calls, [])

    def test_shutdown_runs_only_after_approval(self):
        n = self.make()
        n.policy.set_approval_handler(lambda req: req.resolve(True))
        r = n.coordinator.handle("restart my pc")
        self.assertIn("30 seconds", r.text)
        self.assertEqual(self.calls[0][1][:2], ["shutdown.exe", "/r"])

    def test_volume_is_instant_and_needs_no_model(self):
        p = FakeProvider()
        n = build_test_neko(temp_dir(), p, tools={"computer_control_enabled": True})
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("turn the volume up")
        self.assertEqual(self.calls, [("key", 0xAF, 5)])
        self.assertEqual(p.requests, [])
        self.assertTrue(r.text.lower().startswith("volume up"))

    def test_computer_control_switch_is_respected(self):
        n = build_test_neko(temp_dir(), FakeProvider(), tools={"computer_control_enabled": False})
        self.addCleanup(n.shutdown)
        n.coordinator.handle("turn the volume up")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
