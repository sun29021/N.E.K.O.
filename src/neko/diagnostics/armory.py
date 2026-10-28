"""Tool armory: everything Neko can reach, with an honest status (stdlib only, read-only checks).

status: "connected" (works now) | "needs key" | "off" (switched off in settings) | "missing" (not installed).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any


@dataclass
class Item:
    group: str
    name: str
    what: str
    status: str
    how: str = ""          # what to do to turn it on


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def armory(neko: Any) -> list[Item]:
    s = neko.settings
    items: list[Item] = []
    net, cloud = s.privacy.allow_network, s.privacy.allow_cloud_models

    # brains
    installed = neko.router.installed()
    local = [m for m in installed if m.location == "local" and "embed" not in m.name]
    items.append(Item("Brains", "Local models", ", ".join(m.name for m in local[:5]) or "none found",
                      "connected" if local else "missing", "Start Ollama (scripts\\start-ollama.ps1)"))
    try:
        from ..models.cloud import CLOUDS, read_key
    except ImportError:  # pragma: no cover
        CLOUDS, read_key = {}, None  # type: ignore[assignment]
    for name, spec in CLOUDS.items():
        model = next((m.name for m in installed if m.location == f"cloud:{name}"), "")
        has_key = bool(read_key and read_key(spec, s.data_dir))
        status = ("off" if not cloud else "connected" if model else "needs key" if not has_key else "starting")
        what = {"groq": "fast, smart everyday brain (free tier)", "gemini": "huge documents + deep thinking (free tier)"}
        items.append(Item("Brains", name.title(), (what.get(name, "") + (f" - {model}" if model else "")),
                          status, "Command Center > Settings > paste your free key"))
    office = [m.name for m in installed if m.location == "lan:office"]
    items.append(Item("Brains", "Office PC GPU", ("bigger models on your office PC via Tailscale" +
                                                   (f" - {', '.join(office[:4])}" if office else "")),
                      "connected" if office else ("off" if not s.models.office_url else "offline"),
                      "On the office PC run scripts\\share-gpu.ps1; here Settings: office_url = auto"))
    try:
        from ..tools.dev import find_claude

        claude = bool(find_claude())
    except Exception:  # noqa: BLE001
        claude = False
    items.append(Item("Brains", "Claude Code", "coding, project work, 'upgrade yourself'",
                      "connected" if claude and cloud and s.tools.claude_code else "off" if claude else "missing",
                      "Install Claude Code and sign in"))

    # voice
    v = s.voice
    items.append(Item("Voice", "Natural voice", f"{'Microsoft neural voices online' if v.tts_engine == 'edge' else v.tts_engine}"
                      f", {v.gender}, English + Bangla", "connected" if v.enabled and (v.tts_engine != "edge" or net)
                      and (v.tts_engine != "edge" or _has("edge_tts")) else "off", "Settings > Voice"))
    items.append(Item("Voice", "Hearing", f"{v.stt_model} on {v.stt_device}",
                      "connected" if _has("faster_whisper") else "missing", "scripts\\setup.ps1 -WithVoice"))
    items.append(Item("Voice", "Always listening", f"wake name: {', '.join(v.wake_names[:3])}",
                      "connected" if v.always_listen else "off", "Right-click the orb > Always listen"))

    # abilities from the tool registry
    groups = {"files": "Files & documents", "network": "Internet", "computer_control": "PC control",
              "media": "Music", "dev": "Coding", "diagnostics": "System", "scripts": "Scripts"}
    for spec in sorted(neko.tools.all(), key=lambda t: (t.category, t.name)):
        if spec.prohibited:
            continue
        status = "connected"
        how = ""
        if spec.needs_network and not net:
            status, how = "off", "Settings > Allow internet"
        if spec.category == "computer_control" and not s.tools.computer_control_enabled:
            status, how = "off", "Settings > Computer control"
        if spec.name == "play_music" and not _has("yt_dlp"):
            status, how = "missing", "pip install yt-dlp"
        if spec.name == "read_document" and not _has("pypdf"):
            status = "connected"  # Word/PowerPoint/text work without pypdf; PDFs need it
        risk = {0: "safe", 1: "low risk", 2: "asks you first", 3: "asks you every time"}.get(int(spec.risk), "")
        items.append(Item(groups.get(spec.category, spec.category.title()), spec.name.replace("_", " "),
                          f"{spec.description} ({risk})", status, how))
    return items


__all__ = ["Item", "armory"]
