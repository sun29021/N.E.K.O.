"""Control buttons, menus and fields INSIDE apps (Windows UI Automation via the optional ``pywinauto``).

One tool, ``app_control``:
* ``list``  - what's in a window: buttons, menu items, fields, tabs, text (read-only)
* ``read``  - the text of one element, e.g. Calculator's display (read-only)
* ``click`` - press a button / menu item / tab / checkbox by its name ("Save", "Seven", "Dark mode")
* ``menu``  - walk a menu path: "File > Save as"
* ``fill``  - type text into a named field (asks you first)

Safety (on top of the normal approval rules):
* clicking anything that sounds destructive or outward-facing - delete, send, pay, buy, uninstall, format,
  sign out, submit... - is Level 3: it asks you EVERY time, whatever the app;
* filling a field is Level 2 (asks first); password fields are never filled or read;
* never acts on Neko's own windows (so she can't approve her own actions), Windows security / admin (UAC)
  prompts or credential dialogs.
A click is verified by checking that the app visibly reacted.
"""

from __future__ import annotations

import os
import re
import time
from difflib import SequenceMatcher
from typing import Any

from ..core.errors import PermissionDeniedError, ToolError
from ..core.types import RiskLevel
from ..tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

ACTIONS = ("list", "read", "click", "menu", "fill")
CLICKABLE = ("Button", "MenuItem", "ListItem", "TabItem", "CheckBox", "RadioButton", "Hyperlink", "TreeItem",
             "SplitButton", "ComboBox")
LISTED = CLICKABLE + ("Edit", "Text", "Document")
DANGEROUS = re.compile(
    r"\b(delete|remove|erase|wipe|format|uninstall|send|post|publish|share|pay|buy|purchase|order|checkout|"
    r"transfer|submit|confirm|sign ?out|log ?out|reset|empty|discard|overwrite|install|accept|agree|allow|"
    r"grant|unsubscribe|deactivate|block|report|shut ?down|restart)\b", re.IGNORECASE)
BLOCKED_WINDOWS = re.compile(r"N\.E\.K\.O\.|user account control|windows security|credential|sign in to|"
                             r"password|smart ?screen|administrator", re.IGNORECASE)


def _risk(args: dict[str, Any]) -> RiskLevel:
    action = args.get("action")
    if action in ("list", "read"):
        return RiskLevel.READ_ONLY
    if action == "fill":
        return RiskLevel.MATERIAL
    if DANGEROUS.search(f"{args.get('target', '')}"):
        return RiskLevel.HIGH
    return RiskLevel.LOW


def _score(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8 + 0.15 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def _desktop() -> Any:
    try:
        from pywinauto import Desktop  # optional dependency
    except ImportError as exc:
        raise ToolError("controlling buttons inside apps needs the 'pywinauto' package (pip install pywinauto)") from exc
    return Desktop(backend="uia")


def find_app_window(name: str) -> tuple[Any, str]:
    """(pywinauto window spec, title). Empty name = the window you're using right now."""
    import ctypes

    d = _desktop()
    if name.strip():
        from ..tools.pc import find_window

        found = find_window(name)
        if not found:
            raise ToolError(f"no open window looks like \"{name}\"")
        hwnd, title = found
    else:
        hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        title = d.window(handle=hwnd).window_text() if hwnd else ""
    if BLOCKED_WINDOWS.search(title):
        raise PermissionDeniedError(f"'{title}' is a protected window", user_message=(
            "That's a security, sign-in or approval window - I never click in those. Please do it yourself."))
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        raise PermissionDeniedError("refusing to control Neko's own windows",
                                    user_message="I don't click inside my own windows (that keeps approvals yours).")
    return d.window(handle=hwnd), title


def _elements(win: Any, types: tuple[str, ...]) -> list[Any]:
    out = []
    for c in win.descendants():
        try:
            info = c.element_info
            if info.control_type in types and (c.window_text() or "").strip() and c.is_visible():
                out.append(c)
        except Exception:  # noqa: BLE001 - elements can vanish while we look
            continue
    return out


def _best(win: Any, target: str, types: tuple[str, ...]) -> Any:
    scored = sorted(((_score(target, c.window_text()), c) for c in _elements(win, types)),
                    key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.6:
        names = ", ".join(dict.fromkeys(c.window_text() for _s, c in scored[:12]))
        raise ToolError(f"no \"{target}\" here. Things I can see: {names or 'nothing clickable'}")
    return scored[0][1]


def _is_password(c: Any) -> bool:
    try:
        return bool(c.element_info.element.CurrentIsPassword)
    except Exception:  # noqa: BLE001
        return False


def _press(c: Any) -> None:
    for how in ("invoke", "toggle", "select", "click_input"):
        fn = getattr(c, how, None)
        if fn is None:
            continue
        try:
            fn()
            return
        except Exception:  # noqa: BLE001 - not every element supports every pattern
            continue
    raise ToolError(f"couldn't press \"{c.window_text()}\"")


def _snapshot(win: Any) -> str:
    try:
        texts = [c.window_text() for c in win.descendants()[:400]]
    except Exception:  # noqa: BLE001
        texts = []
    try:
        from ..tools.pc import visible_windows

        tops = [t for _h, t in visible_windows()]
    except Exception:  # noqa: BLE001
        tops = []
    return str(hash(("|".join(texts), "|".join(tops))))


def _run(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    action, target = args["action"], (args.get("target") or "").strip()
    win, title = find_app_window(args.get("window", ""))
    if action == "list":
        lines = [f"{c.element_info.control_type}: {c.window_text()[:60]}" for c in _elements(win, LISTED)
                 if not _is_password(c)][:80]
        return ToolResult(True, f"{len(lines)} things in '{title}'", "\n".join(lines))
    if not target:
        raise ToolError("say which button, menu or field")
    if action == "read":
        c = _best(win, target, LISTED)
        if _is_password(c):
            raise PermissionDeniedError("password field", user_message="That's a password field - I don't read those.")
        try:
            value = c.get_value() if hasattr(c, "get_value") else ""
        except Exception:  # noqa: BLE001
            value = ""
        return ToolResult(True, f"Read '{c.window_text()}'", value or c.window_text())
    before = _snapshot(win)
    if action == "fill":
        c = _best(win, target, ("Edit", "ComboBox", "Document"))
        if _is_password(c):
            raise PermissionDeniedError("password field", user_message="I never type into password fields.")
        c.set_edit_text(args.get("text", ""))
        done = f"Typed into '{c.window_text() or target}' in {title}"
    elif action == "menu":
        steps = [s.strip() for s in re.split(r">|->|/", target) if s.strip()]
        for s in steps:
            _press(_best(win, s, ("MenuItem", "Button", "ListItem")))
            time.sleep(0.35)  # let the menu open
        done = f"Chose {' > '.join(steps)} in {title}"
    else:
        c = _best(win, target, CLICKABLE)
        _press(c)
        done = f"Clicked '{c.window_text()}' in {title}"
    return ToolResult(True, done, {"before": before, "window": args.get("window", "")})


def _verify(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    if args["action"] in ("list", "read"):
        return True, "read only"
    time.sleep(0.6)
    try:
        win, _t = find_app_window(args.get("window", ""))
        after = _snapshot(win)
    except (ToolError, PermissionDeniedError):
        return True, "the window changed or closed"  # e.g. a Close or OK button
    changed = after != (result.data or {}).get("before")
    return changed, "the app reacted" if changed else "no visible change in the app"


def register_automation_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="app_control",
        description="Use buttons, menus and fields INSIDE an open app. First 'list' to see what's there, then "
                    "'click' a name, 'menu' a path like 'File > Save as', 'read' a value, or 'fill' a field. "
                    "window = app name (empty = the window in front).",
        params={"action": {"type": "string", "required": True, "enum": list(ACTIONS)},
                "window": {"type": "string", "default": "", "max_length": 120},
                "target": {"type": "string", "default": "", "max_length": 200},
                "text": {"type": "string", "default": "", "max_length": 2000}},
        handler=_run, risk=RiskLevel.LOW, risk_fn=_risk, category="computer_control",
        side_effects="presses buttons / types into an app", verifier=_verify, timeout_s=30,
    ))


__all__ = ["ACTIONS", "DANGEROUS", "find_app_window", "register_automation_tools"]
