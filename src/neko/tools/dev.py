"""Developer tools: project analysis (local) and delegation to Claude Code (the real coding agent).

* ``analyze_project``: folder tree, languages, key files (README, manifests) - read-only, local.
* ``ask_claude_code``: runs the Claude Code CLI (``claude -p``) in a project folder.
  - read-only by default: Claude may only Read/Grep/Glob (it can't change anything);
  - with ``allow_edits``: Level 2 - you approve every run; Claude can edit files in that folder
    only (``--permission-mode acceptEdits``, no shell). The folder must be in tools.writable_roots.
  - Sends project content to Anthropic (cloud): needs ``privacy.allow_cloud_models = true``.
  - Uses your own Claude Code login/subscription; N.E.K.O. never handles your credentials.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from ..core.errors import PermissionDeniedError, ToolError
from ..core.types import RiskLevel
from .base import ToolContext, ToolRegistry, ToolResult, ToolSpec

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".idea", ".vscode",
             "bin", "obj", ".gradle", "target", ".next", ".cache"}
KEY_FILES = ("README.md", "README.txt", "README", "package.json", "pyproject.toml", "requirements.txt",
             "setup.py", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
             "Gemfile", "CMakeLists.txt", "Makefile", "docker-compose.yml", "Dockerfile", "AGENTS.md", "CLAUDE.md")
LANG = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript/React", ".jsx": "React",
        ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".cpp": "C++", ".c": "C", ".h": "C/C++ header",
        ".go": "Go", ".rs": "Rust", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".dart": "Dart",
        ".html": "HTML", ".css": "CSS", ".sql": "SQL", ".ps1": "PowerShell", ".vue": "Vue", ".xml": "XML"}


def _analyze(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = ctx.paths.check_read(args["path"])
    if not root.is_dir():
        return ToolResult(False, f"{root} is not a folder")
    langs: Counter[str] = Counter()
    tree: list[str] = []
    n_files = 0
    for dirpath, dirnames, filenames in os.walk(root):
        ctx.token.raise_if_cancelled()
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth <= 2 and len(tree) < 160:
            tree.append("  " * depth + (Path(dirpath).name + "/"))
            if depth <= 1:
                tree += ["  " * (depth + 1) + f for f in sorted(filenames)[:25]]
        for f in filenames:
            n_files += 1
            langs[LANG.get(Path(f).suffix.lower(), "")] += 1
        if n_files > 20000:
            break
    langs.pop("", None)
    keys = []
    budget = 14000
    for name in KEY_FILES:
        p = root / name
        if p.is_file() and budget > 0:
            text = p.read_text(encoding="utf-8", errors="replace")[: min(5000, budget)]
            budget -= len(text)
            keys.append(f"--- {name} ---\n{text}")
    summary = (f"Project: {root.name}\nPath: {root}\nFiles: {n_files}\nLanguages: "
               + ", ".join(f"{k} ({v})" for k, v in langs.most_common(6)) + "\n\nStructure:\n" + "\n".join(tree[:160])
               + "\n\nKey files:\n" + ("\n".join(keys) or "(no README or manifest found)"))
    return ToolResult(True, f"Analysed {root.name}: {n_files} files, mostly {langs.most_common(1)[0][0] if langs else 'unknown'}",
                      summary)


def find_claude() -> str | None:
    exe = shutil.which("claude")
    if exe:
        return exe
    for p in (Path.home() / ".local" / "bin" / "claude.exe", Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"):
        if p.is_file():
            return str(p)
    return None


def _claude(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    settings = ctx.settings
    if not getattr(getattr(settings, "privacy", None), "allow_cloud_models", False):
        raise PermissionDeniedError(
            "cloud disabled", user_message="Using Claude Code sends your project to Anthropic's cloud, and cloud "
            "services are turned off in privacy settings (privacy.allow_cloud_models).")
    folder = ctx.paths.check_write(args["folder"]) if args["allow_edits"] else ctx.paths.check_read(args["folder"])
    exe = find_claude()
    if exe is None:
        raise ToolError("Claude Code is not installed (claude CLI not found)")
    cmd = [exe, "-p", args["task"], "--output-format", "text"]
    if args["allow_edits"]:
        cmd += ["--permission-mode", "acceptEdits", "--allowedTools", "Read,Grep,Glob,Edit,Write,MultiEdit"]
    else:
        cmd += ["--allowedTools", "Read,Grep,Glob"]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("NEKO_REMOTE", "ELEVENLABS"))}
    proc = subprocess.Popen(cmd, cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,  # noqa: S603
                            encoding="utf-8", errors="replace", shell=False, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    ctx.token.on_cancel(proc.kill)
    try:
        out, err = proc.communicate(timeout=ctx.token.remaining() or 900)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return ToolResult(False, "Claude Code took too long and was stopped", (out or "")[-6000:])
    if proc.returncode != 0:
        return ToolResult(False, f"Claude Code failed (exit {proc.returncode}): {(err or out)[-300:]}")
    return ToolResult(True, f"Claude Code finished in {folder.name}" + (" (files may have changed)" if args["allow_edits"] else ""),
                      {"answer": out.strip()[-20000:], "folder": str(folder), "edits_allowed": args["allow_edits"]})


def _verify_claude(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    answer = (result.data or {}).get("answer", "")
    return bool(answer), "Claude Code returned an answer" if answer else "empty answer"


def register_dev_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="analyze_project", description="Look at a software project folder: structure, languages, README "
                                            "and manifest files. Use before suggesting features or changes.",
        params={"path": {"type": "string", "required": True, "description": "project folder path"}},
        handler=_analyze, risk=RiskLevel.READ_ONLY, category="files", timeout_s=60,
    ))
    registry.register(ToolSpec(
        name="ask_claude_code", description="Hand a coding task or deep code question to Claude Code (a strong "
                                            "cloud coding agent) running in a project folder.",
        params={"task": {"type": "string", "required": True, "max_length": 4000},
                "folder": {"type": "string", "required": True},
                "allow_edits": {"type": "boolean", "default": False}},
        handler=_claude, risk=RiskLevel.READ_ONLY, category="cloud", needs_network=True, timeout_s=900,
        side_effects="sends project content to Anthropic; may edit files when allow_edits is true",
        risk_fn=lambda a: RiskLevel.MATERIAL if a.get("allow_edits") else RiskLevel.READ_ONLY,
        verifier=_verify_claude,
        summarize=lambda a: (f"Let Claude Code {'CHANGE FILES in' if a.get('allow_edits') else 'read'} "
                             f"{a.get('folder')}: {a.get('task', '')[:200]}"),
    ))
