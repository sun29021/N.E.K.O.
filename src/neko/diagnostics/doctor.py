"""Read-only health check. Never starts, installs, downloads or changes anything."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from ..configuration.settings import Settings
from ..core.errors import ConfigError
from ..models.inventory import scan_ollama_store
from ..models.ollama import OllamaProvider
from ..resources.monitor import ResourceMonitor


@dataclass
class Check:
    name: str
    status: str          # ok | warn | fail | info
    detail: str
    fix: str = ""


def _optional(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def run_checks(settings: Settings | None, *, ollama_models_dir: str | None = None,
               config_error: str | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("N.E.K.O. version", "info", __version__))
    release = platform.release()
    try:  # Python reports Windows 11 as release "10"; build 22000+ is Windows 11
        if release == "10" and int(platform.version().split(".")[2]) >= 22000:
            release = "11"
    except (IndexError, ValueError):
        pass
    checks.append(Check("Windows", "info", f"{platform.system()} {release} ({platform.version()})"))
    py_ok = (3, 11) <= sys.version_info[:2] <= (3, 14)
    checks.append(Check("Python", "ok" if py_ok else "warn", f"{sys.version.split()[0]} at {sys.executable}",
                        "" if py_ok else "Use Python 3.11-3.13 for the optional voice packages."))
    if config_error:
        checks.append(Check("Configuration", "fail", config_error, "Fix the listed keys in %LOCALAPPDATA%\\NEKO\\config.toml"))
        return checks
    assert settings is not None
    checks.append(Check("Configuration", "ok", "loaded from " + " + ".join(settings.source_files)))
    checks.append(Check("Data folder", "ok" if settings.data_dir.exists() else "info", str(settings.data_dir),
                        "" if settings.data_dir.exists() else "Created automatically on first launch."))

    snap = ResourceMonitor(disk_path=str(settings.data_dir.anchor or ".")).snapshot(fresh=True)
    if snap.ram_total_mb:
        status = "ok" if (snap.ram_free_mb or 0) > settings.resources.ram_safety_margin_mb + 2500 else "warn"
        checks.append(Check("RAM", status, f"{snap.ram_free_mb} MB free of {snap.ram_total_mb} MB",
                            "" if status == "ok" else "Close heavy apps (browsers, games) before loading a model."))
    if snap.gpu_name:
        checks.append(Check("GPU", "ok", f"{snap.gpu_name}: {snap.vram_free_mb} MB VRAM free of {snap.vram_total_mb} MB, "
                                         f"{snap.gpu_temp_c} C"))
    else:
        checks.append(Check("GPU", "warn", "nvidia-smi not found or no NVIDIA GPU", "Models will run on CPU (slower)."))
    if snap.on_battery is not None:
        checks.append(Check("Power", "warn" if snap.on_battery else "ok",
                            f"{'on battery' if snap.on_battery else 'plugged in'} ({snap.battery_pct}%)",
                            "Plug in for faster, sustained inference." if snap.on_battery else ""))
    for label, path in (("Disk (data)", str(settings.data_dir.anchor or "C:\\")),
                        ("Disk (models)", ollama_models_dir or os.environ.get("OLLAMA_MODELS", ""))):
        if not path or not Path(path).exists():
            continue
        free_gb = shutil.disk_usage(path).free / 1e9
        ok = free_gb >= settings.resources.disk_min_free_gb
        checks.append(Check(label, "ok" if ok else "warn", f"{free_gb:.1f} GB free on {Path(path).anchor}",
                            "" if ok else "Free up space before adding models."))

    # a PC set up by scripts\install\install.ps1 records its own Ollama paths (the laptop uses D:\Ollama)
    local_paths: dict[str, str] = {}
    paths_file = Path(__file__).resolve().parents[3] / "neko-paths.json"
    if paths_file.exists():
        try:
            import json

            local_paths = json.loads(paths_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            local_paths = {}
    models_dir = (ollama_models_dir or os.environ.get("OLLAMA_MODELS") or local_paths.get("models_dir")
                  or r"D:\Ollama\models")
    inv = scan_ollama_store(Path(models_dir))
    if inv:
        detail = "; ".join(f"{e.name} {e.quantization} {e.size_bytes / 1e9:.2f} GB"
                           f"{'' if e.blob_present else ' (BLOB MISSING)'}" for e in inv)
        checks.append(Check("Models on disk", "ok" if all(e.blob_present for e in inv) else "warn",
                            f"{models_dir}: {detail}"))
    else:
        checks.append(Check("Models on disk", "warn", f"no Ollama models found in {models_dir}",
                            "See docs/MODEL_GUIDE.md."))

    candidates = [local_paths.get("ollama_exe", ""), r"D:\Ollama\app\ollama.exe"]
    exe = shutil.which("ollama") or next((c for c in candidates if c and Path(c).exists()), None)
    checks.append(Check("Ollama executable", "ok" if exe else "fail", exe or "not found",
                        "" if exe else "See INSTALLATION_MANUAL step 4."))
    health = OllamaProvider(settings.models.ollama_url).health(timeout_s=2)
    checks.append(Check("Ollama server", "ok" if health.ok else "warn",
                        f"running, version {health.version}" if health.ok else f"not reachable at {settings.models.ollama_url}",
                        "" if health.ok else "Start it with: powershell -File scripts\\start-ollama.ps1"))
    if health.ok:
        try:
            names = [m.name for m in OllamaProvider(settings.models.ollama_url).list_models()]
            checks.append(Check("Ollama models", "ok" if names else "warn", ", ".join(names) or "none registered",
                                "" if names else "Is OLLAMA_MODELS pointing at D:\\Ollama\\models?"))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Ollama models", "warn", str(exc)))

    if settings.db_path.exists():
        from ..database.db import Database

        import sqlite3

        try:
            db = Database(settings.db_path)
            ok, msg = db.integrity_check()
            checks.append(Check("Database", "ok" if ok else "fail",
                                f"{settings.db_path} schema v{db.schema_version()}: {msg}",
                                "" if ok else "See docs/BACKUP_AND_RECOVERY.md 'Corruption response'."))
            db.close()
        except sqlite3.DatabaseError as exc:  # a damaged file must be reported, not crash the health check
            checks.append(Check("Database", "fail", f"{settings.db_path}: {exc}",
                                "Restore a backup: see docs/BACKUP_AND_RECOVERY.md 'Corruption response'."))
    else:
        checks.append(Check("Database", "info", "not created yet (created on first launch)"))

    for mod, label, extra in (("PySide6", "Desktop UI (PySide6)", "ui"), ("faster_whisper", "Speech recognition", "voice"),
                              ("sounddevice", "Microphone access", "voice"), ("openwakeword", "Wake word", "wakeword")):
        present = _optional(mod)
        checks.append(Check(label, "ok" if present else "info", "installed" if present else "not installed (optional)",
                            "" if present else f"scripts\\setup.ps1 installs it with the '{extra}' option"))
    tts = settings.voice.tts_engine
    if tts == "kokoro":
        from ..voice.tts_kokoro import KokoroSynthesizer

        ok, why = KokoroSynthesizer(settings.voice.kokoro_voice, model_dir=settings.voice.kokoro_dir).available()
        checks.append(Check("Speech output", "ok" if ok else "warn", why,
                            "" if ok else "Falls back to the Windows voice until fixed (MODEL_GUIDE section 4)."))
    else:
        checks.append(Check("Speech output", "ok" if tts in ("sapi", "none") else "info", f"engine: {tts}"))
    return checks


def format_checks(checks: list[Check]) -> str:
    icon = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", "info": "[INFO]"}
    lines = []
    for c in checks:
        lines.append(f"{icon[c.status]} {c.name}: {c.detail}")
        if c.fix:
            lines.append(f"        -> {c.fix}")
    return "\n".join(lines)


def doctor_main(settings_loader: object) -> int:
    try:
        settings = settings_loader()  # type: ignore[operator]
        checks = run_checks(settings)
    except ConfigError as exc:
        checks = run_checks(None, config_error=exc.user_message)
    print(format_checks(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0
