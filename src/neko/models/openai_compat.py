"""Adapter for OpenAI-compatible chat servers: llama.cpp ``llama-server``,
or an Ollama instance on a paired LAN computer exposed through an HTTPS
reverse proxy. Disabled by default.

Remote endpoints must be HTTPS on a private address (validated in
configuration) and authenticate with a bearer token read from an environment
variable - never from a config file. Cloud providers can reuse this adapter
later but require ``privacy.allow_cloud_models = true``.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from ..core.cancel import CancelToken
from ..core.errors import CancelledError, ModelTimeoutError, ModelUnavailableError
from ..core.types import Capability, GenerationRequest, GenerationResult
from .base import ModelInfo, ProviderHealth


class OpenAICompatProvider:
    def __init__(self, name: str, base_url: str, *, token_env: str = "", location: str | None = None,
                 capabilities: dict[str, set[Capability]] | None = None, ca_file: str | None = None) -> None:
        self.id = f"openai-compat:{name}"
        u = urlparse(base_url)
        self.scheme, self.host = u.scheme, u.hostname or "127.0.0.1"
        self.port = u.port or (443 if u.scheme == "https" else 80)
        self.prefix = u.path.rstrip("/")
        self.location = location or ("local" if self.host in ("127.0.0.1", "localhost") else f"lan:{name}")
        self.token_env = token_env
        self.caps = capabilities or {}
        self._ctx = ssl.create_default_context(cafile=ca_file) if self.scheme == "https" else None
        self._last: GenerationResult | None = None

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token_env:
            tok = os.environ.get(self.token_env, "")
            if not tok:
                raise ModelUnavailableError(f"environment variable {self.token_env} is not set",
                                            user_message=f"The paired computer's access token ({self.token_env}) is not set.")
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _conn(self, timeout: float) -> http.client.HTTPConnection:
        if self.scheme == "https":
            return http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=self._ctx)
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def _get(self, path: str, timeout: float = 5) -> Any:
        conn = self._conn(timeout)
        try:
            conn.request("GET", self.prefix + path, headers=self._headers())
            r = conn.getresponse()
            body = r.read()
            if r.status >= 400:
                raise ModelUnavailableError(f"{self.id} {path} HTTP {r.status}")
            return json.loads(body)
        except OSError as exc:
            raise ModelUnavailableError(f"{self.id} unreachable: {exc}",
                                        user_message=f"The model server '{self.id}' is unreachable.") from exc
        finally:
            conn.close()

    def health(self, timeout_s: float = 3.0) -> ProviderHealth:
        try:
            self._get("/v1/models", timeout_s)
            return ProviderHealth(True, "reachable")
        except ModelUnavailableError as exc:
            return ProviderHealth(False, str(exc))

    def list_models(self) -> list[ModelInfo]:
        data = self._get("/v1/models")
        return [ModelInfo(name=m["id"], provider=self.id, location=self.location,
                          capabilities=self.caps.get(m["id"], {Capability.CHAT})) for m in data.get("data", [])]

    def loaded_models(self) -> list[ModelInfo]:
        return []

    @property
    def last_result(self) -> GenerationResult | None:
        return self._last

    def chat_stream(self, req: GenerationRequest, token: CancelToken) -> Iterator[str]:
        body = {
            "model": req.model, "stream": True, "temperature": req.temperature, "max_tokens": req.max_tokens,
            "messages": [{"role": m.role.value, "content": m.content} for m in req.messages],
        }
        conn = self._conn(req.timeout_s)
        token.on_cancel(conn.close)
        start, first, parts = time.perf_counter(), None, []
        try:
            conn.request("POST", self.prefix + "/v1/chat/completions", body=json.dumps(body).encode(),
                         headers=self._headers())
            r = conn.getresponse()
            if r.status >= 400:
                raise ModelUnavailableError(f"HTTP {r.status}: {r.read()[:200]!r}")
            while True:
                if token.cancelled:
                    raise CancelledError(token.reason)
                line = r.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                delta = json.loads(payload)["choices"][0].get("delta", {}).get("content") or ""
                if delta:
                    first = first or (time.perf_counter() - start) * 1000
                    parts.append(delta)
                    yield delta
        except socket.timeout as exc:
            raise ModelTimeoutError(str(exc)) from exc
        except OSError as exc:
            if token.cancelled:
                raise CancelledError(token.reason) from exc
            raise ModelUnavailableError(f"connection lost: {exc}") from exc
        finally:
            conn.close()
            self._last = GenerationResult("".join(parts), req.model, self.id, self.location,
                                          first_token_ms=first, total_ms=(time.perf_counter() - start) * 1000,
                                          cancelled=token.cancelled)

    def chat(self, req: GenerationRequest, token: CancelToken) -> GenerationResult:
        for _ in self.chat_stream(req, token):
            pass
        assert self._last is not None
        return self._last

    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]:
        raise ModelUnavailableError("embeddings are not supported by this adapter")

    def unload(self, model: str) -> None:
        return None
