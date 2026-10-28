import unittest

from tests.helpers import FakeProvider

from neko.core.types import Capability, TaskKind
from neko.database.db import Database
from neko.models.base import ModelInfo
from neko.models.profiles import get_profile
from neko.models.router import ModelLifecycle, ModelRouter, same_model
from neko.resources.monitor import ResourceSnapshot, assess

GB = 1_000_000_000


def snap(ram_free=8000, vram_total=4096, vram_used=500):
    return ResourceSnapshot(ram_total_mb=16000, ram_free_mb=ram_free, vram_total_mb=vram_total,
                            vram_used_mb=vram_used, on_battery=False)


def m(name, caps, size_gb, loaded=False, location="local"):
    return ModelInfo(name, "fake", location, set(caps), size_bytes=int(size_gb * GB), loaded=loaded)


class RouterTests(unittest.TestCase):
    def make(self, models, **kw):
        db = Database(":memory:")
        db.migrate()
        return ModelRouter([FakeProvider(models)], get_profile("laptop-lite"), db, **kw), db

    def test_prefers_profile_order_and_logs(self):
        r, db = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0), m("qwen3:4b", [Capability.CHAT], 2.5)])
        d = r.route(TaskKind.QUESTION, snap())
        self.assertEqual(d.model.name, "llama3.2:3b")
        self.assertEqual(db.one("SELECT chosen FROM routing_decisions")["chosen"], "llama3.2:3b")
        d2 = r.route(TaskKind.PLANNING, snap())
        self.assertEqual(d2.model.name, "llama3.2:3b")  # everyday planning: the faster model
        d3 = r.route(TaskKind.PLANNING, snap(), deep=True)
        self.assertEqual((d3.role, d3.model.name), ("deep", "qwen3:4b"))

    def test_not_installed_candidates_explained(self):
        r, _ = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0)])
        d = r.route(TaskKind.CODING, snap())
        self.assertEqual(d.model.name, "llama3.2:3b")
        reasons = {c.model: c.rejected for c in d.candidates}
        self.assertEqual(reasons["qwen2.5-coder:1.5b"], "not installed")

    def test_vision_without_model_returns_none(self):
        r, _ = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0)])
        d = r.route(TaskKind.VISION, snap())
        self.assertIsNone(d.model)
        self.assertIn("no installed vision model", d.reason)

    def test_memory_pressure_rejects_big_model(self):
        r, _ = self.make([m("qwen3:4b", [Capability.CHAT], 2.5), m("llama3.2:3b", [Capability.CHAT], 2.0)])
        d = r.route(TaskKind.PLANNING, snap(ram_free=2500, vram_used=3800))
        # 2500 - 2048 margin = 452 MB RAM usable, almost no VRAM -> neither fits
        self.assertIsNone(d.model)
        self.assertTrue(all(c.rejected for c in d.candidates if c.model in ("qwen3:4b", "llama3.2:3b")))

    def test_loaded_model_preferred_and_needs_no_memory(self):
        r, _ = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0, loaded=True), m("qwen3:4b", [Capability.CHAT], 2.5)])
        d = r.route(TaskKind.PLANNING, snap(ram_free=2500, vram_used=3800))
        self.assertEqual(d.model.name, "llama3.2:3b")

    def test_partial_offload_warns(self):
        r, _ = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0)])
        d = r.route(TaskKind.QUESTION, snap(vram_used=3000))
        self.assertEqual(d.gpu_fit, "partial")
        self.assertIn("slower", d.slow_warning)

    def test_remote_disabled_and_sensitive_stays_local(self):
        r, _ = self.make([m("qwen3:8b", [Capability.CHAT], 5.2, location="lan:desktop")])
        self.assertIsNone(r.route(TaskKind.QUESTION, snap()).model)
        r2, _ = self.make([m("qwen3:8b", [Capability.CHAT], 5.2, location="lan:desktop")], allow_remote=True)
        self.assertEqual(r2.route(TaskKind.QUESTION, snap()).model.name, "qwen3:8b")
        self.assertIsNone(r2.route(TaskKind.QUESTION, snap(), sensitive=True).model)

    def test_override(self):
        r, _ = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0), m("qwen3:4b", [Capability.CHAT], 2.5)])
        r.override = "qwen3:4b"
        self.assertEqual(r.route(TaskKind.SMALL_TALK, snap()).model.name, "qwen3:4b")

    def test_poor_success_rate_penalised(self):
        r, db = self.make([m("llama3.2:3b", [Capability.CHAT], 2.0), m("qwen3:4b", [Capability.CHAT], 2.5)])
        for _ in range(6):
            db.execute("INSERT INTO routing_decisions(task_kind, chosen, candidates, reason, succeeded, created_at) "
                       "VALUES ('question','llama3.2:3b','[]','x',0,0)")
        self.assertEqual(r.route(TaskKind.QUESTION, snap()).model.name, "qwen3:4b")

    def test_same_model(self):
        self.assertTrue(same_model("nomic-embed-text", "nomic-embed-text:latest"))
        self.assertFalse(same_model("qwen3:4b", "qwen3:8b"))


class LifecycleTests(unittest.TestCase):
    def test_unloads_others_when_max_one(self):
        p = FakeProvider([m("a:1", [Capability.CHAT], 1, loaded=True), m("b:1", [Capability.CHAT], 1)])
        lc = ModelLifecycle(max_loaded=1)
        self.assertEqual(lc.prepare(p.models[1], p), ["a:1"])


class AssessTests(unittest.TestCase):
    def test_assess(self):
        self.assertEqual(assess(1000, snap(), ram_margin_mb=2048, vram_margin_mb=400).gpu_fit, "full")
        self.assertEqual(assess(5000, snap(), ram_margin_mb=2048, vram_margin_mb=400).gpu_fit, "partial")
        self.assertFalse(assess(20000, snap(), ram_margin_mb=2048, vram_margin_mb=400).ok)

    def test_estimate_matches_observed_log_order_of_magnitude(self):
        # serve.log for llama3.2:3b Q4_K_M at 4096 ctx: 1742+484 MiB weights, 448 MiB KV, ~125 MiB compute
        info = m("llama3.2:3b", [Capability.CHAT], 2.019377376)
        est = info.estimated_peak_ram_mb(4096)
        self.assertTrue(2400 <= est <= 3200, est)


if __name__ == "__main__":
    unittest.main()
