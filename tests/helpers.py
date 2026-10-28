"""Test doubles. No test touches the network, a real model, a microphone,
the user's data folder or the existing D:\\Ollama installation."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neko.core.cancel import CancelToken  # noqa: E402
from neko.core.errors import CancelledError  # noqa: E402
from neko.core.types import Capability, GenerationRequest, GenerationResult  # noqa: E402
from neko.models.base import ModelInfo, ProviderHealth  # noqa: E402


class FakeProvider:
    """Scripted model provider. ``responses`` are returned in order."""

    id = "fake"

    def __init__(self, models: list[ModelInfo] | None = None, responses: list[str] | None = None,
                 location: str = "local", chunk: int = 4, delay_s: float = 0.0) -> None:
        self.location = location
        self.models = models if models is not None else [
            ModelInfo("llama3.2:3b", "fake", location, {Capability.CHAT}, size_bytes=2_019_377_376)]
        self.responses = list(responses or ["Hello from the fake model."])
        self.requests: list[GenerationRequest] = []
        self.unloaded: list[str] = []
        self.chunk = chunk
        self.delay_s = delay_s
        self._last: GenerationResult | None = None

    def health(self, timeout_s: float = 3.0) -> ProviderHealth:
        return ProviderHealth(True, "fake ok", "0")

    def list_models(self) -> list[ModelInfo]:
        return list(self.models)

    def loaded_models(self) -> list[ModelInfo]:
        return [m for m in self.models if m.loaded]

    @property
    def last_result(self) -> GenerationResult | None:
        return self._last

    def chat_stream(self, req: GenerationRequest, token: CancelToken) -> Iterator[str]:
        self.requests.append(req)
        text = self.responses.pop(0) if self.responses else "(no more scripted responses)"
        if isinstance(text, dict):  # scripted native tool call: {"tool_calls": [{"name", "arguments"}]}
            self._last = GenerationResult("", req.model, self.id, self.location, completion_tokens=5,
                                          first_token_ms=5, total_ms=20, tool_calls=text["tool_calls"])
            return
        out = []
        for i in range(0, len(text), self.chunk):
            if token.cancelled:
                self._last = GenerationResult("".join(out), req.model, self.id, self.location, cancelled=True)
                raise CancelledError(token.reason)
            if self.delay_s:
                token.wait(self.delay_s)
            piece = text[i:i + self.chunk]
            out.append(piece)
            yield piece
        self._last = GenerationResult(text, req.model, self.id, self.location, prompt_tokens=10,
                                      completion_tokens=len(text) // 4, first_token_ms=5, total_ms=50)

    def chat(self, req: GenerationRequest, token: CancelToken) -> GenerationResult:
        for _ in self.chat_stream(req, token):
            pass
        assert self._last is not None
        return self._last

    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]:
        return [bag_of_words(t) for t in texts]

    def unload(self, model: str) -> None:
        self.unloaded.append(model)


_VOCAB = ["coffee", "tea", "python", "rust", "music", "jazz", "dog", "cat", "name", "project", "neko", "drink"]


def bag_of_words(text: str) -> list[float]:
    low = text.lower()
    return [1.0 if w in low else 0.0 for w in _VOCAB] + [0.01]


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="neko-test-"))


def make_settings(tmp: Path, **overrides: dict) -> object:
    from neko.configuration.settings import load_settings

    extra = {"app": {"data_dir": str(tmp / "data")}}
    for k, v in overrides.items():
        extra.setdefault(k, {}).update(v)
    return load_settings(tmp / "missing.toml", extra=extra)


class FakeMonitor:
    """Deterministic resources: 8 GB RAM free, 3.5 GB VRAM free, on AC power."""

    def __init__(self, **kw: object) -> None:
        from neko.resources.monitor import ResourceSnapshot

        base = dict(ram_total_mb=16000, ram_free_mb=8000, vram_total_mb=4096, vram_used_mb=600,
                    gpu_name="Fake GPU", on_battery=False, battery_pct=90, disk_free_gb=100.0, taken_at=1.0)
        base.update(kw)
        self.snap = ResourceSnapshot(**base)  # type: ignore[arg-type]

    def snapshot(self, *, fresh: bool = False) -> object:
        return self.snap


def build_test_neko(tmp: Path, provider: FakeProvider | None = None, **overrides: dict) -> object:
    from neko.app.bootstrap import build

    s = make_settings(tmp, **overrides)
    neko = build(s, providers=[provider or FakeProvider()])
    neko.monitor = FakeMonitor()
    neko.coordinator.monitor = neko.monitor
    neko.coordinator.explorer = lambda: []  # never ask the real File Explorer from tests
    # never checkpoint / reset / commit N.E.K.O.'s real Git folder from a test: just run the change
    neko.coordinator.upgrade_transaction = lambda request, change, root: (change(), ("kept", "test"))[1]
    return neko
