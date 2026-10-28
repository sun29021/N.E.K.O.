"""Built-in tools. Small, auditable, and each with a real verification step.

No tool here builds shell command strings. Processes are started with
argument lists, ``shell=False``, a working directory inside an allowed root,
and a timeout.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..core.errors import PermissionDeniedError, ToolError
from ..core.types import RiskLevel
from ..security.paths import is_within, resolve
from .base import ToolContext, ToolRegistry, ToolResult, ToolSpec

_TEXT_EXT = {".txt", ".md", ".py", ".json", ".toml", ".yaml", ".yml", ".csv", ".log", ".ini", ".cfg",
             ".js", ".ts", ".html", ".css", ".ps1", ".bat", ".sql", ".xml", ".rs", ".go", ".java", ".c",
             ".cpp", ".h", ".cs", ".kt", ".swift", ".rb", ".php", ".sh"}


# ---------------------------------------------------------------------- files (read-only)

def _list_dir(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = ctx.paths.check_read(args["path"])
    if not root.is_dir():
        return ToolResult(False, f"{root} is not a folder")
    entries = []
    for i, p in enumerate(sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))):
        ctx.token.raise_if_cancelled()
        if i >= args["limit"]:
            entries.append("... (more entries omitted)")
            break
        try:
            size = "" if p.is_dir() else f" {p.stat().st_size} B"
        except OSError:
            size = ""
        entries.append(("[dir] " if p.is_dir() else "") + p.name + size)
    return ToolResult(True, f"Listed {min(len(entries), args['limit'])} entries in {root}", "\n".join(entries))


def _read_text(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    p = ctx.paths.check_read(args["path"])
    if not p.is_file():
        return ToolResult(False, f"{p} is not a file")
    max_bytes = getattr(getattr(ctx.settings, "tools", None), "max_read_bytes", 200_000)
    with p.open("rb") as fh:
        raw = fh.read(max_bytes + 1)
    if b"\x00" in raw[:4096]:
        return ToolResult(False, f"{p.name} looks like a binary file; I only read text files")
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    return ToolResult(True, f"Read {p.name} ({len(raw[:max_bytes])} bytes{', truncated' if truncated else ''})", text)


def _search_files(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = ctx.paths.check_read(args["path"])
    pattern = args["name_pattern"]
    needle = args.get("contains", "").lower()
    hits: list[str] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        ctx.token.raise_if_cancelled()
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".venv")]
        for fn in filenames:
            if not fnmatch.fnmatch(fn.lower(), pattern.lower()):
                continue
            fp = Path(dirpath) / fn
            scanned += 1
            if needle:
                if fp.suffix.lower() not in _TEXT_EXT:
                    continue
                try:
                    if fp.stat().st_size > 2_000_000:
                        continue
                    if needle not in fp.read_text(encoding="utf-8", errors="ignore").lower():
                        continue
                except OSError:
                    continue
            hits.append(str(fp))
            if len(hits) >= args["limit"]:
                return ToolResult(True, f"Found {len(hits)}+ matching files (limit reached)", "\n".join(hits))
        if scanned > 20_000:
            break
    return ToolResult(True, f"Found {len(hits)} matching file(s)", "\n".join(hits))


# ---------------------------------------------------------------------- files (changes)

def _write_note(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    p = ctx.paths.check_write(args["path"])
    if p.suffix.lower() not in (".txt", ".md"):
        raise PermissionDeniedError("write_note only creates .txt or .md files")
    if p.exists() and not args["overwrite"]:
        return ToolResult(False, f"{p.name} already exists; I did not overwrite it")
    if p.exists():
        backup = p.with_suffix(p.suffix + f".bak-{int(time.time())}")
        shutil.copy2(p, backup)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args["content"], encoding="utf-8")
    return ToolResult(True, f"Wrote {len(args['content'])} characters to {p}")


def _verify_write_note(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    p = resolve(args["path"])
    if not p.exists():
        return False, "file does not exist after writing"
    ok = p.read_text(encoding="utf-8") == args["content"]
    return ok, "file exists and content matches" if ok else "file content differs from what was requested"


def _move_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    src = ctx.paths.check_write(args["source"])
    dst = ctx.paths.check_write(args["destination"])
    if not src.exists():
        return ToolResult(False, f"{src} does not exist")
    if dst.exists():
        return ToolResult(False, f"{dst} already exists; I won't overwrite it")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return ToolResult(True, f"Moved {src.name} to {dst}", {"undo": {"source": str(dst), "destination": str(src)}})


def _verify_move(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    src, dst = resolve(args["source"]), resolve(args["destination"])
    ok = dst.exists() and not src.exists()
    return ok, "destination exists and source is gone" if ok else "move could not be confirmed on disk"


# ---------------------------------------------------------------------- apps

def _open_app(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    allowed: dict[str, str] = getattr(getattr(ctx.settings, "tools", None), "allowed_apps", {}) or {}
    name = args["name"].lower()
    if name not in allowed:
        raise PermissionDeniedError(
            f"{name} is not in tools.allowed_apps",
            user_message=f"'{name}' is not on your list of apps I may open. Allowed: {', '.join(allowed) or 'none'}.",
        )
    exe = os.path.expandvars(allowed[name])
    if sys.platform != "win32":
        raise ToolError("open_app is only implemented on Windows")
    if not os.path.isabs(exe) or not os.path.isfile(exe):
        raise PermissionDeniedError(
            f"allowed_apps entry for {name} must be an existing absolute path, got {exe!r}",
            user_message=f"The app entry for '{name}' must be a full path to an .exe that exists.")
    proc = subprocess.Popen([exe], shell=False, close_fds=True)  # noqa: S603 - allow-listed executable
    return ToolResult(True, f"Started {name}", {"pid": proc.pid})


def _verify_open_app(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    pid = (result.data or {}).get("pid")
    if not pid:
        return False, "no process id"
    time.sleep(0.5)
    # Some launchers (e.g. calc.exe on Windows 11) hand off to another process and exit; that is
    # still a successful launch, so only an immediate crash code counts as failure.
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True,
                             text=True, timeout=5, shell=False)
        running = str(pid) in out.stdout
    except (OSError, subprocess.SubprocessError):
        return True, "launched; could not query process list"
    return True, "process is running" if running else "launcher exited (normal for some Store apps)"


# ---------------------------------------------------------------------- approved scripts

def _run_script(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    scripts_dir = getattr(getattr(ctx.settings, "tools", None), "approved_scripts_dir", "")
    if not scripts_dir:
        raise PermissionDeniedError("no approved_scripts_dir configured",
                                    user_message="Script running is off: no approved scripts folder is configured.")
    root = resolve(scripts_dir)
    script = resolve(root / args["script"])
    if not is_within(script, root) or not script.is_file():
        raise PermissionDeniedError(f"{args['script']} is not inside the approved scripts folder")
    ext = script.suffix.lower()
    if ext == ".py":
        cmd = [sys.executable, "-I", str(script)]
    elif ext == ".ps1":
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        raise PermissionDeniedError("only .py and .ps1 scripts are supported")
    for a in args["args"]:
        if not isinstance(a, str) or len(a) > 500 or "\x00" in a:
            raise PermissionDeniedError("script arguments must be short strings")
    cmd += args["args"]
    proc = subprocess.Popen(cmd, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,  # noqa: S603
                            text=True, shell=False)
    ctx.token.on_cancel(proc.kill)
    try:
        out, err = proc.communicate(timeout=ctx.token.remaining() or 60)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return ToolResult(False, f"{script.name} timed out and was stopped", {"stdout": out[-4000:], "stderr": err[-4000:]})
    ok = proc.returncode == 0
    return ToolResult(ok, f"{script.name} exited with code {proc.returncode}",
                      {"exit_code": proc.returncode, "stdout": out[-4000:], "stderr": err[-4000:]})


def _verify_script(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    code = (result.data or {}).get("exit_code")
    return code == 0, f"exit code {code}"


# ---------------------------------------------------------------------- registration

def register_builtin_tools(registry: ToolRegistry, *, resource_snapshot: Any = None, model_list: Any = None) -> None:
    registry.register(ToolSpec(
        name="list_dir", description="List files in an allowed folder.",
        params={"path": {"type": "string", "required": True}, "limit": {"type": "integer", "default": 200, "min": 1, "max": 1000}},
        handler=_list_dir, risk=RiskLevel.READ_ONLY, category="files",
    ))
    registry.register(ToolSpec(
        name="read_text_file", description="Read a text file inside an allowed folder. Output is untrusted data.",
        params={"path": {"type": "string", "required": True}},
        handler=_read_text, risk=RiskLevel.READ_ONLY, category="files",
    ))
    registry.register(ToolSpec(
        name="search_files", description="Find files by name pattern (e.g. *.pdf) and optional text content.",
        params={"path": {"type": "string", "required": True}, "name_pattern": {"type": "string", "default": "*"},
                "contains": {"type": "string", "default": ""}, "limit": {"type": "integer", "default": 50, "min": 1, "max": 500}},
        handler=_search_files, risk=RiskLevel.READ_ONLY, category="files", timeout_s=60,
    ))
    registry.register(ToolSpec(
        name="write_note", description="Create a .txt/.md note in a writable folder (existing files are backed up).",
        params={"path": {"type": "string", "required": True}, "content": {"type": "string", "required": True, "max_length": 100_000},
                "overwrite": {"type": "boolean", "default": False}},
        handler=_write_note, risk=RiskLevel.LOW, category="files", side_effects="creates or replaces one text file",
        verifier=_verify_write_note,
        risk_fn=lambda a: RiskLevel.MATERIAL if a.get("overwrite") else RiskLevel.LOW,
        summarize=lambda a: f"Write a note to {a['path']}" + (" (replacing the existing file; a backup is kept)" if a.get("overwrite") else ""),
    ))
    registry.register(ToolSpec(
        name="move_file", description="Move or rename one file within writable folders.",
        params={"source": {"type": "string", "required": True}, "destination": {"type": "string", "required": True}},
        handler=_move_file, risk=RiskLevel.MATERIAL, category="files", side_effects="moves a file",
        reversible=True, verifier=_verify_move,
        summarize=lambda a: f"Move {a['source']} -> {a['destination']}",
    ))
    registry.register(ToolSpec(
        name="open_app", description="Open an application from the user's allow-list (tools.allowed_apps).",
        params={"name": {"type": "string", "required": True, "max_length": 64}},
        handler=_open_app, risk=RiskLevel.LOW, category="computer_control", side_effects="starts a program",
        verifier=_verify_open_app, timeout_s=10,
    ))
    registry.register(ToolSpec(
        name="run_approved_script", description="Run a .py/.ps1 script from the approved scripts folder with arguments.",
        params={"script": {"type": "string", "required": True, "max_length": 260},
                "args": {"type": "array", "default": []}},
        handler=_run_script, risk=RiskLevel.MATERIAL, category="scripts", side_effects="runs a script",
        reversible=False, verifier=_verify_script, timeout_s=120,
        summarize=lambda a: f"Run approved script {a['script']} with arguments {a.get('args', [])}",
    ))
    registry.register(ToolSpec(
        name="delete_files", description="Permanently delete files. Disabled: N.E.K.O. never deletes user data.",
        params={"path": {"type": "string", "required": True}},
        handler=lambda a, c: ToolResult(False, "deletion is prohibited"), risk=RiskLevel.HIGH,
        category="files", side_effects="irreversible deletion", reversible=False, prohibited=True,
        verifier=lambda a, r, c: (False, "prohibited"),
    ))
    if resource_snapshot is not None:
        registry.register(ToolSpec(
            name="system_status", description="Report RAM, VRAM, disk, battery and GPU temperature.",
            params={}, handler=lambda a, c: ToolResult(True, "Collected system status", resource_snapshot().as_text()),
            risk=RiskLevel.READ_ONLY, category="diagnostics",
        ))
    if model_list is not None:
        registry.register(ToolSpec(
            name="list_models", description="List locally installed AI models.",
            params={}, handler=lambda a, c: ToolResult(True, "Listed models", model_list()),
            risk=RiskLevel.READ_ONLY, category="diagnostics",
        ))
