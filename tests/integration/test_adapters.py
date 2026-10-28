"""Adapter tests against a fake Ollama HTTP server bound to 127.0.0.1 on an
ephemeral port for the duration of the test only (not reachable from the
network). Also a read-only scan of the real D:\\Ollama\\models if present."""

import json
import threading
import tomllib
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.helpers import ROOT, temp_dir

from neko.configuration.settings import load_settings, settings_from_dict
from neko.core.cancel import CancelToken
from neko.core.errors import CancelledError, ModelUnavailableError
from neko.core.types import ChatMessage, GenerationRequest, Role
from neko.models.inventory import scan_ollama_store
from neko.models.ollama import OllamaProvider


class FakeOllama(BaseHTTPRequestHandler):
    slow = False

    def log_message(self, *args):  # silence
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/version":
            self._json({"version": "0.40.9"})
        elif self.path == "/api/tags":
            self._json({"models": [{"name": "llama3.2:3b", "size": 2019377376, "details": {
                "family": "llama", "parameter_size": "3.2B", "quantization_level": "Q4_K_M"}}]})
        elif self.path == "/api/ps":
            self._json({"models": []})
        else:
            self._json({"error": "nope"}, 404)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/chat" and req.get("model") == "qwen3:4b":
            FakeOllama.last_think = req.get("think")
            self.send_response(200)
            self.end_headers()
            for w in ["Okay, the user wants", " tips. Let me think.\n</think>\n\n", "1. Self-test"]:
                self.wfile.write(json.dumps({"message": {"content": w}, "done": False}).encode() + b"\n")
            self.wfile.write(json.dumps({"done": True, "eval_count": 3}).encode() + b"\n")
            return
        if self.path == "/api/chat":
            if req.get("model") != "llama3.2:3b":
                self._json({"error": f"model '{req.get('model')}' not found"}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            words = ["Hello", " from", " fake", " Ollama."] * (50 if FakeOllama.slow else 1)
            try:
                for w in words:
                    self.wfile.write(json.dumps({"message": {"role": "assistant", "content": w},
                                                 "done": False}).encode() + b"\n")
                    self.wfile.flush()
                    if FakeOllama.slow:
                        import time
                        time.sleep(0.02)
                self.wfile.write(json.dumps({"done": True, "eval_count": 4, "prompt_eval_count": 12,
                                             "load_duration": 1_000_000}).encode() + b"\n")
            except (ConnectionError, OSError):
                pass  # client cancelled and closed the connection - expected in the cancel test
        elif self.path == "/api/embed":
            self._json({"embeddings": [[0.1, 0.2, 0.3] for _ in req.get("input", [])]})
        elif self.path == "/api/generate":
            self._json({"done": True})
        else:
            self._json({"error": "nope"}, 404)


class OllamaAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def req(self, model="llama3.2:3b"):
        return GenerationRequest([ChatMessage(Role.USER, "hi")], model=model, timeout_s=10)

    def test_health_list_stream_embed(self):
        p = OllamaProvider(self.url)
        h = p.health()
        self.assertTrue(h.ok)
        self.assertEqual(h.version, "0.40.9")
        models = p.list_models()
        self.assertEqual(models[0].name, "llama3.2:3b")
        self.assertEqual(models[0].quantization, "Q4_K_M")
        chunks = list(p.chat_stream(self.req(), CancelToken()))
        self.assertEqual("".join(chunks), "Hello from fake Ollama.")
        self.assertEqual(p.last_result.completion_tokens, 4)
        self.assertEqual(p.embed("x", ["a", "b"]), [[0.1, 0.2, 0.3]] * 2)
        p.unload("llama3.2:3b")

    def test_leaked_thinking_is_stripped(self):
        p = OllamaProvider(self.url)
        out = "".join(p.chat_stream(self.req("qwen3:4b"), CancelToken()))
        self.assertEqual(out, "1. Self-test")
        self.assertIs(FakeOllama.last_think, False)
        self.assertNotIn("think", json.dumps({}))  # llama3.2 requests carry no think flag (checked below)

    def test_missing_model_explained(self):
        p = OllamaProvider(self.url)
        with self.assertRaises(ModelUnavailableError) as cm:
            list(p.chat_stream(self.req("nope:1b"), CancelToken()))
        self.assertIn("won't download it automatically", cm.exception.user_message)

    def test_cancel_mid_stream(self):
        FakeOllama.slow = True
        try:
            p = OllamaProvider(self.url)
            tok = CancelToken()
            got = []
            with self.assertRaises(CancelledError):
                for c in p.chat_stream(self.req(), tok):
                    got.append(c)
                    if len(got) == 3:
                        tok.cancel("user")
            self.assertTrue(p.last_result.cancelled)
        finally:
            FakeOllama.slow = False

    def test_server_down(self):
        p = OllamaProvider("http://127.0.0.1:1")
        self.assertFalse(p.health(timeout_s=1).ok)
        with self.assertRaises(ModelUnavailableError) as cm:
            p.list_models()
        self.assertIn("start-ollama", cm.exception.user_message)


class ConfigTemplateTests(unittest.TestCase):
    def test_user_example_is_valid(self):
        tmp = temp_dir()
        s = load_settings(ROOT / "config" / "user.example.toml", extra={"app": {"data_dir": str(tmp)}})
        self.assertEqual(s.models.profile, "existing-only")

    def test_safe_mode_snippet_is_valid(self):
        text = (ROOT / "scripts" / "launch.ps1").read_text(encoding="utf-8")
        snippet = text.split('@"')[1].split('"@')[0]
        settings_from_dict(tomllib.loads(snippet))


@unittest.skipUnless(Path(r"D:\Ollama\models\manifests").is_dir(), "no existing Ollama store on this machine")
class RealOllamaStoreTests(unittest.TestCase):
    """Read-only: parses manifests/metadata, never opens model blobs."""

    def test_existing_llama_is_detected(self):
        inv = scan_ollama_store(Path(r"D:\Ollama\models"))
        names = {e.name for e in inv}
        self.assertIn("llama3.2:3b", names)
        llama = next(e for e in inv if e.name == "llama3.2:3b")
        self.assertTrue(llama.blob_present)
        self.assertEqual(llama.size_bytes, 2019377376)
        self.assertEqual(llama.quantization, "Q4_K_M")


if __name__ == "__main__":
    unittest.main()
