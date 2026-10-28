"""Filesystem path restrictions.

Paths are resolved (following symlinks/junctions) *before* the allow-list
check, so ``..`` segments, junctions and 8.3 short names cannot escape the
permitted roots. Some locations are always denied, even if a parent folder is
allowed, because they hold credentials or system state.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..core.errors import PermissionDeniedError

_ALWAYS_DENIED_NAMES = {
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".git-credentials",
    "id_rsa", "id_ed25519", ".env", ".netrc", "credentials", "cookies", "login data",
    "web data", "local state", "ntuser.dat", "protect", "vault",
}


def _system_roots() -> list[Path]:
    roots = []
    for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        v = os.environ.get(var)
        if v:
            roots.append(Path(v))
    return roots


def resolve(path: str | Path) -> Path:
    p = Path(os.path.expandvars(str(path))).expanduser()
    try:
        return p.resolve(strict=False)
    except OSError as exc:
        raise PermissionDeniedError(f"cannot resolve path {path}: {exc}") from exc


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class PathPolicy:
    def __init__(self, readable_roots: list[str], writable_roots: list[str], protected: list[str] | None = None):
        self.readable = [resolve(r) for r in readable_roots if r]
        self.writable = [resolve(r) for r in writable_roots if r]
        # The app's own data dir and source tree are protected from tool writes.
        self.protected = [resolve(p) for p in (protected or [])]

    def _denied_by_name(self, p: Path) -> str | None:
        for part in p.parts:
            if part.lower() in _ALWAYS_DENIED_NAMES:
                return part
        return None

    def check_read(self, path: str | Path) -> Path:
        p = resolve(path)
        bad = self._denied_by_name(p)
        if bad:
            raise PermissionDeniedError(f"{p} is in a protected location ({bad})",
                                        user_message="That file or folder holds credentials or system data and is always off-limits.")
        sysroot = os.environ.get("SystemRoot")
        if sysroot and is_within(p, Path(sysroot) / "System32" / "config"):
            raise PermissionDeniedError(f"{p} is the Windows registry store")
        if not any(is_within(p, r) for r in self.readable + self.writable):
            raise PermissionDeniedError(
                f"{p} is outside the allowed folders",
                user_message=f"I'm not allowed to read {p}. Add its folder to tools.allowed_roots in settings if you want me to.",
            )
        return p

    def check_write(self, path: str | Path) -> Path:
        p = resolve(path)
        bad = self._denied_by_name(p)
        if bad:
            raise PermissionDeniedError(f"{p} is in a protected location ({bad})")
        if any(is_within(p, s) for s in _system_roots()):
            raise PermissionDeniedError(f"{p} is a Windows system location")
        if any(is_within(p, s) for s in self.protected):
            raise PermissionDeniedError(f"{p} belongs to N.E.K.O.'s own data and cannot be changed by tools")
        if not any(is_within(p, r) for r in self.writable):
            raise PermissionDeniedError(
                f"{p} is outside the writable folders",
                user_message=f"I'm not allowed to change files in {p.parent}. Add it to tools.writable_roots first.",
            )
        return p
