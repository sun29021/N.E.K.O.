"""Safe self-upgrades: checkpoint -> change -> test -> keep (as a commit) or undo automatically.

Used by "upgrade yourself so you can ..." (Claude Code makes the change) and three phone-friendly
actions, each a normal tool that goes through the permission policy:

* ``undo_upgrade``   - reverts the most recent self-upgrade commit (Level 2, asks first)
* ``restart_self``   - restarts N.E.K.O. so a change takes effect (Level 1)
* ``publish_update`` - sends the current version to your other PCs through your private GitHub repo
                       (Level 3: asks every time; from the phone it needs your PIN). Refuses if the repo
                       is reachable without signing in (i.e. it is public).

Git and Python are run with argument lists (no shell), with timeouts, only inside N.E.K.O.'s own folder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core.errors import ToolError
from .core.types import RiskLevel
from .tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "Self-upgrade: "
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
restarter: Callable[[], None] | None = None     # set by the desktop app (ui/updates.restart_neko)
before_restart: list[Callable[[], None]] = []    # e.g. the phone remembers to say "I'm back"


def _git_exe() -> str:
    for c in (shutil.which("git"), r"C:\Program Files\Git\cmd\git.exe"):
        if c and os.path.exists(c):
            return c
    raise ToolError("Git isn't installed, so I can't keep a safe checkpoint")


def git(*args: str, root: Path = ROOT, timeout: float = 60) -> tuple[int, str]:
    cp = subprocess.run([_git_exe(), *args], cwd=root, capture_output=True, text=True, timeout=timeout,
                        shell=False, creationflags=_NO_WINDOW, encoding="utf-8", errors="replace")
    return cp.returncode, (cp.stdout or "") + (cp.stderr or "")


def is_repo(root: Path = ROOT) -> bool:
    return (root / ".git").exists()


def head(root: Path = ROOT) -> str:
    code, out = git("rev-parse", "HEAD", root=root)
    return out.strip() if code == 0 else ""


def changed_files(root: Path = ROOT) -> list[str]:
    code, out = git("status", "--porcelain", root=root)
    return [ln[3:] for ln in out.splitlines() if ln.strip()] if code == 0 else []


def run_tests(root: Path = ROOT, timeout: float = 900) -> tuple[bool, str]:
    py = root / ".venv" / "Scripts" / "python.exe"
    exe = str(py) if py.exists() else sys.executable
    try:
        cp = subprocess.run([exe, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=root,
                            capture_output=True, text=True, timeout=timeout, shell=False, creationflags=_NO_WINDOW,
                            encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "the tests took too long"
    out = (cp.stdout or "") + (cp.stderr or "")
    ran = re.findall(r"^Ran \d+ tests?.*$|^(?:OK|FAILED).*$", out, re.M)
    return cp.returncode == 0, " ".join(ran[-2:]) or out[-300:]


# ---------------------------------------------------------------------- the upgrade transaction
class Checkpoint:
    """Remember where the code was; after a change either keep it as a commit or go back exactly."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        if not is_repo(root):
            raise ToolError("my folder isn't a Git copy, so I can't make a safe checkpoint")
        dirty = changed_files(root)
        if dirty:
            raise ToolError(f"there are unsaved changes in my code ({', '.join(dirty[:3])}...) - save (commit) "
                            "or undo them first, so I can undo my own change cleanly if needed")
        self.base = head(root)

    def changed(self) -> bool:
        return bool(changed_files(self.root)) or head(self.root) != self.base

    def rollback(self) -> None:
        git("reset", "--hard", self.base, root=self.root)
        git("clean", "-fd", "--", "src", "tests", "docs", "scripts", root=self.root)  # only files the change added

    def keep(self, request: str) -> str:
        """Commit the change (including any commits Claude Code made) as one self-upgrade."""
        git("add", "-A", root=self.root)
        if changed_files(self.root):
            msg = PREFIX + re.sub(r"\s+", " ", request).strip()[:120]
            code, out = git("-c", "user.name=N.E.K.O.", "-c", "user.email=neko@localhost", "commit", "-q", "-m",
                            msg + "\n\nRequested by the owner; made by Claude Code; tests passed.", root=self.root)
            if code != 0:
                raise ToolError(f"couldn't save the change: {out[-200:]}")
        return head(self.root)


def upgrade_transaction(request: str, change: Callable[[], Any], root: Path = ROOT) -> tuple[str, str]:
    """Run `change()` safely. Returns (status, detail): "kept" | "undone" | "unchanged"."""
    cp = Checkpoint(root)
    try:
        change()
    except Exception:
        if cp.changed():
            cp.rollback()
        raise
    if not cp.changed():
        return "unchanged", ""
    ok, detail = run_tests(root)
    if not ok:
        cp.rollback()
        return "undone", detail
    return "kept", cp.keep(request)[:10]


# ---------------------------------------------------------------------- tools
def last_upgrade(root: Path = ROOT) -> tuple[str, str] | None:
    """The newest self-upgrade that hasn't been undone yet."""
    code, out = git("log", "-n", "60", "--format=%H%x09%s", root=root)
    undone: list[str] = []
    for line in out.splitlines() if code == 0 else []:
        sha, _, subject = line.partition("\t")
        if subject.startswith(f'Revert "{PREFIX}'):
            undone.append(subject[len('Revert "'):-1])
        elif subject.startswith(PREFIX):
            if subject in undone:
                undone.remove(subject)
                continue
            return sha, subject[len(PREFIX):]
    return None


def _undo(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = Path(args.get("root") or ROOT)
    found = last_upgrade(root)
    if found is None:
        return ToolResult(False, "there's no self-upgrade to undo")
    sha, what = found
    Checkpoint(root)  # refuses when there are unsaved changes
    before = head(root)
    code, out = git("-c", "user.name=N.E.K.O.", "-c", "user.email=neko@localhost", "revert", "--no-edit", sha,
                    root=root)
    if code != 0:
        git("revert", "--abort", root=root)
        return ToolResult(False, f"later changes depend on it, so it can't be undone automatically ({out[-120:]})")
    ok, detail = run_tests(root)
    if not ok:
        git("reset", "--hard", before, root=root)
        return ToolResult(False, f"undoing it broke the tests, so I left everything as it was ({detail})")
    return ToolResult(True, f"Undid the upgrade \"{what}\"", {"before": before, "after": head(root), "root": str(root)})


def _verify_undo(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    d = result.data or {}
    now = head(Path(d.get("root") or ROOT))
    return now == d.get("after") and now != d.get("before"), f"code is now at {now[:10]}"


def _restart(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if restarter is None:
        return ToolResult(False, "restarting needs the desktop app")

    def later() -> None:
        time.sleep(4)  # let the reply reach you first
        for hook in before_restart:
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        restarter()

    threading.Thread(target=later, daemon=True, name="neko-restart").start()
    return ToolResult(True, "Restarting in a few seconds - back in about half a minute", {"scheduled": True})


def _verify_restart(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    return bool((result.data or {}).get("scheduled")), "restart scheduled (the new start is logged)"


def repo_is_private(root: Path = ROOT, timeout_s: float = 15) -> bool:
    """True only if GitHub says the repo doesn't exist for anonymous visitors (private = 404)."""
    code, url = git("remote", "get-url", "origin", root=root)
    m = re.search(r"github\.com[/:]([^/]+)/(.+?)(?:\.git)?\s*$", url.strip()) if code == 0 else None
    if not m:
        return False
    req = urllib.request.Request(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}",
                                 headers={"User-Agent": "NEKO"})
    try:
        urllib.request.urlopen(req, timeout=timeout_s)  # noqa: S310 - fixed https host
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except (urllib.error.URLError, OSError):
        return False
    return False  # readable without signing in: public


def _publish(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = Path(args.get("root") or ROOT)
    if not repo_is_private(root):
        return ToolResult(False, "I couldn't confirm your GitHub repo is private, so I didn't publish anything")
    script = root / "scripts" / "publish-update.ps1"
    try:
        cp = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                             "-Message", str(args.get("message") or "")], cwd=root, capture_output=True, text=True,
                            timeout=1200, shell=False, creationflags=_NO_WINDOW, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ToolResult(False, "publishing took too long")
    out = (cp.stdout or "") + (cp.stderr or "")
    if cp.returncode != 0:
        return ToolResult(False, f"not published: {out.strip().splitlines()[-1][:200] if out.strip() else 'failed'}")
    return ToolResult(True, "Published - your other PCs will offer the update", {"head": head(root), "root": str(root)})


def _verify_publish(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    d = result.data or {}
    root = Path(d.get("root") or ROOT)
    code, out = git("ls-remote", "origin", "refs/heads/main", root=root, timeout=60)
    remote = out.split()[0] if code == 0 and out.strip() else ""
    return remote == d.get("head"), f"GitHub main is at {remote[:10] or 'unknown'}"


def register_selfupdate_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="undo_upgrade", description="Undo N.E.K.O.'s most recent self-upgrade (then restart to use it).",
        params={}, handler=_undo, risk=RiskLevel.MATERIAL, category="general",
        side_effects="changes N.E.K.O.'s own code back", reversible=True, verifier=_verify_undo, timeout_s=1000,
    ))
    registry.register(ToolSpec(
        name="restart_self", description="Restart N.E.K.O. so a change takes effect.",
        params={}, handler=_restart, risk=RiskLevel.LOW, category="general",
        side_effects="N.E.K.O. closes and starts again", verifier=_verify_restart, timeout_s=10,
    ))
    registry.register(ToolSpec(
        name="publish_update", description="Send this version to the owner's other PCs via their private GitHub repo.",
        params={"message": {"type": "string", "default": "", "max_length": 200}},
        handler=_publish, risk=RiskLevel.HIGH, category="general", needs_network=True, reversible=False,
        side_effects="pushes N.E.K.O.'s code to your private GitHub repo; other PCs offer it as an update",
        verifier=_verify_publish, timeout_s=1300,
    ))


# ---------------------------------------------------------------------- what you say
_UNDO = re.compile(r"\b(undo|revert|roll ?back|cancel)\b.{0,20}\b(last |latest |your |the )*(self[- ]?)?(upgrade|update|"
                   r"change)\b", re.I)
_RESTART = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:restart|reboot|reload)\s+(?:yourself|neko|n\.e\.k\.o\.?|"
                      r"your ?self|the assistant)\W*$", re.I)
_PUBLISH = re.compile(r"\b(publish|push|send|share)\b.{0,25}\b(update|upgrade|new version)\b.{0,30}"
                      r"(office|other pcs?|github|everywhere)?", re.I)


def command(text: str) -> tuple[str, dict[str, Any]] | None:
    t = text.strip()
    if _RESTART.match(t):
        return "restart_self", {}
    if len(t.split()) <= 10 and _UNDO.search(t):
        return "undo_upgrade", {}
    if len(t.split()) <= 12 and _PUBLISH.search(t) and not re.search(r"\b(publish|send)\b.{0,10}\b(it|this) to\b", t, re.I):
        return "publish_update", {}
    return None


def attach(neko: Any) -> None:
    """Register the tools and let "restart yourself" / "undo the last upgrade" / "publish the update" work."""
    register_selfupdate_tools(neko.tools)

    def handle(text: str, conv: str, task: Any, token: Any) -> tuple[str, str] | None:
        found = command(text)
        if found is None:
            return None
        tool, args = found
        ctx = ToolContext(token=token, paths=neko.paths, task_id=getattr(task, "id", None), settings=neko.settings)
        res = neko.executor.run(tool, args, ctx)
        if not res.ok:
            return f"I didn't do it: {res.summary}.", "sad"
        if tool == "undo_upgrade":
            return f"{res.summary}. Say \"restart yourself\" to use the previous version.", "calm"
        return res.summary + ".", "happy"

    neko.coordinator.extensions.append(handle)


__all__ = ["Checkpoint", "attach", "command", "register_selfupdate_tools", "repo_is_private", "run_tests",
           "upgrade_transaction"]
