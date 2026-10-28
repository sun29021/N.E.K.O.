"""Built-in model profiles. A profile maps *roles* to model names in order of
preference. The router only picks models that are actually installed; it
never downloads anything.

Sizes are Ollama download sizes checked on 2026-10-27 (see RESEARCH_LEDGER).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelProfile:
    name: str
    description: str
    roles: dict[str, list[str]] = field(default_factory=dict)
    num_ctx: int = 4096


PROFILES: dict[str, ModelProfile] = {
    # Works with what is ALREADY on disk (llama3.2:3b) - zero downloads.
    "existing-only": ModelProfile(
        "existing-only",
        "Uses only llama3.2:3b, already present in D:\\Ollama\\models. Text only.",
        {
            "fast": ["llama3.2:3b"],
            "chat": ["llama3.2:3b"],
            "reasoning": ["llama3.2:3b"],
            "coding": ["llama3.2:3b"],
            "vision": [],
            "embedding": [],
        },
    ),
    # Recommended for RTX 3050 4 GB + 16 GB RAM. ~6.2 GB of optional downloads.
    "laptop-lite": ModelProfile(
        "laptop-lite",
        "RTX 3050 4 GB laptop. One model resident at a time. Text, light coding, optional vision.",
        {
            "fast": ["qwen3:1.7b", "llama3.2:3b"],
            "chat": ["llama3.2:3b", "qwen3:4b"],
            # measured 2026-10-27: qwen3:4b always "thinks" (~99 s for a study plan on the RTX 3050),
            # llama3.2:3b ~30 s - so everyday planning uses llama; "think carefully..." uses qwen3:4b.
            "reasoning": ["llama3.2:3b", "qwen3:4b"],
            "deep": ["qwen3:4b", "llama3.2:3b"],
            "coding": ["qwen2.5-coder:1.5b", "qwen3:4b", "llama3.2:3b"],
            "vision": ["gemma3:4b", "qwen2.5vl:3b"],
            "embedding": ["nomic-embed-text", "bge-m3"],
        },
        num_ctx=4096,
    ),
    # For the optional RTX 5060 Ti 16 GB desktop (unverified hardware).
    "desktop-16gb": ModelProfile(
        "desktop-16gb",
        "Desktop with a 12-16 GB GPU (e.g. the office RTX 5060 Ti 16 GB): 14B models fully on the GPU.",
        {
            "fast": ["qwen3:4b", "qwen3:8b"],
            "chat": ["qwen3:14b", "qwen3:8b", "qwen3:4b"],
            "reasoning": ["qwen3:14b", "qwen3:8b"],
            "coding": ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "qwen3:14b"],
            "vision": ["gemma3:12b", "gemma3:4b", "qwen2.5vl:7b"],
            "embedding": ["bge-m3", "nomic-embed-text"],
        },
        num_ctx=16384,
    ),
    # Two 16 GB GPUs (the office MSI with 2x RTX 5060 Ti): Ollama splits a 27-32B model across both cards.
    "desktop-32gb": ModelProfile(
        "desktop-32gb",
        "Desktop with ~32 GB of GPU memory (e.g. 2x RTX 5060 Ti 16 GB): 27-32B models across both GPUs.",
        {
            "fast": ["qwen3:4b", "qwen3:8b", "qwen3:14b"],
            "chat": ["qwen3:32b", "qwen3:14b", "qwen3:8b"],
            "reasoning": ["qwen3:32b", "qwen3:14b"],
            "deep": ["qwen3:32b", "qwen3:14b"],
            "coding": ["qwen2.5-coder:32b", "qwen3:32b", "qwen2.5-coder:14b"],
            "vision": ["gemma3:27b", "gemma3:12b", "qwen2.5vl:7b"],
            "embedding": ["bge-m3", "nomic-embed-text"],
        },
        num_ctx=24576,
    ),
}


def office_rank(role: str, model: str) -> int | None:
    """Where a model on the office PC stands in the big-desktop preferences for a role (0 = best).
    The laptop uses this to pick the office's best model instead of any model the office has."""
    def norm(n: str) -> str:
        n = n.lower()
        return n if ":" in n else n + ":latest"

    order: list[str] = []
    for prof in ("desktop-32gb", "desktop-16gb"):
        order += [n for n in PROFILES[prof].roles.get(role, []) if n not in order]
    return next((i for i, n in enumerate(order) if norm(n) == norm(model)), None)


def get_profile(name: str) -> ModelProfile:
    return PROFILES.get(name, PROFILES["laptop-lite"])
