"""Free cloud brains next to the local model: preferred when available, local takes over on failure."""

import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.errors import ModelUnavailableError
from neko.core.types import Capability
from neko.models.base import ModelInfo
from neko.models.cloud import CLOUDS, CloudProvider, read_key, save_keys


class FakeCloud(FakeProvider):
    def __init__(self, family="groq", fail=False, **kw):
        caps = {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.TOOLS}
        super().__init__(models=[ModelInfo(f"{family}-big", f"cloud:{family}", f"cloud:{family}", caps,
                                           context_length=8000 if family == "groq" else 200_000, family=family)],
                         location=f"cloud:{family}", **kw)
        self.id = f"cloud:{family}"
        self.fail = fail

    def chat_stream(self, req, token):
        if self.fail:
            self.requests.append(req)
            self._last = None
            raise ModelUnavailableError("HTTP 429: free limit", user_message="free limit reached")
        yield from super().chat_stream(req, token)


def make(local, *clouds, **over):
    n = build_test_neko(temp_dir(), local, privacy={"allow_cloud_models": True}, **over)
    n.router.providers.extend(clouds)
    n.router.allow_remote = True
    n.router.cloud_first = True
    n.router.refresh(force=True)
    return n


class CloudRoutingTests(unittest.TestCase):
    def test_cloud_brain_answers_when_available(self):
        local, cloud = FakeProvider(responses=["local"]), FakeCloud(responses=["Paris, of course."])
        n = make(local, cloud)
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("what is the capital of France?")
        self.assertEqual((r.text, r.location), ("Paris, of course.", "cloud:groq"))
        self.assertEqual(local.requests, [])

    def test_free_limit_falls_back_to_local_in_the_same_turn(self):
        local, cloud = FakeProvider(responses=["Paris."]), FakeCloud(fail=True)
        n = make(local, cloud)
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("what is the capital of France?")
        self.assertEqual((r.text, r.location), ("Paris.", "local"))
        self.assertTrue(n.router.resting("groq-big"))
        self.assertIn("answered locally", " ".join(r.notes))
        n.coordinator.handle("and of Spain?")  # while resting, local answers without trying the cloud
        self.assertEqual(len(cloud.requests), 1)

    def test_sensitive_requests_stay_local(self):
        local, cloud = FakeProvider(responses=["ok"]), FakeCloud(responses=["cloud"])
        n = make(local, cloud)
        self.addCleanup(n.shutdown)
        n.coordinator.handle("my password is hunter2, can you remember my bank pin 1234?")
        self.assertEqual(cloud.requests, [])

    def test_deep_thinking_prefers_gemini(self):
        local, groq, gem = FakeProvider(), FakeCloud(responses=["g"]), FakeCloud("gemini", responses=["deep answer"])
        n = make(local, groq, gem)
        self.addCleanup(n.shutdown)
        r = n.coordinator.handle("think carefully about how to plan my week of exam study")
        self.assertEqual(r.location, "cloud:gemini")


class KeyTests(unittest.TestCase):
    def test_keys_saved_privately_and_read_back(self):
        d = temp_dir()
        spec = CLOUDS["groq"]
        self.assertEqual(read_key(spec, d), "")
        save_keys(d, {"groq_key": "gsk_test123"})
        self.assertEqual(read_key(spec, d), "gsk_test123")
        save_keys(d, {"gemini_key": "AIza-test"})  # adding one keeps the other
        self.assertEqual(read_key(spec, d), "gsk_test123")

    def test_no_key_means_no_cloud_model(self):
        self.assertEqual(CloudProvider(CLOUDS["gemini"], temp_dir()).list_models(), [])


if __name__ == "__main__":
    unittest.main()


class SelfUpgradeTests(unittest.TestCase):
    def test_upgrade_goes_to_claude_code_on_her_own_project_with_edits(self):
        from neko.orchestration import coordinator as coord
        from neko.tools.base import ToolResult

        n = build_test_neko(temp_dir(), FakeProvider(), privacy={"allow_cloud_models": True},
                            tools={"claude_code": True})
        self.addCleanup(n.shutdown)
        old = coord.find_claude
        self.addCleanup(setattr, coord, "find_claude", old)
        coord.find_claude = lambda: "claude.exe"
        calls = []
        n.coordinator.executor.run = lambda tool, args, ctx: calls.append((tool, args)) or ToolResult(
            True, "done", {"answer": "I added Excel reading and its tests. Restart me to use it."})
        r = n.coordinator.handle("upgrade yourself so you can read Excel files")
        tool, args = calls[0]
        self.assertEqual(tool, "ask_claude_code")
        self.assertTrue(args["allow_edits"])                       # Level 2: the approval dialog asks you
        from pathlib import Path
        self.assertEqual(Path(args["folder"]), Path(coord.__file__).resolve().parents[3])  # her own folder, wherever installed
        self.assertIn("AGENTS.md", args["task"])
        self.assertIn("Restart", r.text)

    def test_without_claude_code_she_says_what_is_needed(self):
        n = build_test_neko(temp_dir(), FakeProvider(), tools={"claude_code": False})
        self.addCleanup(n.shutdown)
        self.assertIn("Claude Code", n.coordinator.handle("upgrade yourself to read Excel files").text)


class OfficeGpuTests(unittest.TestCase):
    def test_office_models_preferred_and_address_rules(self):
        from neko.models.office import is_tailnet_or_private

        self.assertTrue(is_tailnet_or_private("http://100.93.5.96:11434"))
        self.assertTrue(is_tailnet_or_private("http://office-pc:11434"))
        self.assertTrue(is_tailnet_or_private("http://office-pc.tail7f4ce9.ts.net:11434"))
        self.assertTrue(is_tailnet_or_private("http://192.168.1.20:11434"))
        self.assertFalse(is_tailnet_or_private("http://8.8.8.8:11434"))
        self.assertFalse(is_tailnet_or_private("http://evil.example.com:11434"))

    def test_office_gpu_answers_when_online(self):
        local = FakeProvider(responses=["local"])
        office = FakeProvider(models=[ModelInfo("qwen3:14b", "ollama-office", "lan:office", {Capability.CHAT})],
                              location="lan:office", responses=["from the office GPU"])
        n = build_test_neko(temp_dir(), local)
        self.addCleanup(n.shutdown)
        n.router.providers.append(office)
        n.router.allow_remote = True
        n.router.refresh(force=True)
        r = n.coordinator.handle("explain photosynthesis simply")
        self.assertEqual((r.text, r.location), ("from the office GPU", "lan:office"))
        self.assertEqual(local.requests, [])
    def test_laptop_picks_the_offices_best_model(self):
        from neko.core.types import TaskKind

        office = FakeProvider(models=[ModelInfo(m, "ollama-office", "lan:office", {Capability.CHAT})
                                      for m in ("qwen3:4b", "llama3.2:3b", "qwen3:32b", "qwen3:14b")],
                              location="lan:office")
        n = build_test_neko(temp_dir(), FakeProvider())
        self.addCleanup(n.shutdown)
        n.router.providers.append(office)
        n.router.allow_remote = True
        n.router.refresh(force=True)
        d = n.router.route(TaskKind.QUESTION, n.monitor.snapshot())
        self.assertEqual((d.model.name, d.model.location), ("qwen3:32b", "lan:office"))
