"""Ollama adapter over its local REST API (stdlib HTTP only).

API used (https://docs.ollama.com/api): GET /api/version, GET /api/tags,
GET /api/ps, POST /api/chat (NDJSON stream), POST /api/embed,
POST /api/generate with keep_alive=0 to unload.

N.E.K.O. never calls /api/pull: model downloads are a deliberate user step.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from ..core.cancel import CancelToken
from ..core.errors import CancelledError, ModelTimeoutError, ModelUnavailableError
from ..core.types import Capability, GenerationRequest, GenerationResult
from .base import ModelInfo, ProviderHealth

_VISION_FAMILIES = {"mllama", "qwen25vl", "qwen2vl", "gemma3", "llava", "minicpmv", "qwen3vl", "moondream"}
_EMBED_HINTS = ("embed", "bge", "minilm", "e5-", "gte")
_CODE_HINTS = ("coder", "code", "starcoder", "deepseek-coder", "codellama")
_THINKING_PREFIXES = ("qwen3", "deepseek-r1", "gpt-oss", "magistral")


def infer_capabilities(name: str, family: str, families: list[str] | None = None,
                       reported: list[str] | None = None) -> set[Capability]:
    if reported:  # newer Ollama returns explicit capabilities from /api/show
        mapping = {"completion": Capability.CHAT, "vision": Capability.VISION,
                   "embedding": Capability.EMBEDDING, "tools": Capability.TOOLS, "thinking": Capability.REASONING}
        caps = {mapping[r] for r in reported if r in mapping}
        if any(h in name.lower() for h in _CODE_HINTS):
            caps.add(Capability.CODING)
        return caps
    lname = name.lower()
    fams = {f.lower() for f in (families or [])} | {family.lower()}
    if any(h in lname for h in _EMBED_HINTS) or fams & {"bert", "nomic-bert"}:
        return {Capability.EMBEDDING}
    caps = {Capability.CHAT}
    if fams & _VISION_FAMILIES or "vl" in lname.split(":")[0] or "vision" in lname:
        caps.add(Capability.VISION)
    if any(h in lname for h in _CODE_HINTS):
        caps.add(Capability.CODING)
    if lname.startswith(("qwen3", "deepseek-r1", "phi4-reasoning", "gpt-oss")):
        caps.add(Capability.REASONING)
    return caps


class OllamaProvider:
    id = "ollama"
    supports_native_tools = True

    def __init__(self, base_url: str = "http://127.0.0.1:11434", *, location: str = "local",
                 default_timeout_s: float = 180.0) -> None:
        u = urlparse(base_url)
        self.scheme = u.scheme or "http"
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or (443 if self.scheme == "https" else 11434)
        self.location = location
        self.default_timeout_s = default_timeout_s
        self._last: GenerationResult | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ http
    def _conn(self, timeout: float) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=timeout)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None,
                 timeout: float = 10.0) -> Any:
        conn = self._conn(timeout)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = resp.read()
            if resp.status >= 400:
                raise ModelUnavailableError(f"ollama {path} -> HTTP {resp.status}: {data[:300]!r}",
                                            user_message=_explain_http_error(resp.status, data))
            return json.loads(data) if data else {}
        except (ConnectionRefusedError, socket.gaierror, OSError) as exc:
            if isinstance(exc, socket.timeout):
                raise ModelTimeoutError(f"ollama {path} timed out") from exc
            raise ModelUnavailableError(
                f"cannot reach Ollama at {self.host}:{self.port}: {exc}",
                user_message=("I can't reach the Ollama model server. Start it with scripts\\start-ollama.ps1 "
                              "(see TROUBLESHOOTING: 'Runtime not found')."),
            ) from exc
        finally:
            conn.close()

    # ------------------------------------------------------------------ provider API
    def health(self, timeout_s: float = 3.0) -> ProviderHealth:
        try:
            v = self._request("GET", "/api/version", timeout=timeout_s)
            return ProviderHealth(True, "Ollama is running", v.get("version", ""))
        except (ModelUnavailableError, ModelTimeoutError) as exc:
            return ProviderHealth(False, str(exc))

    def list_models(self) -> list[ModelInfo]:
        data = self._request("GET", "/api/tags")
        loaded = {m.name for m in self.loaded_models()}
        out = []
        for m in data.get("models", []):
            d = m.get("details", {}) or {}
            out.append(ModelInfo(
                name=m["name"], provider=self.id, location=self.location,
                capabilities=infer_capabilities(m["name"], d.get("family", ""), d.get("families")),
                size_bytes=m.get("size"), parameter_size=d.get("parameter_size", ""),
                quantization=d.get("quantization_level", ""), family=d.get("family", ""),
                loaded=m["name"] in loaded,
            ))
        return out

    def show(self, model: str) -> dict[str, Any]:
        return self._request("POST", "/api/show", {"model": model}, timeout=10)

    def loaded_models(self) -> list[ModelInfo]:
        try:
            data = self._request("GET", "/api/ps", timeout=5)
        except (ModelUnavailableError, ModelTimeoutError):
            return []
        return [ModelInfo(name=m["name"], provider=self.id, location=self.location, size_bytes=m.get("size"),
                          loaded=True, vram_bytes=m.get("size_vram")) for m in data.get("models", [])]

    @property
    def last_result(self) -> GenerationResult | None:
        return self._last

    def chat_stream(self, req: GenerationRequest, token: CancelToken) -> Iterator[str]:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": [m.to_ollama() for m in req.messages],
            "stream": True,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens, "num_ctx": req.num_ctx},
        }
        if req.json_mode:
            body["format"] = "json"
        if req.tools:
            body["tools"] = req.tools
        if req.model.lower().startswith(_THINKING_PREFIXES):
            body["think"] = req.think
        calls: list[dict[str, Any]] = []
        if req.keep_alive is not None:
            body["keep_alive"] = req.keep_alive
        timeout = min(req.timeout_s, token.remaining() or req.timeout_s)
        conn = self._conn(timeout)
        token.on_cancel(lambda: _safe_close(conn))
        start = time.perf_counter()
        first_ms: float | None = None
        parts: list[str] = []
        final: dict[str, Any] = {}
        # Always-thinking models (e.g. Ollama's qwen3:4b) ignore think=false and put their reasoning in
        # the content, ending with "</think>". Hold content back until that marker (then drop the
        # reasoning) or until it clearly isn't coming.
        filter_think = req.model.lower().startswith(_THINKING_PREFIXES) and not req.think
        held: list[str] = []
        try:
            conn.request("POST", "/api/chat", body=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status >= 400:
                data = resp.read()
                raise ModelUnavailableError(f"chat HTTP {resp.status}: {data[:300]!r}",
                                            user_message=_explain_http_error(resp.status, data))
            while True:
                if token.cancelled:
                    raise CancelledError(token.reason)
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise ModelUnavailableError(chunk["error"], user_message=f"The model reported an error: {chunk['error']}")
                for tc in chunk.get("message", {}).get("tool_calls") or []:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):  # some models return a JSON string
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    calls.append({"name": fn.get("name", ""), "arguments": args if isinstance(args, dict) else {}})
                text = chunk.get("message", {}).get("content", "")
                if text and filter_think:
                    held.append(text)
                    joined = "".join(held)
                    if "</think>" in joined:
                        text, filter_think, held = joined.split("</think>", 1)[1].lstrip(), False, []
                    elif len(joined) > 6000:
                        text, filter_think, held = joined, False, []
                    else:
                        text = ""
                if text:
                    if first_ms is None:
                        first_ms = (time.perf_counter() - start) * 1000
                    parts.append(text)
                    yield text
                if chunk.get("done"):
                    final = chunk
                    break
            if held:  # stream ended without a </think> marker: it was a normal answer
                rest = "".join(held)
                first_ms = first_ms or (time.perf_counter() - start) * 1000
                parts.append(rest)
                yield rest
        except socket.timeout as exc:
            raise ModelTimeoutError(f"no response from {req.model} within {timeout:.0f}s") from exc
        except (ConnectionError, OSError) as exc:
            if token.cancelled:
                raise CancelledError(token.reason) from exc
            raise ModelUnavailableError(f"connection to Ollama lost: {exc}",
                                        user_message="The connection to the model server was lost.") from exc
        finally:
            _safe_close(conn)
            self._last = GenerationResult(
                text="".join(parts), model=req.model, provider=self.id, location=self.location,
                prompt_tokens=final.get("prompt_eval_count"), completion_tokens=final.get("eval_count"),
                load_ms=(final.get("load_duration") or 0) / 1e6 or None,
                first_token_ms=first_ms, total_ms=(time.perf_counter() - start) * 1000,
                cancelled=token.cancelled, tool_calls=calls,
                eval_ms=(final.get("eval_duration") or 0) / 1e6 or None,
            )

    def chat(self, req: GenerationRequest, token: CancelToken) -> GenerationResult:
        for _ in self.chat_stream(req, token):
            pass
        assert self._last is not None
        return self._last

    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]:
        # num_gpu=0 keeps the embedder on the CPU: on a 4 GB GPU it would otherwise evict the chat
        # model on every request (measured live: +4 s reload per message).
        data = self._request("POST", "/api/embed", {"model": model, "input": texts, "keep_alive": "30m",
                                                    "options": {"num_gpu": 0}}, timeout=120)
        return data.get("embeddings", [])

    def unload(self, model: str) -> None:
        self._request("POST", "/api/generate", {"model": model, "keep_alive": 0}, timeout=15)


def _safe_close(conn: http.client.HTTPConnection) -> None:
    try:
        if conn.sock is not None:
            conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass


def _explain_http_error(status: int, data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if "does not support tools" in text.lower():
        return "NO_NATIVE_TOOLS: " + text[:200]
    if status == 404 or "not found" in text.lower():
        return ("That model isn't installed in Ollama. N.E.K.O. won't download it automatically - "
                "see docs/MODEL_GUIDE.md for how to add it.")
    if "memory" in text.lower() or "out of memory" in text.lower():
        return "The model ran out of memory. Try a smaller model profile or close other heavy apps."
    return f"The model server returned HTTP {status}: {text[:200]}"
