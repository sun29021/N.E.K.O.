import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.cancel import CancelToken
from neko.core.errors import PermissionDeniedError
from neko.core.types import Capability
from neko.models.base import ModelInfo
from neko.orchestration.coordinator import _speakable_summary, app_command, looks_like_fake_tool_use
from neko.orchestration.smart import coding_request, resolve_folder, screen_reference
from neko.security.paths import PathPolicy
from neko.tools.base import ToolContext
from neko.tools.web import _check_public, html_to_text, parse_ddg


class SmartTests(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir() / "PROJECT"
        for n in ("HISAB", "TrayDor", "MoPare by SUN", "N.E.K.O"):
            (self.root / n).mkdir(parents=True)

    def test_screen_vs_drive(self):
        self.assertTrue(screen_reference("can you tell me what the problem on this thing"))
        self.assertTrue(screen_reference("what's this error?"))
        self.assertTrue(screen_reference("what am I looking at"))
        self.assertFalse(screen_reference("what's the problem in this folder"))
        self.assertFalse(screen_reference("check this file in D drive"))
        self.assertFalse(screen_reference("tell me a joke"))

    def test_resolve_folder(self):
        roots = [str(self.root)]
        g = resolve_folder("in d drive project folder analyse my hisab project and suggest features", roots)
        self.assertTrue(g.path.endswith("HISAB"))
        self.assertTrue(resolve_folder("look at the traydor code", roots).path.endswith("TrayDor"))
        self.assertTrue(resolve_folder("review mopare by sun", roots).path.endswith("MoPare by SUN"))
        ask = resolve_folder("analyse my project in the project folder", roots)
        self.assertIsNone(ask.path)
        self.assertEqual(len(ask.candidates), 4)  # -> "which project do you mean?"
        self.assertEqual(resolve_folder(r"open D:\PROJECT\HISAB\src please", roots).path, r"D:\PROJECT\HISAB\src please")

    def test_coding_request(self):
        self.assertEqual(coding_request("analyse my hisab project and tell me which feature I can add"), (True, False))
        self.assertEqual(coding_request("fix the login bug in my traydor project"), (True, True))
        self.assertEqual(coding_request("what's the weather"), (False, False))

    def test_app_commands(self):
        self.assertEqual(app_command("Okay, I wanna close you for now. Can you shut down?")[0], "quit")
        self.assertEqual(app_command("go to sleep")[0], "quit")
        self.assertIsNone(app_command("close notepad"))
        self.assertIsNone(app_command("how do I close a file in python"))
        self.assertIsNone(app_command("shut down my computer"))  # the PC tool handles it - and asks first

    def test_fake_tool_prose_detected(self):
        self.assertTrue(looks_like_fake_tool_use("Let me check... (checking system status) Ah, all fine.", ["x"]))

    def test_speakable_summary(self):
        long = "This project is a budgeting app. It uses Python and SQLite. " + "Detail sentence here. " * 40 + "```code```"
        s = _speakable_summary(long)
        self.assertTrue(s.startswith("This project is a budgeting app."))
        self.assertIn("Command Center", s)
        self.assertLess(len(s), 520)


class WebTests(unittest.TestCase):
    def test_private_addresses_blocked(self):
        for bad in ("http://127.0.0.1:11434/api/tags", "http://localhost/x", "http://192.168.1.1/",
                    "http://10.0.0.5/", "file:///C:/Windows/win.ini", "ftp://example.com"):
            with self.assertRaises(PermissionDeniedError, msg=bad):
                _check_public(bad)

    def test_parsers(self):
        page = ('<div class="result results_links results_links_deep web-result "><div class="links_main">'
                '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa&amp;rut=x">'
                'Example <b>Title</b></a><a class="result__snippet" href="#">A <b>snippet</b>.</a></div></div>')
        r = parse_ddg(page, 5)
        self.assertEqual(r[0]["url"], "https://example.org/a")
        self.assertEqual(r[0]["title"], "Example Title")
        t, text = html_to_text("<html><title>T</title><script>evil()</script><p>Hello</p><p>World</p></html>")
        self.assertEqual(t, "T")
        self.assertNotIn("evil", text)
        self.assertIn("Hello", text)

    def test_web_tools_denied_when_network_off(self):
        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_network": False})
        self.addCleanup(n.shutdown)
        ctx = ToolContext(CancelToken(), n.paths, None, n.settings)
        r = n.executor.run("web_search", {"query": "anything"}, ctx)
        self.assertFalse(r.ok)
        self.assertIn("network access is disabled", r.summary)


class DevAndRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.proj = self.tmp / "PROJECT" / "HISAB"
        (self.proj / "src").mkdir(parents=True)
        (self.proj / "README.md").write_text("# HISAB\nA shop accounting app.", encoding="utf-8")
        (self.proj / "src" / "main.py").write_text("print('hi')", encoding="utf-8")

    def make(self, responses, models=None, **over):
        p = FakeProvider(models=models, responses=responses)
        over.setdefault("tools", {}).update({"allowed_roots": [str(self.tmp / "PROJECT")], "claude_code": False})
        n = build_test_neko(self.tmp, p, **over)
        self.addCleanup(n.shutdown)
        return n, p

    def test_analyze_project_tool(self):
        n, _ = self.make([])
        r = n.executor.run("analyze_project", {"path": str(self.proj)}, ToolContext(CancelToken(), n.paths, None, n.settings))
        self.assertTrue(r.ok, r.summary)
        self.assertIn("A shop accounting app", r.data)
        self.assertIn("Python", r.data)

    def test_project_question_uses_local_analysis_when_claude_off(self):
        n, p = self.make(["You could add monthly reports and backups."])
        r = n.coordinator.handle("analyse my hisab project and tell me which features I can add")
        self.assertEqual(r.text, "You could add monthly reports and backups.")
        joined = "\n".join(m.content for m in p.requests[0].messages)
        self.assertIn("BEGIN UNTRUSTED", joined)
        self.assertIn("A shop accounting app", joined)

    def test_ambiguous_project_asks(self):
        (self.tmp / "PROJECT" / "TrayDor").mkdir()
        n, p = self.make([])
        r = n.coordinator.handle("analyse my project and suggest features")
        self.assertIn("Which project", r.text)
        self.assertEqual(p.requests, [])

    def test_claude_code_requires_cloud_permission(self):
        n, _ = self.make([], privacy={"allow_cloud_models": False})
        r = n.executor.run("ask_claude_code", {"task": "hi", "folder": str(self.proj)},
                           ToolContext(CancelToken(), n.paths, None, n.settings))
        self.assertFalse(r.ok)

    def test_quit_command_needs_no_model(self):
        n, p = self.make([])
        r = n.coordinator.handle("okay, close yourself now")
        self.assertEqual(r.action, "quit")
        self.assertEqual(p.requests, [])

    def test_this_thing_looks_at_screen(self):
        vision = [ModelInfo("gemma3:4b", "fake", "local", {Capability.CHAT, Capability.VISION}, size_bytes=3_400_000_000)]
        n, p = self.make(["That's a 'file locked' error."], models=vision)
        n.coordinator.screen_capturer = lambda: b"PNGSCREEN"
        r = n.coordinator.handle("can you tell me what the problem on this thing")
        self.assertEqual(p.requests[0].messages[-1].images, [b"PNGSCREEN"])
        self.assertTrue(any("screen" in x for x in r.notes))

    def test_chat_still_works_during_emergency_stop(self):
        n, _ = self.make(["Still here!"])
        n.estop.trip()
        r = n.coordinator.handle("are you there?")
        self.assertEqual(r.text, "Still here!")
        ctx = ToolContext(CancelToken(), PathPolicy([str(self.tmp)], [str(self.tmp)]), None, n.settings)
        w = n.executor.run("write_note", {"path": str(self.tmp / "x.md"), "content": "x"}, ctx)
        self.assertFalse(w.ok)  # actions still blocked


if __name__ == "__main__":
    unittest.main()
