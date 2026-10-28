"""Resource monitoring using documented Windows APIs and nvidia-smi.

* RAM: ``GlobalMemoryStatusEx`` (kernel32) via ctypes.
* Power: ``GetSystemPowerStatus`` (kernel32).
* Disk: ``shutil.disk_usage``.
* CPU load: ``GetSystemTimes`` deltas (no polling thread needed).
* NVIDIA GPU: ``nvidia-smi --query-gpu`` (ships with the driver). Missing
  values are reported as ``None`` - N.E.K.O. never guesses a temperature.
* CPU temperature: intentionally not read. There is no reliable, documented,
  driver-independent API on this laptop (WMI thermal zones are often absent
  or wrong on consumer AMD laptops).
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ResourceSnapshot:
    ram_total_mb: int | None = None
    ram_free_mb: int | None = None
    cpu_pct: float | None = None
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    gpu_util_pct: float | None = None
    gpu_temp_c: float | None = None
    gpu_name: str = ""
    on_battery: bool | None = None
    battery_pct: int | None = None
    disk_free_gb: float | None = None
    disk_path: str = ""
    taken_at: float = 0.0

    @property
    def vram_free_mb(self) -> int | None:
        if self.vram_total_mb is None or self.vram_used_mb is None:
            return None
        return self.vram_total_mb - self.vram_used_mb

    def as_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["vram_free_mb"] = self.vram_free_mb
        return d

    def as_text(self) -> str:
        def f(v: object, unit: str = "") -> str:
            return "unknown" if v is None else f"{v}{unit}"

        return "\n".join([
            f"RAM free: {f(self.ram_free_mb, ' MB')} of {f(self.ram_total_mb, ' MB')}",
            f"CPU load: {f(None if self.cpu_pct is None else round(self.cpu_pct), '%')}",
            f"GPU: {self.gpu_name or 'not detected'}; VRAM free {f(self.vram_free_mb, ' MB')} of "
            f"{f(self.vram_total_mb, ' MB')}; util {f(self.gpu_util_pct, '%')}; temp {f(self.gpu_temp_c, ' C')}",
            f"Power: {'battery' if self.on_battery else 'AC' if self.on_battery is False else 'unknown'}"
            f" ({f(self.battery_pct, '%')})",
            f"Disk free on {self.disk_path or '?'}: {f(self.disk_free_gb, ' GB')}",
        ])


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_ulong), ("hi", ctypes.c_ulong)]

    @property
    def value(self) -> int:
        return (self.hi << 32) | self.lo


class ResourceMonitor:
    def __init__(self, disk_path: str | Path = ".", *, nvidia_smi: str = "nvidia-smi", cache_s: float = 3.0) -> None:
        self.disk_path = str(disk_path)
        self.nvidia_smi = nvidia_smi
        self.cache_s = cache_s
        self._last: ResourceSnapshot | None = None
        self._lock = threading.Lock()
        self._cpu_prev: tuple[int, int, int] | None = None
        self._gpu_ok = True  # stop calling nvidia-smi if it is missing

    def snapshot(self, *, fresh: bool = False) -> ResourceSnapshot:
        with self._lock:
            if not fresh and self._last and time.time() - self._last.taken_at < self.cache_s:
                return self._last
            s = ResourceSnapshot(taken_at=time.time(), disk_path=self.disk_path)
            self._ram(s)
            self._power(s)
            self._cpu(s)
            self._disk(s)
            self._gpu(s)
            self._last = s
            return s

    # ------------------------------------------------------------------ probes
    def _ram(self, s: ResourceSnapshot) -> None:
        if sys.platform != "win32":
            return
        st = _MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            s.ram_total_mb = st.ullTotalPhys // 1_048_576
            s.ram_free_mb = st.ullAvailPhys // 1_048_576

    def _power(self, s: ResourceSnapshot) -> None:
        if sys.platform != "win32":
            return
        ps = _SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps)):
            s.on_battery = {0: True, 1: False}.get(ps.ACLineStatus)
            s.battery_pct = None if ps.BatteryLifePercent == 255 else int(ps.BatteryLifePercent)

    def _cpu(self, s: ResourceSnapshot) -> None:
        if sys.platform != "win32":
            return
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return
        cur = (idle.value, kernel.value, user.value)
        if self._cpu_prev is not None:
            di, dk, du = (c - p for c, p in zip(cur, self._cpu_prev, strict=True))
            total = dk + du  # kernel time includes idle time
            if total > 0:
                s.cpu_pct = max(0.0, min(100.0, 100.0 * (total - di) / total))
        self._cpu_prev = cur

    def _disk(self, s: ResourceSnapshot) -> None:
        try:
            s.disk_free_gb = round(shutil.disk_usage(self.disk_path).free / 1e9, 1)
        except OSError:
            pass

    def _gpu(self, s: ResourceSnapshot) -> None:
        if not self._gpu_ok:
            return
        try:
            out = subprocess.run(
                [self.nvidia_smi, "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            self._gpu_ok = False
            return
        if out.returncode != 0 or not out.stdout.strip():
            return
        parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
        if len(parts) >= 5:
            s.gpu_name = parts[0]
            s.vram_total_mb = _num(parts[1], int)
            s.vram_used_mb = _num(parts[2], int)
            s.gpu_util_pct = _num(parts[3], float)
            s.gpu_temp_c = _num(parts[4], float)


def _num(text: str, cast: type) -> int | float | None:
    try:
        return cast(float(text))
    except ValueError:
        return None  # "[N/A]" or "[Not Supported]"


@dataclass
class Feasibility:
    ok: bool
    reason: str
    gpu_fit: str = "unknown"       # full | partial | none | unknown


def assess(required_mb: int, snap: ResourceSnapshot, *, ram_margin_mb: int, vram_margin_mb: int) -> Feasibility:
    """Can a model needing ``required_mb`` (weights+KV+buffers) run now without
    pushing Windows into memory pressure? Ollama splits layers between VRAM
    and RAM, so the *combined* free memory matters, minus safety margins."""
    vram_free = max(0, (snap.vram_free_mb or 0) - vram_margin_mb)
    ram_free = snap.ram_free_mb
    if ram_free is None:
        return Feasibility(True, "RAM unknown; proceeding cautiously", "unknown")
    ram_avail = max(0, ram_free - ram_margin_mb)
    if required_mb <= vram_free:
        return Feasibility(True, f"fits in GPU memory ({required_mb} MB <= {vram_free} MB free)", "full")
    if required_mb <= vram_free + ram_avail:
        part = "partial" if vram_free > 0 else "none"
        return Feasibility(True, f"fits with CPU/GPU split ({required_mb} MB; {vram_free} MB VRAM + {ram_avail} MB RAM "
                                 "usable) - slower", part)
    return Feasibility(False, f"needs ~{required_mb} MB but only {vram_free + ram_avail} MB is safely free "
                              f"(keeping {ram_margin_mb} MB for Windows)", "none")
