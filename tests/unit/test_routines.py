"""Reminders (time parsing, storage, firing) and learned skills (save, replay, approvals re-asked)."""

import time
import unittest
from datetime import datetime

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.cancel import CancelToken
from neko.core.types import RiskLevel
from neko.routines import parse_reminder
from neko.tools.base import ToolContext, ToolResult, ToolSpec

NOW = datetime(2026, 10, 28, 14, 0)


class ParseTests(unittest.TestCase):
    def test_times(self):
        cases = {
            "remind me at 6 to call Ammu": (datetime(2026, 10, 28, 18, 0), "call Ammu"),
            "Neko, remind me in 20 minutes to check the rice": (datetime(2026, 10, 28, 14, 20), "check the rice"),
            "remind me tomorrow at 9 to pay the bill": (datetime(2026, 10, 29, 9, 0), "pay the bill"),
            "remind me to call 2 people at 6:30 pm": (datetime(2026, 10, 28, 18, 30), "call 2 people"),
            "remind me to drink water in half an hour": (datetime(2026, 10, 28, 14, 30), "drink water"),
            "set a reminder for 7am tomorrow to go gym": (datetime(2026, 10, 29, 7, 0), "go gym"),
            "remind me tonight at 10 to lock the door": (datetime(2026, 10, 28, 22, 0), "lock the door"),
            "remind me at 11 to sleep": (datetime(2026, 10, 28, 23, 0), "sleep"),
        }
        for text, want in cases.items():
            self.assertEqual(parse_reminder(text, NOW), want, text)
        self.assertEqual(parse_reminder("remind me to buy milk", NOW), (None, "buy milk"))
        self.assertIsNone(parse_reminder("what is the time", NOW))
        self.assertIsNone(parse_reminder("I remember you", NOW))


class Base(unittest.TestCase):
    def setUp(self):
        self.neko = build_test_neko(temp_dir(), FakeProvider(), tools={"computer_control_enabled": True})
        self.addCleanup(self.neko.shutdown)
        self.r = self.neko.routines
        self.conv = self.neko.conversations.create()


class ReminderTests(Base):
    def test_set_list_fire_cancel(self):
        reply = self.neko.coordinator.handle("remind me in 1 seconds to stretch", conversation_id=self.conv)
        self.assertIn("stretch", reply.text)
        self.assertEqual(len(self.r.pending_reminders()), 1)
        self.assertIn("stretch", self.neko.coordinator.handle("what are my reminders?").text)
        self.assertEqual(self.r.due_now(time.time() - 60), [])  # not yet
        due = self.r.due_now(time.time() + 5)
        self.assertEqual([d["text"] for d in due], ["stretch"])
        self.assertEqual(self.r.due_now(time.time() + 5), [])  # fires once
        self.neko.coordinator.handle("remind me tomorrow at 9 to pay the bill", conversation_id=self.conv)
        self.assertIn("cancelled 1", self.neko.coordinator.handle("cancel my reminders").text)

    def test_asks_when_time_missing(self):
        reply = self.neko.coordinator.handle("remind me to buy milk", conversation_id=self.conv)
        self.assertIn("When", reply.text)
        self.assertEqual(self.r.pending_reminders(), [])


class SkillTests(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        for name, risk in (("test_step", RiskLevel.LOW), ("test_material", RiskLevel.MATERIAL)):
            self.neko.tools.register(ToolSpec(
                name=name, description="test", params={"what": {"type": "string", "required": True}},
                handler=lambda a, c, n=name: self.calls.append((n, a["what"])) or ToolResult(True, "ok", {}),
                risk=risk, side_effects="test", verifier=lambda a, r, c: (True, "ok")))

    def _do(self, tool, what):
        task = self.neko.tasks.create("do it", "chat", self.conv)
        ctx = ToolContext(token=CancelToken(), paths=self.neko.paths, task_id=task.id, settings=self.neko.settings)
        return self.neko.executor.run(tool, {"what": what}, ctx)

    def test_save_and_replay(self):
        self._do("test_step", "one")
        self._do("test_step", "two")
        reply = self.neko.coordinator.handle("save that as morning setup", conversation_id=self.conv)
        self.assertIn("2 steps", reply.text)
        self.calls.clear()
        reply = self.neko.coordinator.handle("do the morning setup", conversation_id=self.conv)
        self.assertIn("all 2 steps", reply.text)
        self.assertEqual(self.calls, [("test_step", "one"), ("test_step", "two")])
        self.assertIn("morning setup", self.neko.coordinator.handle("what skills do you know?").text)
        self.assertIn("Forgot", self.neko.coordinator.handle("forget the skill morning setup").text)
        self.assertEqual(self.r.skills(), [])

    def test_replay_asks_for_approval_again(self):
        self.neko.policy.set_approval_handler(lambda req: req.resolve(True))
        self._do("test_material", "move file")
        self.neko.coordinator.handle("save that as tidy", conversation_id=self.conv)
        asked = []
        self.neko.policy.set_approval_handler(lambda req: (asked.append(req.tool), req.resolve(False)))
        self.calls.clear()
        reply = self.neko.coordinator.handle("run the tidy skill", conversation_id=self.conv)
        self.assertEqual(asked, ["test_material"])     # a skill can never skip an approval
        self.assertEqual(self.calls, [])
        self.assertIn("stopped", reply.text)

    def test_nothing_to_save_and_no_hijack(self):
        self.assertIn("don't have any recent actions",
                      self.neko.coordinator.handle("save that as nothing", conversation_id=self.conv).text)
        self.assertIsNone(self.r.match_skill("open spotify"))
        self.assertIsNone(self.r.match_skill("remember that I like tea"))


if __name__ == "__main__":
    unittest.main()
