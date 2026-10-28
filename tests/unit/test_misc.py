import json
import unittest

from tests.helpers import temp_dir

from neko.agents.registry import AGENTS, agent_for
from neko.core.cancel import CancelToken
from neko.core.errors import CancelledError
from neko.core.types import RiskLevel, TaskKind
from neko.database.db import Database
from neko.memory.store import MemoryStore
from neko.models.inventory import scan_ollama_store
from neko.models.ollama import infer_capabilities
from neko.orchestration.intent import classify
from neko.orchestration.tasks import InvalidTransition, TaskManager
from neko.vision.images import tile_boxes
from neko.voice.tts import clean_for_speech


class IntentTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify("hi").kind, TaskKind.SMALL_TALK)
        self.assertEqual(classify("Fix this Python traceback: TypeError").kind, TaskKind.CODING)
        self.assertEqual(classify("Make a step-by-step plan for my exams").kind, TaskKind.PLANNING)
        self.assertEqual(classify("open notepad").kind, TaskKind.COMMAND)
        self.assertEqual(classify("what is the capital of Japan?").kind, TaskKind.QUESTION)
        self.assertEqual(classify("anything", has_image=True).kind, TaskKind.VISION)
        i = classify("Remember that I like tea")
        self.assertEqual((i.memory_action, i.memory_text), ("remember", "I like tea"))
        self.assertEqual(classify("forget about my old address").memory_action, "forget")
        self.assertEqual(classify("আমার নাম সান মনে রাখো").memory_action, "remember")
        self.assertTrue(classify("my bank password is ...").sensitive)
        self.assertTrue(classify("Think carefully about whether I should change jobs").deep)
        self.assertFalse(classify("make a plan for my week").deep)


class TaskTests(unittest.TestCase):
    def test_state_machine(self):
        db = Database(":memory:")
        db.migrate()
        tm = TaskManager(db, MemoryStore(db))
        t = tm.create("goal", "question", None)
        tm.transition(t, "running")
        tm.transition(t, "succeeded")
        with self.assertRaises(InvalidTransition):
            tm.transition(t, "running")

    def test_lesson_needs_evidence(self):
        db = Database(":memory:")
        db.migrate()
        mem = MemoryStore(db)
        tm = TaskManager(db, mem)
        t = tm.create("g", "command", None)
        self.assertIsNone(tm.record_outcome(t, succeeded=True, lesson="Claims success without evidence"))
        t2 = tm.create("g2", "command", None)
        db.execute("INSERT INTO verification_evidence(task_id, method, passed, detail, created_at) "
                   "VALUES (?, 'file_exists', 1, 'ok', 0)", (t2.id,))
        mid = tm.record_outcome(t2, succeeded=True, lesson="Notes folder is D:/Notes")
        self.assertEqual(mem.get(mid).status, "pending_approval")  # still needs the user's approval


class CancelTests(unittest.TestCase):
    def test_child_and_timeout(self):
        parent = CancelToken()
        child = parent.child()
        parent.cancel("stop")
        self.assertTrue(child.cancelled)
        with self.assertRaises(CancelledError):
            child.raise_if_cancelled()
        t = CancelToken(timeout_s=0.01)
        self.assertTrue(t.wait(0.5))


class InventoryTests(unittest.TestCase):
    def test_scan_synthetic_store(self):
        root = temp_dir()
        man = root / "manifests" / "registry.ollama.ai" / "library" / "llama3.2"
        man.mkdir(parents=True)
        digest = "sha256:" + "a" * 64
        (man / "3b").write_text(json.dumps({"layers": [
            {"mediaType": "application/vnd.ollama.image.model", "digest": digest, "size": 2019377376}]}))
        (root / "blobs").mkdir()
        (root / "blobs" / digest.replace(":", "-")).write_bytes(b"x")
        (root / "metadata").mkdir()
        (root / "metadata" / (digest.replace(":", "-") + ".json")).write_text(
            json.dumps({"kv": {"general.file_type": 15, "tokenizer.chat_template": "..."}}))
        inv = scan_ollama_store(root)
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0].name, "llama3.2:3b")
        self.assertEqual(inv[0].quantization, "Q4_K_M")
        self.assertTrue(inv[0].blob_present)
        self.assertIn("Llama 3.2", inv[0].license_note)

    def test_capability_inference(self):
        self.assertIn("vision", {c.value for c in infer_capabilities("gemma3:4b", "gemma3")})
        self.assertEqual({c.value for c in infer_capabilities("nomic-embed-text:latest", "nomic-bert")}, {"embedding"})
        self.assertIn("coding", {c.value for c in infer_capabilities("qwen2.5-coder:1.5b", "qwen2")})


class AgentTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertFalse(any(a.can_delegate for n, a in AGENTS.items() if n != "coordinator"))
        self.assertEqual(agent_for(TaskKind.VISION).allowed_tools, frozenset())
        self.assertLessEqual(AGENTS["planner"].max_risk, RiskLevel.READ_ONLY)


class SmallUtilTests(unittest.TestCase):
    def test_clean_for_speech(self):
        self.assertEqual(clean_for_speech("**Hi** see `x` ```code``` https://a.b"), "Hi see x (code omitted) link")

    def test_tiles_cover(self):
        boxes = tile_boxes(2560, 1440)
        self.assertGreaterEqual(len(boxes), 4)
        self.assertEqual(boxes[0][:2], (0, 0))


if __name__ == "__main__":
    unittest.main()
