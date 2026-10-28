"""Neko's "brain map": everything she knows and can do as a graph (nodes + links) for the UI.

Kinds (colour in the UI): core, memory, project, document, word (personal vocabulary), tool, brain
(language models), voice, topic (shared tags / categories that tie things together). Stdlib only; the
UI does the 3D layout and drawing. Sensitive memories are shown without their text.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KINDS = ("core", "topic", "memory", "project", "document", "word", "tool", "brain", "voice")


@dataclass
class Node:
    id: str
    label: str
    kind: str
    detail: str = ""
    weight: float = 1.0


@dataclass
class BrainGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)

    def add(self, node: Node) -> str:
        self.nodes.setdefault(node.id, node)
        return node.id

    def link(self, a: str, b: str) -> None:
        if a != b and a in self.nodes and b in self.nodes:
            self.edges.add((a, b) if a < b else (b, a))

    def degree(self, nid: str) -> int:
        return sum(1 for a, b in self.edges if nid in (a, b))

    def neighbours(self, nid: str) -> list[str]:
        return [b if a == nid else a for a, b in self.edges if nid in (a, b)]

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(KINDS, 0)
        for n in self.nodes.values():
            out[n.kind] = out.get(n.kind, 0) + 1
        return out


def _topic(g: BrainGraph, name: str) -> str:
    name = name.strip().lower()
    return g.add(Node(f"topic:{name}", name.title(), "topic", f"Things tagged or grouped as '{name}'"))


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{3,}")
_STOP = {"user", "asked", "result", "project", "about", "with", "that", "this", "from", "have", "want", "they",
         "their", "what", "when", "will", "your", "neko", "into", "which", "there", "been", "were", "would"}


def build_brain(neko: Any, *, max_memories: int = 220, max_docs: int = 40) -> BrainGraph:
    s = neko.settings
    g = BrainGraph()
    core = g.add(Node("core", (s.voice.wake_names or ["neko"])[0].capitalize(), "core",
                      "The centre: everything she knows and can do connects here.", 3.0))
    hubs = {k: g.add(Node(f"hub:{k}", t, "topic", d, 2.0)) for k, t, d in (
        ("memory", "Memories", "Things you told her or she learned"), ("project", "Projects", "Your projects"),
        ("document", "Documents", "Files in your folders"), ("word", "Vocabulary", "Words she listens for"),
        ("tool", "Tools", "What she can do"), ("brain", "Brains", "The AI models she thinks with"),
        ("voice", "Voice", "How she hears and speaks"))}
    for h in hubs.values():
        g.link(core, h)

    # memories (+ shared tags and key words become topics that tie them together)
    for m in neko.memory.list(limit=max_memories):
        kind = "project" if m.kind == "project" else "memory"
        text = "(sensitive - hidden)" if m.sensitive else m.content
        label = (m.tags[1] if kind == "project" and len(m.tags) > 1 else text[:38]).strip() or m.kind
        nid = g.add(Node(f"mem:{m.id}", label, kind, f"{m.kind}, {m.trust.value}, "
                         f"{time.strftime('%d %b %Y', time.localtime(m.created_at))}\n{text}", 1.0 + min(m.use_count, 10) / 5))
        g.link(nid, hubs[kind])
        for tag in m.tags[:4]:
            if tag and tag not in ("project",):
                g.link(nid, _topic(g, tag))
        if not m.sensitive:
            for w in {w.lower() for w in _WORD.findall(m.content)} - _STOP:
                tid = f"topic:{w}"
                if tid in g.nodes:
                    g.link(nid, tid)

    # documents in your own folders (names only)
    files: list[tuple[float, Path]] = []
    for root in [r for r in s.tools.allowed_roots if len(r.rstrip("\\/")) > 3][:6]:
        try:
            for e in os.scandir(root):
                if e.is_file() and os.path.splitext(e.name)[1].lower() in (".pdf", ".docx", ".pptx", ".txt", ".md"):
                    files.append((e.stat().st_mtime, Path(e.path)))
        except OSError:
            continue
    for _mt, p in sorted(files, reverse=True)[:max_docs]:
        nid = g.add(Node(f"doc:{p}", p.stem[:40], "document", str(p)))
        g.link(nid, hubs["document"])
        g.link(nid, _topic(g, p.parent.name))
        for w in re.findall(r"[a-z]{4,}", p.stem.lower()):
            if f"topic:{w}" in g.nodes:
                g.link(nid, f"topic:{w}")

    # projects on disk
    for root in list(s.tools.writable_roots)[:3]:
        try:
            for d in sorted(Path(root).iterdir()):
                if d.is_dir() and not d.name.startswith((".", "$")):
                    nid = g.add(Node(f"proj:{d}", d.name, "project", str(d), 1.4))
                    g.link(nid, hubs["project"])
                    mem = [n for n in g.nodes.values() if n.kind == "project" and n.label.lower() == d.name.lower()]
                    for n in mem:
                        g.link(nid, n.id)
        except OSError:
            continue

    # vocabulary
    try:
        from ..voice.vocabulary import vocabulary_for

        for w in vocabulary_for(s).words()[:40]:
            g.link(g.add(Node(f"word:{w.lower()}", w, "word", "She listens for this word")), hubs["word"])
    except Exception:  # noqa: BLE001 - the map must open even if a source fails
        pass

    # tools grouped by category
    for spec in neko.tools.all():
        if spec.prohibited:
            continue
        nid = g.add(Node(f"tool:{spec.name}", spec.name.replace("_", " "), "tool",
                         f"{spec.description}\nRisk level {int(spec.risk)} - {spec.category}"))
        g.link(nid, hubs["tool"])
        g.link(nid, _topic(g, spec.category))

    # brains
    for m in neko.router.installed():
        where = "on this PC" if m.location == "local" else m.location.replace("cloud:", "cloud: ")
        nid = g.add(Node(f"brain:{m.name}", m.name.split("/")[-1], "brain",
                         f"{where}; can do: {', '.join(sorted(c.value for c in m.capabilities))}", 1.5))
        g.link(nid, hubs["brain"])

    # voice
    for key, label, detail in (("stt", f"Hearing: {s.voice.stt_model}", f"speech recognition on {s.voice.stt_device}"),
                               ("tts", f"Voice: {s.voice.tts_engine} ({s.voice.gender})", "how she speaks"),
                               ("wake", "Wake name", ", ".join(s.voice.wake_names))):
        g.link(g.add(Node(f"voice:{key}", label, "voice", detail, 1.3)), hubs["voice"])

    # drop topics that connect fewer than two things (noise)
    for nid in [n for n, node in g.nodes.items() if node.kind == "topic" and not n.startswith("hub:")]:
        if g.degree(nid) < 2:
            g.edges = {e for e in g.edges if nid not in e}
            del g.nodes[nid]
    return g


__all__ = ["KINDS", "BrainGraph", "Node", "build_brain"]
