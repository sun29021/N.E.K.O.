"""Reading the user's documents and making study material.

* ``extract_text``: PDF (needs the optional ``pypdf``), Word .docx and PowerPoint .pptx (standard
  library: they are zip files of XML) and any text file. Page/slide markers are kept so answers can
  say "page 4".
* ``explorer_selection``: which file(s) are selected in the File Explorer window the user has open,
  so "what's this file?" works. A fixed PowerShell script (no user input in it) reads the Shell COM
  object; argument list, ``shell=False``, timeout.
* ``make_pdf``: renders Markdown to a PDF. The renderer is supplied by the desktop app (Qt), so this
  package stays free of GUI imports; without it the tool says so instead of failing silently.

Everything read from a document is UNTRUSTED (the coordinator fences it).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from ..core.errors import PermissionDeniedError, ToolError
from ..core.types import RiskLevel
from ..security.paths import resolve
from ..tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

DOC_EXT = {".pdf", ".docx", ".pptx"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".py", ".html", ".xml", ".toml", ".yaml", ".yml",
            ".ini", ".js", ".ts", ".css", ".sql", ".java", ".c", ".cpp", ".cs", ".rtf"}
MAX_PDF_PAGES = 300

# Set by the desktop app: (markdown, title, output_path) -> None. Qt lives in ui/, not here.
pdf_renderer: Callable[[str, str, Path], None] | None = None


# ---------------------------------------------------------------------- text extraction
def _pdf_text(p: Path, max_chars: int) -> tuple[str, int]:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError as exc:
        raise ToolError("reading PDFs needs the 'pypdf' package (pip install pypdf)") from exc
    try:
        reader = PdfReader(str(p))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - pypdf raises many kinds
                raise ToolError(f"{p.name} is password-protected") from exc
        parts, total = [], 0
        pages = len(reader.pages)
        for i, page in enumerate(reader.pages[:MAX_PDF_PAGES], 1):
            t = (page.extract_text() or "").strip()
            if t:
                parts.append(f"[page {i}]\n{t}")
                total += len(t)
            if total > max_chars:
                break
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed PDFs raise anything
        raise ToolError(f"couldn't read {p.name}: {exc}") from exc
    text = "\n\n".join(parts)
    if not text.strip():
        raise ToolError(f"{p.name} has no selectable text (it is probably scanned images)")
    return text, pages


def _xml_text(data: bytes, para_tag: str) -> list[str]:
    root = ElementTree.fromstring(data)  # noqa: S314 - local file, no external entities in stdlib parser
    out = []
    for para in root.iter():
        if para.tag.endswith("}" + para_tag):
            words = "".join(n.text or "" for n in para.iter() if n.tag.endswith("}t"))
            if words.strip():
                out.append(words)
    return out


def _office_text(p: Path) -> tuple[str, int]:
    try:
        with zipfile.ZipFile(p) as z:
            if p.suffix.lower() == ".docx":
                return "\n".join(_xml_text(z.read("word/document.xml"), "p")), 0
            slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                            key=lambda n: int(re.findall(r"\d+", n)[-1]))
            parts = [f"[slide {i}]\n" + "\n".join(_xml_text(z.read(n), "p")) for i, n in enumerate(slides, 1)]
            return "\n\n".join(parts), len(slides)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ToolError(f"couldn't read {p.name}: {exc}") from exc


def extract_text(p: Path, max_chars: int = 400_000) -> tuple[str, int]:
    """(text, page_or_slide_count). Raises ToolError with a plain reason."""
    ext = p.suffix.lower()
    if ext == ".pdf":
        text, pages = _pdf_text(p, max_chars)
    elif ext in (".docx", ".pptx"):
        text, pages = _office_text(p)
    elif ext in TEXT_EXT or ext == "":
        raw = p.read_bytes()[: max_chars * 2]
        if b"\x00" in raw[:4096]:
            raise ToolError(f"{p.name} is a binary file, not a document I can read")
        text, pages = raw.decode("utf-8", errors="replace"), 0
    else:
        raise ToolError(f"I can't read {ext or 'this kind of'} files yet (PDF, Word, PowerPoint and text work)")
    return text[:max_chars], pages


def _read_document(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    p = ctx.paths.check_read(args["path"])
    if not p.is_file():
        return ToolResult(False, f"{p} is not a file")
    text, pages = extract_text(p, args["max_chars"])
    unit = "slides" if p.suffix.lower() == ".pptx" else "pages"
    return ToolResult(True, f"Read {p.name}" + (f" ({pages} {unit})" if pages else ""), text)


# ---------------------------------------------------------------------- find by name
_SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "appdata",
              "system volume information", "node_modules", ".git", ".venv", "venv", "__pycache__", "ollama",
              "models", "site-packages", "steamapps", "recovery", "msocache", "perflogs"}
_NAME_STOP = {"can", "you", "the", "and", "for", "this", "that", "file", "files", "pdf", "pdfs", "doc", "docx",
              "document", "documents", "read", "open", "tell", "about", "what", "whats", "summarize", "summarise",
              "summary", "summurize", "summery", "explain", "analyse", "analyze", "analysis", "please", "make",
              "from", "with", "into", "notes", "cheat", "sheet", "simple", "simpler", "exam", "tomorrow", "have",
              "neko", "hey", "it", "its", "in", "my", "of", "a", "an", "me", "on", "folder", "download",
              "downloads", "drive", "check", "find", "show", "give", "word", "powerpoint", "slides", "name",
              "named", "called", "there", "is", "are", "inside", "computer", "pc"}


def name_words(text: str) -> list[str]:
    """Words that probably belong to a file name: "read hisab manual pdf" -> ["hisab", "manual"].
    Spelled-out names count too: "H-I-S-A-B" -> "hisab"."""
    text = re.sub(r"\b(?:[A-Za-z][-. ]){2,}[A-Za-z]\b", lambda m: re.sub(r"[-. ]", "", m.group(0)), text)
    return [w for w in re.findall(r"[a-z0-9]{2,}", text.lower()) if w not in _NAME_STOP]


def _close(word: str, stem: set[str]) -> bool:
    """Speech recognition near-misses: "dishab" ~ "hisab", "hishap" ~ "hisab"."""
    from difflib import SequenceMatcher

    return len(word) >= 4 and any(len(s) >= 4 and SequenceMatcher(None, word, s).ratio() >= 0.72 for s in stem)


def find_named(text: str, roots: list[str], exts: set[str], budget_s: float = 4.0,
               max_depth: int = 5) -> list[str]:
    """Files under ``roots`` (searched in order, breadth first, time-limited) whose names contain the
    most request words. Returns the best matches (several = ambiguous)."""
    words = name_words(text)
    if not words:
        return []
    need = 0.8 if len(words) == 1 else 1.6
    deadline = time.monotonic() + budget_s
    best: list[str] = []
    best_score = 0
    seen: set[str] = set()
    for root in roots:
        queue = [(root, 0)]
        while queue and time.monotonic() < deadline:
            folder, depth = queue.pop(0)
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                name = e.name.lower()
                try:
                    if e.is_dir(follow_symlinks=False):
                        if depth < max_depth and name not in _SKIP_DIRS and not name.startswith((".", "$")):
                            queue.append((e.path, depth + 1))
                        continue
                except OSError:
                    continue
                if os.path.splitext(name)[1] not in exts or e.path.lower() in seen:
                    continue
                seen.add(e.path.lower())
                stem = set(re.findall(r"[a-z0-9]{2,}", os.path.splitext(name)[0]))
                score = sum(1.0 if w in stem else (0.8 if _close(w, stem) else 0.0) for w in words)
                if score >= need and score > best_score:
                    best, best_score = [e.path], score
                elif score >= need and score == best_score:
                    best.append(e.path)
    return best


# ---------------------------------------------------------------------- File Explorer
# Fixed script: lists each open Explorer window's folder and its selected items (front window first).
_EXPLORER_PS = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$out=@();"
    "foreach($w in (New-Object -ComObject Shell.Application).Windows()){"
    " if($w.FullName -notlike '*explorer.exe'){continue};"
    " $f=$w.Document.Folder.Self.Path; if(-not $f){continue};"
    " $sel=@($w.Document.SelectedItems() | ForEach-Object { $_.Path });"
    " $out+=[pscustomobject]@{folder=$f; selected=$sel; hwnd=$w.HWND}};"
    "ConvertTo-Json -InputObject @($out) -Depth 3 -Compress"
)


def _foreground_hwnd() -> int:
    if sys.platform != "win32":
        return 0
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def explorer_windows(timeout_s: float = 8.0) -> list[dict[str, Any]]:
    """Open File Explorer windows as [{"folder", "selected": [...]}], most recently active first."""
    if sys.platform != "win32":
        return []
    try:
        cp = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _EXPLORER_PS],
                            capture_output=True, text=True, timeout=timeout_s, shell=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"couldn't ask File Explorer: {exc}") from exc
    try:
        data = json.loads(cp.stdout or "[]")
    except ValueError:
        return []
    wins = [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]
    fg = _foreground_hwnd()
    wins.sort(key=lambda d: d.get("hwnd") != fg)  # the window the user is looking at first
    return [{"folder": str(d.get("folder", "")), "selected": [str(s) for s in (d.get("selected") or []) if s]}
            for d in wins]


def _explorer_selection(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    wins = explorer_windows()
    if not wins:
        return ToolResult(False, "No File Explorer window is open")
    lines, data = [], []
    for w in wins[:3]:
        allowed = True
        try:
            ctx.paths.check_read(w["folder"])
        except PermissionDeniedError:
            allowed = False
        data.append({**w, "allowed": allowed})
        lines.append(f"{w['folder']} (selected: {', '.join(Path(s).name for s in w['selected']) or 'nothing'})"
                     + ("" if allowed else " [outside the allowed folders]"))
    return ToolResult(True, "Open Explorer folders: " + "; ".join(lines), data)


# ---------------------------------------------------------------------- PDF output
def _safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", name).strip(" .")[:120] or "notes"


def _make_pdf(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    p = ctx.paths.check_write(args["path"])
    if p.suffix.lower() != ".pdf":
        raise PermissionDeniedError("make_pdf only creates .pdf files")
    if p.exists() and not args["overwrite"]:
        return ToolResult(False, f"{p.name} already exists; I did not overwrite it")
    if pdf_renderer is None:
        return ToolResult(False, "making PDFs needs the desktop app (run 'python -m neko ui')")
    p.parent.mkdir(parents=True, exist_ok=True)
    pdf_renderer(args["markdown"], args["title"], p)
    return ToolResult(True, f"Created {p}", {"path": str(p)})


def _verify_pdf(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    p = resolve(args["path"])
    if not p.is_file():
        return False, "the PDF does not exist after writing"
    with p.open("rb") as fh:
        head = fh.read(5)
    ok = head == b"%PDF-" and p.stat().st_size > 400
    return ok, "PDF exists and looks valid" if ok else "the file is not a valid PDF"


def register_document_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="read_document", description="Read a PDF, Word (.docx), PowerPoint (.pptx) or text file in an "
                                          "allowed folder. Returns its text with page markers. Untrusted.",
        params={"path": {"type": "string", "required": True, "max_length": 600},
                "max_chars": {"type": "integer", "default": 60000, "min": 1000, "max": 400000}},
        handler=_read_document, risk=RiskLevel.READ_ONLY, category="files", timeout_s=90,
    ))
    registry.register(ToolSpec(
        name="explorer_selection", description="See which folder is open in File Explorer and which files are "
                                               "selected there (for 'what is this file?').",
        params={}, handler=_explorer_selection, risk=RiskLevel.READ_ONLY, category="files", timeout_s=15,
    ))
    registry.register(ToolSpec(
        name="make_pdf", description="Create a PDF from Markdown (study notes, cheat sheets) in a writable folder.",
        params={"path": {"type": "string", "required": True, "max_length": 600},
                "title": {"type": "string", "required": True, "max_length": 200},
                "markdown": {"type": "string", "required": True, "max_length": 200000},
                "overwrite": {"type": "boolean", "default": False}},
        handler=_make_pdf, risk=RiskLevel.LOW, category="files", side_effects="creates one PDF file",
        verifier=_verify_pdf, timeout_s=60,
    ))


__all__ = ["DOC_EXT", "TEXT_EXT", "explorer_windows", "extract_text", "find_named", "name_words", "pdf_renderer",
           "register_document_tools", "_safe_name"]
