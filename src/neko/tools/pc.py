"""PC control: open anything, volume/media keys, windows, lock/sleep/restart/shutdown, typing.

Standard library only (ctypes for the Windows APIs). No shell strings: programs start with argument
lists, ``shell=False`` and timeouts; the one PowerShell call (listing Start Menu apps) is a fixed script.

Risk levels (docs/SAFETY_AND_PERMISSIONS.md):
* open_anything, media/volume keys, lock screen, focus/minimise/maximise a window: LOW - reversible.
* sleep, typing into the active window: MATERIAL - asks you. (Closing a window is LOW: the app itself
  still asks to save unsaved work.)
* restart / shut down: HIGH - asks you every time, and starts a 30 s countdown you can cancel
  ("Neko, cancel the shutdown").
Every tool checks the real outcome afterwards.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from difflib import SequenceMatcher
from typing import Any

from ..core.errors import ToolError
from ..core.types import RiskLevel
from .base import ToolContext, ToolRegistry, ToolResult, ToolSpec

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Windows Settings pages (these only OPEN the page; changing settings is left to you)
SETTINGS_PAGES = {
    "settings": "ms-settings:", "wifi": "ms-settings:network-wifi", "wi-fi": "ms-settings:network-wifi",
    "network": "ms-settings:network", "bluetooth": "ms-settings:bluetooth", "display": "ms-settings:display",
    "sound": "ms-settings:sound", "volume": "ms-settings:sound", "apps": "ms-settings:appsfeatures",
    "windows update": "ms-settings:windowsupdate", "update": "ms-settings:windowsupdate",
    "battery": "ms-settings:batterysaver", "power": "ms-settings:powersleep", "storage": "ms-settings:storagesense",
    "privacy": "ms-settings:privacy", "microphone settings": "ms-settings:privacy-microphone",
    "mouse": "ms-settings:mousetouchpad", "keyboard": "ms-settings:typing", "language": "ms-settings:regionlanguage",
    "date and time": "ms-settings:dateandtime", "notifications": "ms-settings:notifications",
    "personalization": "ms-settings:personalization", "background": "ms-settings:personalization-background",
    "night light": "ms-settings:nightlight", "printers": "ms-settings:printers", "vpn": "ms-settings:network-vpn",
}
_SITES = {"youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
          "facebook": "https://www.facebook.com", "github": "https://github.com", "chatgpt": "https://chatgpt.com",
          "claude": "https://claude.ai", "netflix": "https://www.netflix.com", "whatsapp web": "https://web.whatsapp.com",
          "messenger": "https://www.messenger.com", "instagram": "https://www.instagram.com",
          "wikipedia": "https://www.wikipedia.org", "maps": "https://www.google.com/maps"}
_URL = re.compile(r"^(https?://\S+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|ai|dev|edu|gov|bd|co|me|tv|app)"
                  r"(?:/\S*)?)$", re.IGNORECASE)
_APPS_CACHE: dict[str, Any] = {"at": 0.0, "apps": []}


# ---------------------------------------------------------------------- windows (ctypes)
def _user32() -> Any:
    if sys.platform != "win32":
        raise ToolError("PC control works on Windows only")
    return ctypes.windll.user32


def visible_windows() -> list[tuple[int, str]]:
    """(handle, title) of visible top-level windows with a title."""
    u = _user32()
    out: list[tuple[int, str]] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _lp):  # noqa: ANN001, ANN202
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.strip()
                if title and title not in ("Program Manager", "Windows Input Experience"):
                    out.append((int(hwnd or 0), title))
        return True

    u.EnumWindows(proto(cb), 0)
    return out


def _score(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def find_window(name: str) -> tuple[int, str] | None:
    best = max(((_score(name, t), h, t) for h, t in visible_windows()), default=None)
    return (best[1], best[2]) if best and best[0] >= 0.6 else None


# ---------------------------------------------------------------------- open anything
def start_apps() -> list[dict[str, str]]:
    """Installed apps from the Start Menu: [{"Name", "AppID"}] (cached 10 min)."""
    if time.monotonic() - _APPS_CACHE["at"] < 600 and _APPS_CACHE["apps"]:
        return _APPS_CACHE["apps"]
    try:
        cp = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                            capture_output=True, text=True, timeout=20, shell=False, creationflags=_NO_WINDOW)
        apps = json.loads(cp.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ToolError(f"couldn't list installed apps: {exc}") from exc
    apps = [a for a in (apps if isinstance(apps, list) else [apps]) if a.get("Name") and a.get("AppID")]
    _APPS_CACHE.update(at=time.monotonic(), apps=apps)
    return apps


_ALIASES = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
            "edge": "microsoft edge", "store": "microsoft store", "explorer": "file explorer",
            "files": "file explorer", "terminal": "terminal", "cmd": "command prompt", "ppt": "powerpoint",
            "camera": "camera", "photos": "photos", "calc": "calculator", "paint": "paint",
            "task manager": "task manager", "control panel": "control panel"}


def best_app(name: str) -> dict[str, str] | None:
    name = _ALIASES.get(name.lower().strip(), name)
    junk = re.compile(r"\b(uninstall|readme|help|website|on the web|documentation|license)\b", re.IGNORECASE)
    scored = sorted(((_score(name, a["Name"]), a) for a in start_apps() if not junk.search(a["Name"])),
                    key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.62 else None


def resolve_target(target: str, ctx: ToolContext) -> tuple[str, str, str]:
    """(kind, what_to_open, label) - kind is url | settings | path | app."""
    t = target.strip().strip("\"'")
    low = t.lower()
    low = re.sub(r"^(the|my)\s+", "", low)
    low = re.sub(r"\s+(app|application|website|site|page|program)$", "", low)
    if low in _SITES:
        return "url", _SITES[low], low
    if _URL.match(t):
        return "url", t if t.lower().startswith("http") else "https://" + t, t
    if low in SETTINGS_PAGES or low.removesuffix(" settings") in SETTINGS_PAGES:
        return "settings", SETTINGS_PAGES.get(low) or SETTINGS_PAGES[low.removesuffix(" settings")], low
    if re.match(r"^[a-z]:\\", t, re.IGNORECASE) or t.startswith("\\\\"):
        p = ctx.paths.check_read(t)  # same folder rules as reading files
        if not p.exists():
            raise ToolError(f"{p} doesn't exist")
        return "path", str(p), p.name or str(p)
    app = best_app(low)
    if app:
        return "app", app["AppID"], app["Name"]
    raise ToolError(f"I couldn't find an app, website or folder called \"{target}\"")


def _open(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    kind, what, label = resolve_target(args["target"], ctx)
    before = {h for h, _t in visible_windows()} if sys.platform == "win32" else set()
    if kind == "app":
        # The Start Menu launcher handles desktop and Store apps alike (argument list, no shell).
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{what}"], shell=False, creationflags=_NO_WINDOW)
    else:
        os.startfile(what)  # type: ignore[attr-defined]  # URL -> default browser, path -> Explorer/app
    return ToolResult(True, f"Opening {label}", {"kind": kind, "target": what, "label": label,
                                                 "windows_before": sorted(before)})


def _verify_open(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    data = result.data or {}
    before = set(data.get("windows_before", []))
    label = str(data.get("label", ""))
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        wins = visible_windows()
        if any(h not in before for h, _t in wins):
            return True, "a new window opened"
        if label and any(_score(label, t) >= 0.7 for _h, t in wins):
            return True, f"{label} is open"
        time.sleep(0.3)
    return False, "no new window appeared (it may already have been open)"


# ---------------------------------------------------------------------- keys, power, windows
_VK = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3, "next_track": 0xB0,
       "previous_track": 0xB1, "stop_media": 0xB2}


def _press(vk: int, times: int = 1) -> None:
    u = _user32()
    for _ in range(times):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        time.sleep(0.02)


PC_ACTIONS = ("volume_up", "volume_down", "mute", "play_pause", "next_track", "previous_track", "stop_media",
              "lock", "sleep", "restart", "shutdown", "cancel_shutdown")


def _pc_risk(args: dict[str, Any]) -> RiskLevel:
    a = args.get("action")
    if a in ("restart", "shutdown"):
        return RiskLevel.HIGH
    if a == "sleep":
        return RiskLevel.MATERIAL
    return RiskLevel.LOW


def _pc(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    a = args["action"]
    if a in _VK:
        steps = max(1, min(25, int(args.get("steps", 5)))) if a in ("volume_up", "volume_down") else 1
        _press(_VK[a], steps)  # each step is 2 %
        return ToolResult(True, f"{a.replace('_', ' ')}" + (f" x{steps}" if steps > 1 else ""))
    if a == "lock":
        if not _user32().LockWorkStation():
            raise ToolError("Windows refused to lock")
        return ToolResult(True, "Locked the PC")
    if a == "sleep":
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return ToolResult(True, "Putting the PC to sleep")
    if a in ("restart", "shutdown"):
        flag = "/r" if a == "restart" else "/s"
        cp = subprocess.run(["shutdown.exe", flag, "/t", "30", "/c", "N.E.K.O.: say 'cancel the shutdown' to stop"],
                            capture_output=True, text=True, timeout=10, shell=False, creationflags=_NO_WINDOW)
        if cp.returncode != 0:
            raise ToolError(f"Windows refused: {cp.stderr.strip() or cp.returncode}")
        return ToolResult(True, f"{'Restarting' if a == 'restart' else 'Shutting down'} in 30 seconds")
    if a == "cancel_shutdown":
        cp = subprocess.run(["shutdown.exe", "/a"], capture_output=True, text=True, timeout=10, shell=False,
                            creationflags=_NO_WINDOW)
        if cp.returncode != 0:
            return ToolResult(False, "there was no shutdown to cancel")
        return ToolResult(True, "Cancelled the shutdown")
    raise ToolError(f"unknown action {a}")


def _verify_pc(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    a = args["action"]
    if a in ("restart", "shutdown"):
        return True, "Windows accepted the shutdown request (30 s countdown)"
    if a == "lock":
        return True, "lock requested"  # the screen locks; nothing more can be read from here
    return True, "key sent"


WINDOW_ACTIONS = ("focus", "minimize", "maximize", "restore", "close")


def _window_risk(args: dict[str, Any]) -> RiskLevel:
    # Closing sends WM_CLOSE, so the app itself still asks "save changes?" - no extra prompt needed.
    return RiskLevel.LOW


def _window(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    found = find_window(args["name"])
    if not found:
        return ToolResult(False, f"no open window looks like \"{args['name']}\"")
    hwnd, title = found
    u, a = _user32(), args["action"]
    if a == "close":
        u.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE: the app can still ask to save your work
    elif a == "minimize":
        u.ShowWindow(hwnd, 6)
    elif a == "maximize":
        u.ShowWindow(hwnd, 3)
    else:  # focus / restore
        u.ShowWindow(hwnd, 9)
        u.SetForegroundWindow(hwnd)
    done = {"close": "Closed", "minimize": "Minimised", "maximize": "Maximised"}.get(a, "Switched to")
    return ToolResult(True, f"{done} {title}", {"hwnd": hwnd, "title": title})


def _verify_window(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    data, u = result.data or {}, _user32()
    hwnd, a = data.get("hwnd"), args["action"]
    time.sleep(0.6)
    if a == "close":
        gone = not u.IsWindow(hwnd) or not u.IsWindowVisible(hwnd)
        return gone, "window closed" if gone else "the app is still open (it may be asking to save)"
    if a == "minimize":
        return bool(u.IsIconic(hwnd)), "minimised"
    if a == "maximize":
        return bool(u.IsZoomed(hwnd)), "maximised"
    return bool(u.GetForegroundWindow() == hwnd) or bool(u.IsWindowVisible(hwnd)), "brought to front"


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _type(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    u = _user32()
    text = args["text"]
    target = u.GetForegroundWindow()
    for ch in text:  # KEYEVENTF_UNICODE: any language, including Bangla
        for flags in (0x0004, 0x0004 | 0x0002):
            inp = _INPUT(type=1)
            inp.ki = _KEYBDINPUT(0, ord(ch), flags, 0, None)
            u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
        time.sleep(0.004)
    return ToolResult(True, f"Typed {len(text)} characters", {"hwnd": int(target or 0)})


def _verify_type(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    same = _user32().GetForegroundWindow() == (result.data or {}).get("hwnd")
    return bool(same), "typed into the active window" if same else "the active window changed while typing"


def web_search_url(query: str) -> str:
    return "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})


def register_pc_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="open_anything", description="Open an installed app (by name), a website, a file or folder, or a "
                                          "Windows Settings page. Examples: 'spotify', 'youtube.com', 'bluetooth'.",
        params={"target": {"type": "string", "required": True, "max_length": 300}},
        handler=_open, risk=RiskLevel.LOW, category="computer_control", side_effects="opens a window",
        verifier=_verify_open, timeout_s=30,
    ))
    registry.register(ToolSpec(
        name="pc_control", description="Volume up/down, mute, media play/pause/next/previous, lock, sleep, restart, "
                                       "shutdown (30 s countdown) or cancel_shutdown.",
        params={"action": {"type": "string", "required": True, "enum": list(PC_ACTIONS)},
                "steps": {"type": "integer", "default": 5, "min": 1, "max": 25}},
        handler=_pc, risk=RiskLevel.LOW, risk_fn=_pc_risk, category="computer_control",
        side_effects="changes volume/media or the PC's power state", reversible=True, verifier=_verify_pc,
        timeout_s=15,
    ))
    registry.register(ToolSpec(
        name="window_control", description="Focus, minimize, maximize, restore or close an open window by name.",
        params={"name": {"type": "string", "required": True, "max_length": 120},
                "action": {"type": "string", "required": True, "enum": list(WINDOW_ACTIONS)}},
        handler=_window, risk=RiskLevel.LOW, risk_fn=_window_risk, category="computer_control",
        side_effects="changes a window", verifier=_verify_window, timeout_s=10,
    ))
    registry.register(ToolSpec(
        name="type_text", description="Type text into the window that is active right now.",
        params={"text": {"type": "string", "required": True, "max_length": 4000}},
        handler=_type, risk=RiskLevel.MATERIAL, category="computer_control", side_effects="types into an app",
        verifier=_verify_type, timeout_s=60,
    ))


__all__ = ["PC_ACTIONS", "SETTINGS_PAGES", "WINDOW_ACTIONS", "best_app", "find_window", "register_pc_tools",
           "resolve_target", "start_apps", "visible_windows", "web_search_url"]

