"""Personal vocabulary: the user's own words, given to speech recognition as a spelling hint.

Whisper turns unfamiliar words into English-sounding ones ("oporadhi bangla" -> "opera di Bungalow").
A short prompt listing the words the user really says fixes most of that (measured 2026-10-28:
"up a Radhi Bangla song" -> "Oporadhi, Bangla song", "HISSEP project" -> "Hisab project").

Words come from ``voice.vocabulary`` in the settings, from ``vocabulary.txt`` in the data folder
("Neko, learn the word Oporadhi" adds to it) and from the user's project folder names. Plain text
only, never audio. Stdlib only.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

MAX_PROMPT_CHARS = 420  # whisper reads at most ~224 prompt tokens; keep well under


class Vocabulary:
    def __init__(self, path: Path, seed: list[str] | None = None, folders: list[str] | None = None,
                 names: list[str] | None = None, doc_folders: list[str] | None = None) -> None:
        self.doc_folders = doc_folders or []
        self.path = path
        self.seed = [w for w in (seed or []) if w.strip()]
        self.folders = folders or []
        self.names = [n for n in (names or []) if n]
        self._lock = threading.Lock()
        self._cache: tuple[float, str] | None = None

    # ------------------------------------------------------------------ words
    def learned(self) -> list[str]:
        try:
            return [ln.strip() for ln in self.path.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]
        except OSError:
            return []

    def _project_names(self) -> list[str]:
        out = []
        for root in self.folders[:4]:
            try:
                out += [p.name for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith((".", "$"))
                        and len(p.name) >= 3]
            except OSError:
                continue
        return out[:20]

    def _document_names(self) -> list[str]:
        """Names of your newest documents (Downloads, Desktop...): "Hisab-Manual.pdf" -> "Hisab Manual".
        Seen live: "Hisab Manual" was heard as "Dishab Manual"."""
        files: list[tuple[float, str]] = []
        for root in self.doc_folders[:6]:
            try:
                for e in os.scandir(root):
                    if e.is_file() and os.path.splitext(e.name)[1].lower() in (".pdf", ".docx", ".pptx", ".txt"):
                        files.append((e.stat().st_mtime, e.name))
            except OSError:
                continue
        out = []
        for _m, name in sorted(files, reverse=True)[:30]:
            words = [w for w in re.split(r"[^A-Za-z]+", os.path.splitext(name)[0]) if len(w) >= 3]
            if words:
                out.append(" ".join(words[:4]))
        return out[:20]

    def words(self) -> list[str]:
        seen: dict[str, str] = {}
        for w in self.names + self.learned() + self.seed + self._project_names() + self._document_names():  # learned words win
            seen.setdefault(w.lower(), w)
        return list(seen.values())

    def prompt(self) -> str:
        """'Neko. Words I use: A, B, C.' cut to fit; rebuilt only when the learned file changes."""
        try:
            stamp = os.path.getmtime(self.path)
        except OSError:
            stamp = 0.0
        with self._lock:
            stamp += int(__import__("time").time() // 600)  # document names change: rebuild every 10 min
            if self._cache and self._cache[0] == stamp:
                return self._cache[1]
            lead = (self.names[0] + ". ") if self.names else ""
            text, used = lead + "Words I use:", 0
            for w in self.words()[len(self.names[:1]):]:
                if len(text) + len(w) + 2 > MAX_PROMPT_CHARS:
                    break
                text += ("," if used else "") + " " + w
                used += 1
            out = text + "." if used else lead.strip()
            self._cache = (stamp, out)
            return out

    def add(self, phrase: str) -> str:
        """Learn a word or name the user taught. Returns the cleaned phrase ('' if unusable)."""
        clean = re.sub(r"[^\w '\-&.]", " ", phrase, flags=re.UNICODE)
        clean = re.sub(r"\s+", " ", clean).strip(" .'-")[:60]
        if len(clean) < 2:
            return ""
        if clean.lower() in (w.lower() for w in self.learned()):
            return clean
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            if self.path.stat().st_size == 0:
                fh.write("# Words Neko should hear correctly (one per line). Edit or delete freely.\n")
            fh.write(clean + "\n")
            self._cache = None
        return clean


def vocabulary_for(settings: object) -> Vocabulary:
    s = settings
    return Vocabulary(Path(s.data_dir) / "vocabulary.txt", seed=list(getattr(s.voice, "vocabulary", []) or []),  # type: ignore[attr-defined]
                      folders=list(s.tools.writable_roots),  # type: ignore[attr-defined]
                      doc_folders=[r for r in s.tools.allowed_roots if len(r.rstrip("\\/")) > 3],  # type: ignore[attr-defined]
                      names=[((getattr(s.voice, "wake_names", None) or ["neko"])[0]).capitalize(),  # type: ignore[attr-defined]
                             getattr(s.app, "user_name", "")])  # type: ignore[attr-defined]
