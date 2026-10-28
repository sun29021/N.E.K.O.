"""Neko <-> Neko: your laptop uses the office PC's Neko (and the office PC can use the laptop's).

Server side (the PC being used, e.g. the office): Command Center > Phone > "Let my other PC connect".
It serves ``/link/*`` on the same local-only web server as the call page (127.0.0.1, shared by Tailscale
inside your tailnet) and shows a **link code** - its address plus a long random key.

Client side (e.g. the laptop): Command Center > Phone > "Connect to my other PC" and paste that code.
Then, by voice, text or from your phone:

* "what can the office PC do that you can't?" / "compare with the office PC" - features, programs, skills,
  AI models and versions, side by side, with what to do about each difference
* "on the office PC, run Print SOFT" / "ask the office PC to ..." - the office Neko does it; anything risky
  is approved by the office Neko's OWNER (your phone), never by the laptop
* "get the skill X from the office PC" / "send the skill X to the office PC" - share learned skills
  (replaying a skill always asks for approval again, on the PC that runs it)

Memories are NOT shared: each PC keeps its own.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.request
from typing import Any

from ..core import origin
from ..core.cancel import CancelToken
from ..core.errors import ToolError

log = logging.getLogger("neko.phone.link")
CODE_PREFIX = "neko-link:"


# ====================================================================== server side
class LinkServer:
    """Answers the other PC. Plugged into CallServer's HTTP handler (routes under /link/)."""

    def __init__(self, neko: Any, service: Any) -> None:
        self.neko, self.service = neko, service
        self._bad: list[float] = []

    @property
    def enabled(self) -> bool:
        return bool(self.neko.settings.phone.link_server and self.service.state.link_key)

    def code(self) -> str:
        from .call import tailnet_name

        host = tailnet_name()
        if not host or not self.service.state.link_key:
            return ""
        port = self.neko.settings.phone.call_https_port
        return f"{CODE_PREFIX}https://{host}{'' if port == 443 else f':{port}'}#{self.service.state.link_key}"

    def new_key(self) -> str:
        self.service.state.link_key = secrets.token_urlsafe(32)
        self.service._save()
        return self.service.state.link_key

    def authorized(self, key: str) -> bool:
        now = time.time()
        self._bad = [t for t in self._bad if now - t < 60]
        if len(self._bad) >= 10 or not self.enabled:
            return False
        ok = bool(key) and hmac.compare_digest(key.encode(), self.service.state.link_key.encode())
        if not ok:
            self._bad.append(now)
            log.warning("link: request with a wrong key")
        return ok

    def handle(self, route: str, key: str, body: bytes) -> tuple[int, dict[str, Any]]:
        if not self.authorized(key):
            return 403, {"error": "forbidden"}
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            return 400, {"error": "bad request"}
        if route == "/link/info":
            return 200, describe_self(self.neko)
        if route == "/link/ask":
            text = str(data.get("text", ""))[:4000].strip()
            if not text:
                return 400, {"error": "empty"}
            # the owner's request, approved by this PC's owner phone (or this PC's dialog)
            with origin.from_origin(origin.PHONE):
                reply = self.neko.coordinator.handle(text, conversation_id=self.service._conversation(),
                                                     token=CancelToken(timeout_s=900))
            return 200, {"text": reply.text, "ok": reply.succeeded}
        if route == "/link/skill":
            r = self.neko.routines
            if "steps" in data:   # the other PC sends one
                name = re.sub(r"\s+", " ", str(data.get("name", ""))).strip().lower()[:60]
                steps = data["steps"] if isinstance(data["steps"], list) else []
                if not name or not steps or len(steps) > 15 or not all(isinstance(s, dict) and "tool" in s
                                                                        for s in steps):
                    return 400, {"error": "bad skill"}
                r.store_skill(name, steps)
                return 200, {"ok": True, "name": name}
            want = r.find_skill(str(data.get("name", "")))
            if want is None:
                return 404, {"error": "no such skill"}
            return 200, {"name": want["name"], "steps": json.loads(want["steps_json"])}
        return 404, {"error": "unknown"}


def describe_self(neko: Any) -> dict[str, Any]:
    """What this Neko can do - for the other PC's comparison."""
    from .. import __version__

    models = []
    for m, _p in neko.router.refresh():
        if m.location == "local":
            models.append(m.name)
    progs = []
    try:
        from ..programs import Programs

        progs = sorted(Programs(neko.settings).load())
    except Exception:  # noqa: BLE001
        pass
    snap = neko.monitor.snapshot()
    return {
        "name": neko.settings.app.assistant_name, "version": __version__,
        "tools": sorted(s.name for s in neko.tools.all() if not s.prohibited),
        "programs": progs,
        "skills": [s["name"] for s in neko.routines.skills()] if neko.routines is not None else [],
        "models": sorted(models), "profile": neko.settings.models.profile,
        "gpu_mb": getattr(snap, "vram_total_mb", None), "ram_mb": getattr(snap, "ram_total_mb", None),
        "voice": bool(neko.settings.voice.enabled), "internet": bool(neko.settings.privacy.allow_network),
        "telegram": bool(neko.settings.phone.telegram), "calls": bool(neko.settings.phone.calls),
    }


# ====================================================================== client side
def parse_code(code: str) -> tuple[str, str]:
    code = code.strip()
    if not code.startswith(CODE_PREFIX) or "#" not in code:
        raise ToolError("not a link code", user_message="That isn't a link code - copy it from the other PC's "
                                                        "Command Center > Phone.")
    url, key = code[len(CODE_PREFIX):].split("#", 1)
    if not re.match(r"^https://[A-Za-z0-9.-]+\.ts\.net(:\d+)?$", url):
        raise ToolError("link code must point to your tailnet",
                        user_message="That link code doesn't point inside your Tailscale network.")
    return url, key


class LinkClient:
    def __init__(self, url: str, key: str, timeout_s: float = 30) -> None:
        self.url, self._key, self.timeout_s = url.rstrip("/"), key, timeout_s

    def call(self, route: str, data: dict[str, Any] | None = None, timeout_s: float | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.url + route, data=json.dumps(data or {}).encode("utf-8"), method="POST",
                                     headers={"X-Neko-Link": self._key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s or self.timeout_s) as resp:  # noqa: S310 - tailnet
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise ToolError("link refused", user_message="The other PC refused the link key - make a new link "
                                                             "code there and connect again.") from None
            if exc.code == 404:
                return {"error": "not found"}
            raise ToolError(f"link HTTP {exc.code}", user_message="The other PC had a problem with that.") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ToolError(f"link: {exc}", user_message="I can't reach the other PC - is it on, with Neko and "
                                                         "Tailscale running?") from None


def compare(mine: dict[str, Any], theirs: dict[str, Any]) -> str:
    """Plain-language differences, each with what to do about it."""
    other = theirs.get("name") or "the other PC"
    lines = [f"{other} (version {theirs.get('version')}) vs me (version {mine.get('version')}):"]
    if theirs.get("version") != mine.get("version"):
        newer = "I'm newer" if _ver(mine.get("version")) > _ver(theirs.get("version")) else f"{other} is newer"
        tip = ("say \"publish the update\" and install it there" if newer == "I'm newer" else
               "install the update offered in my tray")
        lines.append(f"- Versions differ ({newer}) - {tip}; then both have the same features.")
    for key, what in (("tools", "abilities"), ("programs", "programs"), ("skills", "skills")):
        only_there = sorted(set(theirs.get(key) or []) - set(mine.get(key) or []))
        only_here = sorted(set(mine.get(key) or []) - set(theirs.get(key) or []))
        if only_there:
            use = (" - use them with \"on the other PC, ...\"" if key != "skills" else
                   " - \"get the skill <name> from the other PC\"")
            lines.append(f"- Only {other} has these {what}: {', '.join(only_there[:12])}{use}.")
        if only_here:
            lines.append(f"- Only I have these {what}: {', '.join(only_here[:12])}.")
    big_there = sorted(set(theirs.get("models") or []) - set(mine.get("models") or []))
    if big_there:
        lines.append(f"- {other}'s AI models I can borrow (automatically, when it's on): {', '.join(big_there[:8])}.")
    for flag, what in (("telegram", "Telegram"), ("calls", "phone calls"), ("voice", "voice")):
        if theirs.get(flag) and not mine.get(flag):
            lines.append(f"- {other} has {what} on; I don't (Command Center > Phone/Settings).")
        elif mine.get(flag) and not theirs.get(flag):
            lines.append(f"- I have {what} on; {other} doesn't.")
    if len(lines) == 1:
        lines.append("- We can do the same things.")
    return "\n".join(lines)


def _ver(v: Any) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "0")))


_ASK = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:on|at|use)\s+(?:the|my)\s+(?:office|other|desktop|big)\s+(?:pc|"
                  r"computer)\W+(?P<req>.+)$|^\W*(?:ask|tell)\s+(?:the|my)\s+(?:office|other|desktop)\s+(?:pc|computer)"
                  r"(?:'s neko)?\s+(?:to\s+)?(?P<req2>.+)$", re.I | re.S)
_COMPARE = re.compile(r"\b(compare|difference|what can|how (?:much|many) more|which features?)\b.{0,60}"
                      r"\b(office|other|desktop)\s+(pc|computer|version|neko)\b", re.I)
_GET_SKILL = re.compile(r"\b(?:get|copy|bring|take)\s+(?:the\s+)?skill\s+(?P<name>.+?)\s+from\s+(?:the\s+|my\s+)?"
                        r"(?:office|other|desktop)\s+(?:pc|computer)\W*$", re.I)
_SEND_SKILL = re.compile(r"\b(?:send|share|give|copy)\s+(?:the\s+)?skill\s+(?P<name>.+?)\s+to\s+(?:the\s+|my\s+)?"
                         r"(?:office|other|desktop)\s+(?:pc|computer)\W*$", re.I)


def link_client(neko: Any) -> LinkClient | None:
    url = neko.settings.phone.link_url
    if not url:
        return None
    from .service import secret

    key = secret(neko.settings.data_dir, "link_key")
    return LinkClient(url, key) if key else None


def attach_client(neko: Any) -> None:
    """Commands that use the other PC (only active once you've connected with a link code)."""

    def handle(text: str, conv: str, task: Any, token: Any) -> tuple[str, str] | None:
        t = text.strip()
        hit = _COMPARE.search(t) or _ASK.match(t) or _GET_SKILL.search(t) or _SEND_SKILL.search(t)
        if not hit:
            return None
        client = link_client(neko)
        if client is None:
            return ("I'm not connected to another PC yet. On that PC: Command Center > Phone > \"Let my other PC "
                    "connect\", then paste its link code here in Command Center > Phone > \"Connect to my other "
                    "PC\"."), "curious"
        if _COMPARE.search(t):
            return compare(describe_self(neko), client.call("/link/info")), "neutral"
        if (m := _GET_SKILL.search(t)):
            got = client.call("/link/skill", {"name": m.group("name")})
            if "steps" not in got:
                return f"The other PC doesn't have a skill called \"{m.group('name')}\".", "neutral"
            neko.routines.store_skill(got["name"], got["steps"])
            return (f"Copied the skill \"{got['name']}\" ({len(got['steps'])} steps). Each step still asks for "
                    "approval here when it needs it."), "happy"
        if (m := _SEND_SKILL.search(t)):
            mine = neko.routines.find_skill(m.group("name"))
            if mine is None:
                return f"I don't have a skill called \"{m.group('name')}\".", "neutral"
            client.call("/link/skill", {"name": mine["name"], "steps": json.loads(mine["steps_json"])})
            return f"Sent the skill \"{mine['name']}\" to the other PC.", "happy"
        m = _ASK.match(t)
        req = (m.group("req") or m.group("req2") or "").strip()
        got = client.call("/link/ask", {"text": req}, timeout_s=900)
        other = "The other PC"
        return f"{other}: {got.get('text') or got.get('error') or '(no answer)'}", "neutral" if got.get("ok") else "sad"

    # first: "on the office PC, publish the update" is for THAT PC, not a command for this one
    neko.coordinator.extensions.insert(0, handle)


__all__ = ["LinkClient", "LinkServer", "attach_client", "compare", "describe_self", "parse_code"]
