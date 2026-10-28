"""Provider contracts.

Every runtime adapter implements ``ModelProvider``. The rest of N.E.K.O.
only talks to this interface, never to Ollama/llama.cpp directly.

Cancellation: ``chat_stream`` must stop yielding promptly once
``token.cancelled`` is set and close its network connection.
Timeouts: adapters raise ``ModelTimeoutError``; unavailability raises
``ModelUnavailableError``. Both are caught by the router for fallback.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..core.cancel import CancelToken
from ..core.types import Capability, GenerationRequest, GenerationResult


@dataclass
class ModelInfo:
    name: str                               # runtime-specific id, e.g. "llama3.2:3b"
    provider: str                           # provider id, e.g. "ollama"
    location: str = "local"                 # local | lan:<name> | cloud:<name>
    capabilities: set[Capability] = field(default_factory=set)
    size_bytes: int | None = None           # file size on disk
    parameter_size: str = ""                # e.g. "3.2B"
    quantization: str = ""                  # e.g. "Q4_K_M"
    context_length: int | None = None
    family: str = ""
    license: str = ""
    loaded: bool = False
    vram_bytes: int | None = None           # when loaded and reported by runtime

    def estimated_peak_ram_mb(self, num_ctx: int = 4096) -> int:
        """Conservative peak *combined* (RAM+VRAM) memory estimate.

        weights ~= file size; KV cache for a ~3B GQA model at 4k ctx ~= 0.45 GB
        (observed 448 MiB in serve.log for llama3.2:3b); compute buffers ~= 0.15 GB.
        Scaled linearly with context. This is an estimate, not a measurement.
        """
        weights_mb = (self.size_bytes or 0) / 1_048_576
        kv_mb = 450 * (num_ctx / 4096) * max(1.0, weights_mb / 2000)
        return int(weights_mb + kv_mb + 150)


@dataclass
class ProviderHealth:
    ok: bool
    detail: str
    version: str = ""


@runtime_checkable
class ModelProvider(Protocol):
    id: str
    location: str

    def health(self, timeout_s: float = 3.0) -> ProviderHealth: ...

    def list_models(self) -> list[ModelInfo]: ...

    def loaded_models(self) -> list[ModelInfo]: ...

    def chat_stream(self, req: GenerationRequest, token: CancelToken) -> Iterator[str]:
        """Yield text chunks. After exhaustion, ``last_result`` holds timings."""
        ...

    def chat(self, req: GenerationRequest, token: CancelToken) -> GenerationResult: ...

    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]: ...

    def unload(self, model: str) -> None: ...

    @property
    def last_result(self) -> GenerationResult | None: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, model: str, texts: list[str], token: CancelToken | None = None) -> list[list[float]]: ...
