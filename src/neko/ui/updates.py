"""Background update check + one-click install (runs scripts/update.ps1; argument lists, no shell strings)."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "update.ps1"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(*flags: str, timeout: float) -> tuple[int, str]:
    cp = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *flags],
                        capture_output=True, text=True, timeout=timeout, shell=False, creationflags=_NO_WINDOW)
    return cp.returncode, (cp.stdout or "") + (cp.stderr or "")


class Updater(QObject):
    available = Signal(str)     # what's new (short text)
    finished = Signal(bool, str)

    def __init__(self, every_hours: float = 6.0) -> None:
        super().__init__()
        self.pending = ""
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        if (ROOT / ".git").exists():  # only copies connected to the update repo
            QTimer.singleShot(120_000, self.check)       # 2 min after start
            self._timer.start(int(every_hours * 3600_000))

    def check(self) -> None:
        if self._busy:
            return
        self._busy = True

        def work() -> None:
            try:
                code, out = _run("-Check", timeout=90)
                if code == 10:
                    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(("Update available", "- "))]
                    self.pending = "\n".join(lines[:8])
                    self.available.emit(self.pending)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                self._busy = False
        threading.Thread(target=work, daemon=True, name="neko-update-check").start()

    def install(self) -> None:
        """You clicked 'Install update': backup, new code, packages, self-test (rolls back on failure)."""
        if self._busy:
            return
        self._busy = True

        def work() -> None:
            try:
                code, out = _run("-Apply", timeout=1800)
                self.finished.emit(code == 0, out[-600:])
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.finished.emit(False, str(exc))
            finally:
                self._busy = False
        threading.Thread(target=work, daemon=True, name="neko-update-apply").start()


def restart_neko() -> None:
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File",
                      str(ROOT / "scripts" / "restart-neko.ps1")], shell=False, creationflags=_NO_WINDOW)


__all__ = ["Updater", "restart_neko"]
