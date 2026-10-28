"""Offline model inventory: reads Ollama's model store from disk, read-only.

This works even when the Ollama server is not running, which is how the
existing ``llama3.2:3b`` in ``D:\\Ollama\\models`` was verified without starting
anything. Nothing here modifies, moves or deletes model files.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..database.db import Database

# Licence notes for families N.E.K.O. recommends. Always re-check the model card.
KNOWN_LICENSES = {
    "llama3.2": "Llama 3.2 Community License (custom; attribution + AUP; redistribution allowed with notice)",
    "qwen3": "Apache-2.0",
    "qwen2.5-coder": "Apache-2.0 for most sizes; the 3B size uses the Qwen Research License (non-commercial) - verify",
    "qwen2.5vl": "Qwen license varies by size; 3B uses Qwen Research License (non-commercial) - verify",
    "gemma3": "Gemma Terms of Use (custom; use restrictions apply)",
    "nomic-embed-text": "Apache-2.0",
    "bge-m3": "MIT",
}


@dataclass
class InventoryEntry:
    name: str
    runtime: str
    manifest_path: str
    blob_path: str
    size_bytes: int
    digest: str
    blob_present: bool
    license_note: str
    metadata: dict[str, Any]

    @property
    def quantization(self) -> str:
        ft = self.metadata.get("general.file_type")
        return {15: "Q4_K_M", 7: "Q8_0", 1: "F16", 2: "Q4_0", 17: "Q5_K_M", 18: "Q6_K"}.get(ft, str(ft or ""))


def scan_ollama_store(models_dir: Path) -> list[InventoryEntry]:
    entries: list[InventoryEntry] = []
    manifests = models_dir / "manifests"
    if not manifests.is_dir():
        return entries
    for mf in manifests.rglob("*"):
        if not mf.is_file():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        layers = data.get("layers", [])
        model_layer = next((ly for ly in layers if ly.get("mediaType", "").endswith(".model")), None)
        if model_layer is None:
            continue
        rel = mf.relative_to(manifests).parts  # registry/namespace/name/tag
        name = f"{rel[-2]}:{rel[-1]}" if len(rel) >= 2 else mf.name
        if len(rel) >= 3 and rel[-3] not in ("library",):
            name = f"{rel[-3]}/{name}"
        digest = model_layer["digest"]
        blob = models_dir / "blobs" / digest.replace(":", "-")
        meta_file = models_dir / "metadata" / (digest.replace(":", "-") + ".json")
        meta: dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8")).get("kv", {})
                meta.pop("tokenizer.chat_template", None)
            except (OSError, json.JSONDecodeError):
                meta = {}
        family = name.split(":")[0].split("/")[-1]
        entries.append(InventoryEntry(
            name=name, runtime="ollama", manifest_path=str(mf), blob_path=str(blob),
            size_bytes=int(model_layer.get("size", 0)), digest=digest, blob_present=blob.exists(),
            license_note=KNOWN_LICENSES.get(family, "unknown - check the model card before sharing"),
            metadata={k: v for k, v in meta.items() if not k.startswith("tokenizer.")},
        ))
    # de-duplicate manifests/ and manifests-v2/ style copies of the same model
    seen: dict[str, InventoryEntry] = {}
    for e in entries:
        seen.setdefault(e.digest + e.name, e)
    return list(seen.values())


def sync_inventory(db: Database, entries: list[InventoryEntry], capabilities: dict[str, str] | None = None) -> None:
    now = time.time()
    for e in entries:
        db.execute(
            """INSERT INTO model_inventory(name, runtime, path, size_bytes, quantization, capabilities, license,
                   source, digest, discovered_at, removable)
               VALUES (?,?,?,?,?,?,?,?,?,?,0)
               ON CONFLICT(name) DO UPDATE SET path=excluded.path, size_bytes=excluded.size_bytes,
                   quantization=excluded.quantization, digest=excluded.digest""",
            (e.name, e.runtime, e.blob_path, e.size_bytes, e.quantization, (capabilities or {}).get(e.name, ""),
             e.license_note, "ollama registry (pre-existing on disk)", e.digest, now),
        )
