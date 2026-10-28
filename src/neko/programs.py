"""Your own programs: Neko learns them once, then runs them when you ask (also from your phone).

* "what programs do I have?"            - lists runnable things in your projects folder (default D:\\PROJECT)
* "learn to use Traid" / "add my program Print SOFT"
                                          - finds the entry point (.py / .exe / .bat / .ps1 / package.json
                                            script), reads its README / docstring (never runs it to find out),
                                            and asks you once before adding it (Level 2)
* "run Traid", "run Traid with --report daily", "open Print SOFT", "start HISAB"
                                          - command-line programs: she runs them (timeout) and tells you the
                                            result; windows apps, servers and web apps start in the background
                                            (web apps open in the browser)
* "stop HISAB"                           - stops what she started
* "always allow Traid"                   - no more approval for that one program (a narrow standing rule,
                                            itself approved by you); otherwise each run asks (Level 2)
* "forget my program Traid", "which programs can you run?"

Rules: only files inside the projects folder; argument lists, never shell strings; program output is
shown to you, never treated as instructions; nothing runs as administrator.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .core.errors import PermissionDeniedError, ToolError
from .core.types import RiskLevel
from .tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

DEFAULT_ROOT = r"D:\PROJECT"
SKIP_DIRS = {".venv", "venv", "env", "node_modules", ".git", "__pycache__", "site-packages", ".expo", "build",
             ".idea", ".vscode", "Lib", "Scripts", "tests", "test", "obj", "android", "ios", "packages", "Debug"}
_TOOLING = re.compile(r"^(gradlew|publish|build|deploy|install|setup|unins.*|uninstall|createdump|apphost|"
                      r"singlefilehost|lint|format|clean|test.*|migrate|bootstrap|update)$", re.I)
_INSTALLER = re.compile(r"setup|install|unins|updater", re.I)   # never "run" an installer by accident
_LAUNCHER = ("launch", "launcher", "start", "run")
_MAINISH = ("main", "app", "server", "gui")
KINDS = {".py": "python", ".exe": "exe", ".bat": "batch", ".cmd": "batch", ".ps1": "powershell"}
_BACKGROUND_PY = re.compile(r"^\s*(?:import|from)\s+(tkinter|PySide6|PyQt5|PyQt6|flask|fastapi|uvicorn|streamlit|"
                            r"gradio|pygame|customtkinter|wx|kivy)\b", re.M)
_NPM_PREFERRED = ("web", "dev", "start", "serve")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
_running: dict[str, subprocess.Popen[Any]] = {}


def _score(a: str, b: str) -> float:
    a, b = re.sub(r"[\W_]+", " ", a.lower()).strip(), re.sub(r"[\W_]+", " ", b.lower()).strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------- finding programs
def projects_root(settings: Any) -> Path:
    return Path(os.path.expandvars(getattr(getattr(settings, "tools", None), "programs_root", "") or DEFAULT_ROOT))


def _entry_files(project: Path, depth: int = 4) -> list[Path]:
    out: list[Path] = []

    def walk(d: Path, level: int) -> None:
        try:
            items = sorted(d.iterdir())
        except OSError:
            return
        for p in items:
            if p.is_dir():
                if level < depth and p.name not in SKIP_DIRS and not p.name.startswith("."):
                    walk(p, level + 1)
            elif p.suffix.lower() in KINDS and not p.name.startswith(("_", "test_", "setup.", "conftest")):
                out.append(p)
    walk(project, 0)
    return out


def _main_file(project: Path) -> Path | None:
    files = _entry_files(project)
    if not files:
        return None

    def rank(p: Path) -> tuple[int, int, int, float]:
        stem = p.stem.lower()
        tooling = 1 if _TOOLING.match(stem) or _INSTALLER.search(stem) else 0  # helpers and installers: never
        named = (0 if stem in _LAUNCHER else 1 if _score(stem, project.name) >= 0.85 else 2 if stem in _MAINISH
                 else 3)
        kind = {"exe": 0, "python": 1}.get(KINDS[p.suffix.lower()], 2)  # a finished app before its scripts
        return tooling, named, kind, -p.stat().st_mtime                  # newest build of the same app wins
    best = sorted(files, key=rank)[0]
    return None if _TOOLING.match(best.stem) or _INSTALLER.search(best.stem) else best


def candidates(settings: Any) -> list[dict[str, Any]]:
    """Runnable things in the projects folder (one best guess per project + its npm scripts)."""
    root = projects_root(settings)
    found: list[dict[str, Any]] = []
    if not root.is_dir():
        return found
    for project in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if project.name in ("N.E.K.O",):
            continue
        main = _main_file(project)
        if main is not None:
            found.append({"name": project.name, "kind": KINDS[main.suffix.lower()], "path": str(main),
                          "cwd": str(main.parent)})
        pkg = project / "package.json"
        if pkg.exists():
            try:
                scripts = json.loads(pkg.read_text(encoding="utf-8-sig")).get("scripts") or {}
            except (OSError, ValueError):
                scripts = {}
            script = next((s for s in _NPM_PREFERRED if s in scripts), None)
            if script:
                found.append({"name": project.name + (" web" if main is not None else ""), "kind": "npm",
                              "path": str(pkg), "cwd": str(project), "script": script,
                              "url": _guess_url(str(scripts[script]))})
    return found


def _guess_url(cmd: str) -> str:
    m = re.search(r"--port[ =](\d{2,5})", cmd)
    if m:
        return f"http://localhost:{m.group(1)}"
    if "expo" in cmd:
        return "http://localhost:8081"
    if "vite" in cmd:
        return "http://localhost:5173"
    if "next" in cmd:
        return "http://localhost:3000"
    return ""


def describe(entry: dict[str, Any]) -> str:
    """What the program is, from its README / docstring / package.json (read, never executed)."""
    path = Path(entry["path"])
    folder = path.parent
    for name in ("README.md", "readme.md", "README.txt", "README"):
        p = folder / name
        if not p.exists() and folder.parent != folder:
            p = folder.parent / name
        if p.exists():
            text = re.sub(r"[#*`>\[\]]", "", p.read_text(encoding="utf-8", errors="replace"))
            return re.sub(r"\s+", " ", text).strip()[:600]
    if path.suffix == ".py":
        m = re.match(r'\s*(?:#.*\n)*\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', path.read_text(encoding="utf-8",
                                                                                     errors="replace"), re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()[:600]
    if path.name == "package.json":
        try:
            return str(json.loads(path.read_text(encoding="utf-8-sig")).get("description", ""))[:600]
        except (OSError, ValueError):
            return ""
    return ""


# ---------------------------------------------------------------------- the registry (your approved programs)
class Programs:
    def __init__(self, settings: Any) -> None:
        self.s = settings
        self.path = Path(settings.data_dir) / "programs.json"
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def find(self, name: str) -> dict[str, Any] | None:
        best = max(((_score(name, n), e) for n, e in self.load().items()), default=None, key=lambda x: x[0])
        return best[1] if best and best[0] >= 0.8 else None

    def add(self, entry: dict[str, Any]) -> None:
        with self._lock:
            data = self.load()
            data[entry["name"]] = entry
            self._save(data)

    def remove(self, name: str) -> bool:
        with self._lock:
            data = self.load()
            hit = self.find(name)
            if hit is None:
                return False
            data.pop(hit["name"], None)
            self._save(data)
            return True


def _inside_root(settings: Any, path: str) -> Path:
    p = Path(path).resolve()
    root = projects_root(settings).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise PermissionDeniedError(f"{p} is outside {root}",
                                    user_message=f"I only run your programs from {root}.") from None
    if not p.exists():
        raise ToolError(f"{p} doesn't exist any more")
    return p


def _python_for(script: Path, root: Path) -> list[str]:
    for d in [script.parent, *script.parents]:
        for venv in (".venv", "venv", "env"):
            py = d / venv / "Scripts" / "python.exe"
            if py.exists():
                return [str(py)]
        if d == root:
            break
    if shutil.which("py"):
        return [shutil.which("py") or "py", "-3"]
    return [shutil.which("python") or "python"]


def command_for(entry: dict[str, Any], args: list[str], settings: Any) -> tuple[list[str], Path, bool]:
    """(argument list, working folder, background?) - never a shell string."""
    p = _inside_root(settings, entry["path"])
    cwd = _inside_root(settings, entry.get("cwd") or str(p.parent))
    kind = entry["kind"]
    if kind == "python":
        bg = bool(entry.get("background")) or bool(_BACKGROUND_PY.search(p.read_text(encoding="utf-8",
                                                                                   errors="replace")[:20000]))
        return [*_python_for(p, projects_root(settings).resolve()), str(p), *args], cwd, bg
    if kind == "exe":
        return [str(p), *args], cwd, True
    if kind == "batch":
        return ["cmd.exe", "/d", "/c", "call", str(p), *args], cwd, bool(entry.get("background"))
    if kind == "powershell":
        return (["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(p), *args], cwd,
                bool(entry.get("background")))
    if kind == "npm":
        npm = shutil.which("npm.cmd") or r"C:\Program Files\nodejs\npm.cmd"
        return [npm, "run", entry.get("script", "start"), *args], cwd, True
    raise ToolError(f"unknown program kind {kind}")


def _check_args(args: list[Any]) -> list[str]:
    if len(args) > 30 or any(not isinstance(a, str) or len(a) > 500 or "\x00" in a for a in args):
        raise PermissionDeniedError("program arguments must be a few short pieces of text")
    return list(args)


# ---------------------------------------------------------------------- tools
def _register(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    entry = dict(args["entry"])
    _inside_root(ctx.settings, entry["path"])
    entry["kind"] = entry.get("kind") if entry.get("kind") in (*KINDS.values(), "npm") else "exe"
    entry["added"] = time.strftime("%Y-%m-%d")
    Programs(ctx.settings).add(entry)
    return ToolResult(True, f"Added {entry['name']}", {"name": entry["name"]})


def _verify_register(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    return Programs(ctx.settings).find(args["entry"]["name"]) is not None, "saved in programs.json"


def _run(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    entry = Programs(ctx.settings).find(args["name"])
    if entry is None:
        return ToolResult(False, f"I don't know a program called {args['name']} yet - say \"learn to use {args['name']}\"")
    cmd, cwd, background = command_for(entry, _check_args(args.get("args") or []), ctx.settings)
    if background:
        old = _running.get(entry["name"])
        if old is not None and old.poll() is None:
            return ToolResult(True, f"{entry['name']} is already running", {"pid": old.pid, "background": True})
        flags = _NEW_GROUP | (0 if entry["kind"] == "exe" else _NO_WINDOW if entry["kind"] == "npm" else 0)
        proc = subprocess.Popen(cmd, cwd=str(cwd), shell=False, creationflags=flags,  # noqa: S603 - argument list
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        _running[entry["name"]] = proc
        url = entry.get("url", "")
        if url:
            threading.Thread(target=_open_when_ready, args=(url, proc), daemon=True).start()
        return ToolResult(True, f"Started {entry['name']}" + (f" - opening {url} when it's ready" if url else ""),
                          {"pid": proc.pid, "background": True, "name": entry["name"]})
    timeout = float(entry.get("timeout_s") or 300)
    proc = subprocess.Popen(cmd, cwd=str(cwd), shell=False, creationflags=_NO_WINDOW,  # noqa: S603
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace")
    ctx.token.on_cancel(proc.kill)
    try:
        out, _ = proc.communicate(timeout=min(timeout, ctx.token.remaining() or timeout))
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        out = (proc.communicate()[0] or "") + "\n[stopped: it ran too long]"
    tail = "\n".join((out or "").strip().splitlines()[-25:])[-3000:]
    return ToolResult(proc.returncode == 0, f"{entry['name']} finished (exit code {proc.returncode})",
                      {"exit_code": proc.returncode, "output": tail, "background": False})


def _open_when_ready(url: str, proc: subprocess.Popen[Any], wait_s: float = 90) -> None:
    import urllib.request

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            urllib.request.urlopen(url, timeout=2)  # noqa: S310 - localhost address you registered
            os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606
            return
        except OSError:
            time.sleep(2)


def _verify_run(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    d = result.data or {}
    if d.get("background"):
        time.sleep(1.5)
        proc = _running.get(d.get("name", ""))
        alive = proc is not None and proc.poll() is None
        return alive or proc is None, "it is running" if alive else "it stopped right after starting"
    return d.get("exit_code") == 0, f"exit code {d.get('exit_code')}"


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20, shell=False,
                   creationflags=_NO_WINDOW)


def _stop(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    entry = Programs(ctx.settings).find(args["name"])
    proc = _running.get(entry["name"]) if entry else None
    if proc is None or proc.poll() is not None:
        return ToolResult(False, f"I didn't start {args['name']}, or it has already stopped")
    _kill_tree(proc.pid)
    return ToolResult(True, f"Stopped {entry['name']}", {"name": entry["name"]})


def _verify_stop(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    proc = _running.get((result.data or {}).get("name", ""))
    time.sleep(0.5)
    return proc is None or proc.poll() is not None, "process ended"


def register_program_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="register_program", description="Add one of the user's own programs (inside their projects folder).",
        params={"entry": {"type": "object", "required": True}}, handler=_register, risk=RiskLevel.MATERIAL,
        category="scripts", side_effects="lets Neko run this program when you ask", verifier=_verify_register,
        summarize=lambda a: (f"Add your program \"{a['entry'].get('name')}\" ({a['entry'].get('kind')}): "
                             f"{a['entry'].get('path')}"), timeout_s=10,
    ))
    registry.register(ToolSpec(
        name="run_program", description="Run or start one of the user's registered programs.",
        params={"name": {"type": "string", "required": True, "max_length": 120},
                "args": {"type": "array", "default": []}},
        handler=_run, risk=RiskLevel.MATERIAL, category="scripts", reversible=False, verifier=_verify_run,
        side_effects="runs your program", timeout_s=900,
        summarize=lambda a: f"Run your program {a['name']}" + (f" with {' '.join(a.get('args') or [])}"
                                                                if a.get("args") else ""),
    ))
    registry.register(ToolSpec(
        name="stop_program", description="Stop a program that Neko started.",
        params={"name": {"type": "string", "required": True, "max_length": 120}},
        handler=_stop, risk=RiskLevel.LOW, category="scripts", side_effects="stops a program",
        verifier=_verify_stop, timeout_s=30,
    ))


# ---------------------------------------------------------------------- what you say
_LIST = re.compile(r"\b(what|which|show|list|scan)\b.{0,25}\b(programs?|apps?|projects?|tools?)\b.{0,30}"
                   r"\b(have|got|run|know|use|there|folder)\b|^\W*scan my projects\W*$", re.I)
_LEARN = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:learn (?:how )?to (?:use|run|open)|add (?:my )?(?:program|app|"
                    r"tool|project)|register (?:my )?(?:program|app)?)\s+(?:my\s+|the\s+)?(?:program\s+|app\s+)?"
                    r"(?P<name>.+?)\W*$", re.I)
_RUN = re.compile(r"^\W*(?:neko\W+)?(?:please\s+|can you\s+|could you\s+)?(?P<verb>run|start|open|launch)\s+"
                  r"(?:my\s+|the\s+)?(?P<name>.+?)(?:\s+(?:with|using|args?)\s+(?P<args>.+?))?\W*$", re.I)
_STOP = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:stop|close|kill|quit)\s+(?:my\s+|the\s+)?(?P<name>.+?)\W*$", re.I)
_ALWAYS = re.compile(r"^\W*(?:neko\W+)?always allow\s+(?:my\s+|the\s+)?(?P<name>.+?)\W*$", re.I)
_FORGET = re.compile(r"^\W*(?:neko\W+)?(?:forget|remove)\s+(?:my\s+)?(?:program|app)\s+(?P<name>.+?)\W*$", re.I)


def attach(neko: Any) -> Programs:
    register_program_tools(neko.tools)
    reg = Programs(neko.settings)

    def ctx_for(task: Any, token: Any) -> ToolContext:
        return ToolContext(token=token, paths=neko.paths, task_id=getattr(task, "id", None), settings=neko.settings)

    def handle(text: str, conv: str, task: Any, token: Any) -> tuple[str, str] | None:
        t = text.strip()
        if _LIST.search(t) and len(t.split()) <= 12:
            mine = reg.load()
            found = [c for c in candidates(neko.settings) if c["name"] not in mine]
            lines = [f"- {n} ({e['kind']})" for n, e in mine.items()]
            more = [f"- {c['name']} ({c['kind']}: {Path(c['path']).name})" for c in found]
            return ((("Programs I can run:\n" + "\n".join(lines)) if lines else "I haven't learned any of your "
                     "programs yet.") + (("\n\nFound in your projects (say \"learn to use <name>\"):\n"
                                          + "\n".join(more)) if more else "")), "neutral"
        if (m := _LEARN.match(t)):
            want = m.group("name").strip('"')
            path = Path(want)
            if path.suffix.lower() in KINDS and path.is_absolute():   # you named the exact file
                p = _inside_root(neko.settings, want)
                project = p.relative_to(projects_root(neko.settings).resolve()).parts[0]
                pool = [{"name": project, "kind": KINDS[p.suffix.lower()], "path": str(p), "cwd": str(p.parent)}]
                want = project
            else:
                pool = candidates(neko.settings)
            best = max(((_score(want, c["name"]), c) for c in pool), default=None, key=lambda x: x[0])
            if not best or best[0] < 0.6:
                names = ", ".join(c["name"] for c in pool[:12])
                return f"I couldn't find \"{want}\" in {projects_root(neko.settings)}. I see: {names}.", "curious"
            entry = dict(best[1])
            entry["about"] = describe(entry)
            res = neko.executor.run("register_program", {"entry": entry}, ctx_for(task, token))
            if not res.ok:
                return f"I didn't add it: {res.summary}.", "sad"
            how = ("I'll open it in the background" if entry["kind"] in ("exe", "npm") else
                   "I'll run it and tell you what it prints")
            about = f"\nWhat it is: {entry['about'][:200]}" if entry.get("about") else ""
            return (f"Learned {entry['name']} ({Path(entry['path']).name}). Say \"run {entry['name']}\" any time - "
                    f"{how}.{about}\nFor buttons inside it, ask me to click them, then \"save that as ...\" to "
                    "make it a skill."), "happy"
        if (m := _ALWAYS.match(t)):
            entry = reg.find(m.group("name"))
            if entry is None:
                return None
            from .core.types import RiskLevel as R

            req_ok = neko.executor.policy.request_approval  # the standing rule itself needs your OK
            from .security.policy import ApprovalRequest

            req = ApprovalRequest(tool="run_program", risk=R.MATERIAL, args={"name": entry["name"]},
                                  summary=f"Let me run {entry['name']} from now on without asking each time",
                                  side_effects="no approval for this one program for 30 days", reversible=True)
            if not req_ok(req, token):
                return "Okay, I'll keep asking each time.", "calm"
            neko.policy.add_standing_rule("run_program", {"equals": {"name": entry["name"]}},
                                          risk=R.MATERIAL, days=30)
            return f"Done - I'll run {entry['name']} without asking for the next 30 days.", "happy"
        if (m := _FORGET.match(t)):
            return ((f"Forgot {m.group('name')}.", "calm") if reg.remove(m.group("name")) else
                    (f"I don't have a program called {m.group('name')}.", "neutral"))
        if (m := _STOP.match(t)) and (entry := reg.find(m.group("name"))) is not None:
            res = neko.executor.run("stop_program", {"name": entry["name"]}, ctx_for(task, token))
            return (res.summary + ".", "calm" if res.ok else "neutral")
        if (m := _RUN.match(t)) and (entry := reg.find(m.group("name"))) is not None:
            args = shlex.split(m.group("args"), posix=False) if m.group("args") else []
            res = neko.executor.run("run_program", {"name": entry["name"], "args": args}, ctx_for(task, token))
            out = (res.data or {}).get("output", "") if isinstance(res.data, dict) else ""
            if not res.ok and "approve" in res.summary:
                return res.summary, "calm"
            return (res.summary + "." + (f"\n\nWhat it printed:\n{out}" if out else "")), ("happy" if res.ok else "sad")
        return None

    neko.coordinator.extensions.append(handle)
    return reg


__all__ = ["Programs", "attach", "candidates", "command_for", "describe", "register_program_tools"]
