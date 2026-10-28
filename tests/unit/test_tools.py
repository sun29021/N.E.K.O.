import time
import unittest

from tests.helpers import make_settings, temp_dir

from neko.core.cancel import CancelToken, EmergencyStop
from neko.core.types import RiskLevel
from neko.database.db import Database
from neko.security.paths import PathPolicy
from neko.security.policy import PermissionPolicy
from neko.tools.base import ToolContext, ToolExecutor, ToolRegistry, ToolResult, ToolSpec, validate_args
from neko.tools.builtin import register_builtin_tools


class Harness:
    def __init__(self, approve: bool | None = None, **settings_over):
        self.tmp = temp_dir()
        (self.tmp / "work").mkdir()
        self.db = Database(":memory:")
        self.db.migrate()
        self.estop = EmergencyStop()
        self.policy = PermissionPolicy(self.db, self.estop, computer_control_enabled=False)
        self.asked = []
        if approve is not None:
            def handler(req):
                self.asked.append(req)
                req.resolve(approve)
            self.policy.set_approval_handler(handler)
        self.reg = ToolRegistry()
        register_builtin_tools(self.reg)
        self.ex = ToolExecutor(self.reg, self.policy, self.db)
        self.paths = PathPolicy([str(self.tmp / "work")], [str(self.tmp / "work")])
        self.settings = make_settings(self.tmp, **settings_over)

    def ctx(self, tainted=False):
        return ToolContext(CancelToken(), self.paths, None, self.settings, tainted=tainted)


class ValidationTests(unittest.TestCase):
    def test_schema_validation(self):
        h = Harness()
        spec = h.reg.get("list_dir")
        self.assertEqual(validate_args(spec, {"path": "x"})["limit"], 200)
        for bad in ({}, {"path": 3}, {"path": "x", "extra": 1}, {"path": "x", "limit": 0}, {"path": "a\x00b"},
                    {"path": "x", "limit": True}):
            with self.assertRaises(Exception):
                validate_args(spec, bad)

    def test_state_changing_tool_requires_verifier(self):
        reg = ToolRegistry()
        with self.assertRaises(ValueError):
            reg.register(ToolSpec("bad", "d", {}, lambda a, c: ToolResult(True, ""), RiskLevel.MATERIAL,
                                  side_effects="changes things"))


class ExecutorTests(unittest.TestCase):
    def test_read_allowed_and_logged(self):
        h = Harness()
        (h.tmp / "work" / "n.txt").write_text("hello", encoding="utf-8")
        r = h.ex.run("read_text_file", {"path": str(h.tmp / "work" / "n.txt")}, h.ctx())
        self.assertTrue(r.ok)
        self.assertEqual(r.data, "hello")
        row = h.db.one("SELECT status, args_redacted FROM tool_invocations WHERE id=?", (r.invocation_id,))
        self.assertEqual(row["status"], "succeeded")

    def test_read_outside_denied(self):
        h = Harness()
        r = h.ex.run("read_text_file", {"path": str(h.tmp / "elsewhere.txt")}, h.ctx())
        self.assertFalse(r.ok)
        self.assertIn("allowed", r.summary)

    def test_write_note_verified(self):
        h = Harness()
        target = h.tmp / "work" / "note.md"
        r = h.ex.run("write_note", {"path": str(target), "content": "# hi"}, h.ctx())
        self.assertTrue(r.ok, r.summary)
        self.assertTrue(r.verified)
        self.assertEqual(target.read_text(encoding="utf-8"), "# hi")

    def test_overwrite_escalates_and_backs_up(self):
        h = Harness(approve=True)
        target = h.tmp / "work" / "note.md"
        target.write_text("old", encoding="utf-8")
        r = h.ex.run("write_note", {"path": str(target), "content": "new", "overwrite": True}, h.ctx())
        self.assertTrue(r.ok, r.summary)
        self.assertEqual(len(h.asked), 1)  # escalated to Level 2 -> asked
        self.assertTrue(list((h.tmp / "work").glob("note.md.bak-*")))

    def test_move_needs_approval_denied(self):
        h = Harness(approve=False)
        src = h.tmp / "work" / "a.txt"
        src.write_text("x", encoding="utf-8")
        r = h.ex.run("move_file", {"source": str(src), "destination": str(h.tmp / "work" / "b.txt")}, h.ctx())
        self.assertFalse(r.ok)
        self.assertTrue(src.exists())
        self.assertEqual(h.db.one("SELECT decision FROM approvals")["decision"], "denied")

    def test_move_approved_verified(self):
        h = Harness(approve=True)
        src = h.tmp / "work" / "a.txt"
        src.write_text("x", encoding="utf-8")
        r = h.ex.run("move_file", {"source": str(src), "destination": str(h.tmp / "work" / "sub" / "b.txt")}, h.ctx())
        self.assertTrue(r.ok, r.summary)
        self.assertTrue(r.verified)

    def test_tainted_context_forces_approval_for_low_risk(self):
        h = Harness(approve=False)
        target = h.tmp / "work" / "x.md"
        r = h.ex.run("write_note", {"path": str(target), "content": "pwned"}, h.ctx(tainted=True))
        self.assertFalse(r.ok)
        self.assertFalse(target.exists())
        self.assertEqual(len(h.asked), 1)

    def test_prohibited_delete(self):
        h = Harness(approve=True)
        r = h.ex.run("delete_files", {"path": str(h.tmp / "work")}, h.ctx())
        self.assertFalse(r.ok)
        self.assertEqual(h.asked, [])
        self.assertTrue((h.tmp / "work").exists())

    def test_computer_control_disabled_by_default(self):
        h = Harness()
        r = h.ex.run("open_app", {"name": "notepad"}, h.ctx())
        self.assertFalse(r.ok)
        self.assertIn("disabled", r.summary)

    def test_script_requires_configured_dir(self):
        h = Harness(approve=True)
        r = h.ex.run("run_approved_script", {"script": "x.py"}, h.ctx())
        self.assertFalse(r.ok)

    def test_approved_script_runs_and_traversal_blocked(self):
        tmp = temp_dir()
        scripts = tmp / "scripts"
        scripts.mkdir()
        (scripts / "hello.py").write_text("import sys; print('hi', *sys.argv[1:])", encoding="utf-8")
        h = Harness(approve=True, tools={"approved_scripts_dir": str(scripts)})
        r = h.ex.run("run_approved_script", {"script": "hello.py", "args": ["there"]}, h.ctx())
        self.assertTrue(r.ok, r.summary)
        self.assertIn("hi there", r.data["stdout"])
        r2 = h.ex.run("run_approved_script", {"script": "..\\..\\evil.py"}, h.ctx())
        self.assertFalse(r2.ok)

    def test_timeout(self):
        h = Harness()
        h.reg.register(ToolSpec("slow", "slow", {}, lambda a, c: (time.sleep(2), ToolResult(True, "done"))[1],
                                RiskLevel.READ_ONLY, timeout_s=0.3))
        r = h.ex.run("slow", {}, h.ctx())
        self.assertFalse(r.ok)
        self.assertIn("timed out", r.summary)

    def test_estop_denies_side_effects(self):
        h = Harness()
        h.estop.trip()
        r = h.ex.run("write_note", {"path": str(h.tmp / "work" / "z.md"), "content": "x"}, h.ctx())
        self.assertFalse(r.ok)
        self.assertIn("emergency", r.summary)


if __name__ == "__main__":
    unittest.main()
