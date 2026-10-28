"""Reminders and learned skills.

Reminders
    "remind me at 6 to call Ammu", "remind me in 20 minutes to check the rice", "remind me tomorrow at 9
    to pay the bill". When one is due it is published as ``ev.REMINDER``: the PC says it and the paired
    phone gets a message. "What are my reminders?", "cancel my reminders".

Learned skills (the idea from Hermes Agent, kept deterministic and safe)
    After she does a few actions for you, say "save that as monthly sheet". Next time say "do the monthly
    sheet" and she replays the same actions. Every replayed step goes through the normal permission
    policy again - a skill can never skip an approval - and replay stops at the first step that fails.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from ..core import events as ev
from ..core import origin
from ..core.cancel import CancelToken
from ..core.types import new_id
from ..tools.base import ToolContext

log = logging.getLogger("neko.routines")

# ====================================================================== reminders
_REMIND = re.compile(r"^\W*(?:(?:hey|ok|okay)\s+)?(?:neko\W+)?(?:please\s+|can you\s+|could you\s+)?"
                     r"(?:remind me|set (?:a |an )?(?:reminder|alarm)|reminder)\b(?P<rest>.*)$", re.I | re.S)
_REL = re.compile(r"\bin\s+(?P<n>an?|half an|\d+(?:\.\d+)?)\s*(?P<u>seconds?|secs?|minutes?|mins?|hours?|hrs?|"
                  r"days?)\b", re.I)
_HALF_HOUR = re.compile(r"\bin\s+half an hour\b", re.I)
_AT = re.compile(r"(?:\b(?:at|by|for|around)\s+)?\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)?"
                 r"(?=\W|$)", re.I)
_DAY = re.compile(r"\b(tomorrow|tonight|today|this evening|this afternoon|in the morning|in the evening)\b", re.I)
_LIST_REMINDERS = re.compile(r"\b(what|which|show|list|any)\b.{0,20}\breminders?\b", re.I)
_CANCEL_REMINDERS = re.compile(r"\b(cancel|delete|remove|clear|stop)\b.{0,25}\breminders?\b", re.I)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_reminder(text: str, now: datetime | None = None) -> tuple[datetime | None, str] | None:
    """None = not a reminder request. (None, what) = a reminder without a time we could understand."""
    m = _REMIND.match(text.strip())
    if not m:
        return None
    now = now or datetime.now()
    rest = m.group("rest")
    due: datetime | None = None
    if (half := _HALF_HOUR.search(rest)):
        due, rest = now + timedelta(minutes=30), rest[:half.start()] + rest[half.end():]
    elif (rel := _REL.search(rest)):
        n = rel.group("n").lower()
        amount = 1.0 if n in ("a", "an") else 0.5 if n == "half an" else float(n)
        due = now + timedelta(seconds=amount * _UNITS[rel.group("u")[0].lower()])
        rest = rest[:rel.start()] + rest[rel.end():]
    else:
        day = _DAY.search(rest)
        day_word = day.group(1).lower() if day else ""
        if day:
            rest = rest[:day.start()] + rest[day.end():]
        # a bare number is only a time with "at"/"by"..., minutes ("6:30") or am/pm: "call 2 people at 6"
        at = next((a for a in _AT.finditer(rest) if a.group("m") or a.group("ap")
                   or a.group(0).lower().startswith(("at", "by", "for", "around"))), None)
        if at and int(at.group("h")) <= 24 and int(at.group("m") or 0) < 60:
            due = _resolve_clock(int(at.group("h")), int(at.group("m") or 0), (at.group("ap") or "").lower(),
                                 day_word, now)
            rest = rest[:at.start()] + rest[at.end():]
        elif day_word == "tomorrow":
            due = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif day_word == "tonight":
            due = now.replace(hour=21, minute=0, second=0, microsecond=0)
    what = re.sub(r"^\W*(?:me\s+)?(?:to|that|about|of|for)\s+", "", rest.strip(), flags=re.I)
    what = re.sub(r"\s+(?:at|by|for|on)\s*$", "", what.strip(" .,!?"), flags=re.I).strip(" .,!?")
    return due, what


def _resolve_clock(h: int, minute: int, ampm: str, day_word: str, now: datetime) -> datetime:
    if ampm.startswith("p") and h < 12:
        h += 12
    elif ampm.startswith("a") and h == 12:
        h = 0
    base = now + timedelta(days=1) if day_word == "tomorrow" else now
    if ampm or h > 12:
        options = [h % 24]
    elif day_word in ("tonight", "this evening", "in the evening", "this afternoon") and h < 12:
        options = [h + 12]
    elif day_word == "in the morning":
        options = [h % 12]
    else:
        options = [h % 24, (h + 12) % 24] if h < 12 else [h % 24]  # "at 6" = the next 6 o'clock
    candidates = sorted(base.replace(hour=o, minute=minute, second=0, microsecond=0) for o in options)
    if day_word == "tomorrow":
        # "tomorrow at 6" without am/pm: 1-7 means evening, otherwise as said
        return candidates[-1] if (not ampm and 1 <= h <= 7) else candidates[0]
    for c in candidates:
        if c > now:
            return c
    return candidates[0] + timedelta(days=1)


def _when(dt: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    clock = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return f"at {clock}"
    if dt.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {clock}"
    return f"on {dt.strftime('%a %d %b')} at {clock}"


# ====================================================================== skills
_SAVE_SKILL = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:save|learn|remember|keep)\s+(?:that|this|these steps|"
                         r"those steps|what you (?:just )?did|it)\s+as\s+(?:a\s+)?(?:skill\s+)?(?:called\s+|named\s+)?"
                         r"[\"“']?(?P<name>[^\"”']{2,60}?)[\"”']?\W*$", re.I)
_RUN_SKILL = re.compile(r"^\W*(?:neko\W+)?(?:please\s+|can you\s+|could you\s+)?(?P<verb>run|do|start|use|repeat)?\s*"
                        r"(?:the\s+|my\s+)?(?P<skill1>skill\s+)?(?P<name>.+?)(?P<skill2>\s+skill)?\W*$", re.I)
_LIST_SKILLS = re.compile(r"\b(what|which|show|list)\b.{0,20}\bskills?\b.{0,20}(know|have|saved|learn)?|"
                          r"\bmy skills\b", re.I)
_FORGET_SKILL = re.compile(r"^\W*(?:neko\W+)?(?:please\s+)?(?:forget|delete|remove)\s+(?:the\s+)?skill\s+"
                           r"[\"“']?(?P<name>.+?)[\"”']?\W*$", re.I)
NOT_REPLAYABLE = {"ask_claude_code"}  # long and unpredictable: ask for it again instead
STEP_GAP_S = 600                      # actions further apart than this belong to different jobs
WINDOW_S = 1800


def _say(tool: str, args: dict[str, Any]) -> str:
    a = args
    if tool == "open_anything":
        return f"open {a.get('target', '')}"
    if tool == "app_control":
        where = f" in {a['window']}" if a.get("window") else ""
        if a.get("action") == "fill":
            return f"type into {a.get('target', '')}{where}"
        return f"{a.get('action', 'click')} {a.get('target', '')}{where}".strip()
    if tool == "window_control":
        return f"{a.get('action', '')} {a.get('name', '')}".strip()
    if tool == "pc_control":
        return str(a.get("action", "")).replace("_", " ")
    if tool == "type_text":
        t = str(a.get("text", ""))
        return f'type "{t[:30]}{"..." if len(t) > 30 else ""}"'
    first = next((str(v) for v in a.values() if isinstance(v, str) and v), "")
    return f"{tool.replace('_', ' ')} {first[:40]}".strip()


def _score(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


class Routines:
    def __init__(self, *, db: Any, bus: Any, executor: Any, paths: Any, settings: Any) -> None:
        self.db, self.bus, self.executor, self.paths, self.s = db, bus, executor, paths, settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ coordinator hooks
    def handle(self, text: str, conv: str, task: Any, token: CancelToken) -> tuple[str, str] | None:
        if (r := parse_reminder(text)) is not None:
            return self._add_reminder(*r)
        if _LIST_REMINDERS.search(text) and len(text.split()) <= 10:
            return self._list_reminders()
        if _CANCEL_REMINDERS.search(text) and len(text.split()) <= 10:
            return self._cancel_reminders()
        if (m := _SAVE_SKILL.match(text.strip())):
            return self.save_skill(m.group("name"), conv, task_id=getattr(task, "id", ""))
        if (m := _FORGET_SKILL.match(text.strip())):
            return self._forget_skill(m.group("name"))
        if _LIST_SKILLS.search(text) and len(text.split()) <= 10:
            return self._list_skills()
        if (skill := self.match_skill(text)) is not None:
            return self.run_skill(skill, task, token)
        return None

    def after_reply(self, text: str, reply: Any) -> None:
        """After a job of several actions: offer to save it as a skill (shown, not spoken)."""
        if not reply.succeeded or self.match_skill(text) is not None or _SAVE_SKILL.match(text.strip()):
            return
        rows = self.db.query("SELECT COUNT(*) AS n FROM tool_invocations WHERE task_id=? AND status='succeeded' "
                             "AND risk_level>=1", (reply.task_id,))
        if rows and rows[0]["n"] >= 2:
            reply.speech = reply.speech or reply.text
            reply.text += '\n\n(Want me to remember how to do this? Say "save that as" and a name.)'

    # ------------------------------------------------------------------ reminders
    def _add_reminder(self, due: datetime | None, what: str) -> tuple[str, str]:
        if not what:
            return "Sure - what should I remind you about, and when?", "curious"
        if due is None:
            return f"When should I remind you to {what}? For example \"at 6 pm\" or \"in 20 minutes\".", "curious"
        if due <= datetime.now() - timedelta(seconds=5):
            return "That time has already passed - when should I remind you?", "curious"
        self.db.execute("INSERT INTO reminders(id, due_at, text, created_at, origin) VALUES (?,?,?,?,?)",
                        (new_id("rm_"), due.timestamp(), what[:300], time.time(), origin.current()))
        return f"Okay, I'll remind you to {what} {_when(due)}.", "happy"

    def pending_reminders(self) -> list[Any]:
        return self.db.query("SELECT * FROM reminders WHERE done_at IS NULL ORDER BY due_at")

    def _list_reminders(self) -> tuple[str, str]:
        rows = self.pending_reminders()
        if not rows:
            return "You have no reminders set.", "neutral"
        lines = [f"- {r['text']} ({_when(datetime.fromtimestamp(r['due_at']))})" for r in rows[:15]]
        return "Your reminders:\n" + "\n".join(lines), "neutral"

    def _cancel_reminders(self) -> tuple[str, str]:
        n = len(self.pending_reminders())
        self.db.execute("UPDATE reminders SET done_at=? WHERE done_at IS NULL", (time.time(),))
        return (f"Done - I cancelled {n} reminder{'s' if n != 1 else ''}." if n else
                "You didn't have any reminders."), "neutral"

    def due_now(self, now: float | None = None) -> list[dict[str, Any]]:
        """Mark due reminders done and return them (missed ones while Neko was off are included)."""
        now = now or time.time()
        rows = self.db.query("SELECT * FROM reminders WHERE done_at IS NULL AND due_at<=?", (now,))
        out = []
        for r in rows:
            self.db.execute("UPDATE reminders SET done_at=? WHERE id=?", (now, r["id"]))
            late = now - r["due_at"] > 120
            out.append({"id": r["id"], "text": r["text"], "late": late,
                        "due": datetime.fromtimestamp(r["due_at"]).strftime("%I:%M %p").lstrip("0")})
        return out

    def start(self) -> None:
        """Background clock (the UI starts it). Due reminders are published as ev.REMINDER."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="neko-reminders")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(10):
            try:
                for r in self.due_now():
                    self.bus.publish(ev.REMINDER, **r)
            except Exception:  # noqa: BLE001 - keep the clock alive
                log.exception("reminder check failed")

    # ------------------------------------------------------------------ skills
    def recent_steps(self, conv: str, *, exclude_task: str = "", now: float | None = None) -> list[dict[str, Any]]:
        now = now or time.time()
        rows = self.db.query(
            """SELECT ti.tool, ti.args_redacted, ti.started_at FROM tool_invocations ti JOIN tasks t ON t.id=ti.task_id
               WHERE t.conversation_id=? AND ti.status='succeeded' AND ti.risk_level>=1 AND ti.started_at>?
                 AND ti.task_id<>? ORDER BY ti.started_at DESC, ti.rowid DESC LIMIT 30""",
            (conv, now - WINDOW_S, exclude_task))
        steps: list[dict[str, Any]] = []
        last = None
        for r in rows:  # newest first: walk back until there's a long pause
            if last is not None and last - r["started_at"] > STEP_GAP_S:
                break
            last = r["started_at"]
            if r["tool"] in NOT_REPLAYABLE or "[REDACTED" in r["args_redacted"]:
                continue
            args = json.loads(r["args_redacted"])
            steps.append({"tool": r["tool"], "args": args, "say": _say(r["tool"], args)})
        return list(reversed(steps))[-15:]

    def save_skill(self, name: str, conv: str, task_id: str = "") -> tuple[str, str]:
        name = re.sub(r"\s+", " ", name).strip(" .")
        if not name:
            return "What should I call it?", "curious"
        steps = self.recent_steps(conv, exclude_task=task_id)
        if not steps:
            return ("I don't have any recent actions to save. Ask me to do the steps first (open apps, click "
                    "buttons...), then say \"save that as\" and a name."), "curious"
        self.db.execute("INSERT INTO skills(id, name, steps_json, created_at) VALUES (?,?,?,?) "
                        "ON CONFLICT(name) DO UPDATE SET steps_json=excluded.steps_json, created_at=excluded.created_at",
                        (new_id("sk_"), name.lower(), json.dumps(steps), time.time()))
        listing = "\n".join(f"{i}. {s['say']}" for i, s in enumerate(steps, 1))
        return (f"Saved the skill \"{name}\" ({len(steps)} step{'s' if len(steps) != 1 else ''}):\n{listing}\n"
                f"Say \"do the {name}\" any time.", "happy")

    def skills(self) -> list[Any]:
        return self.db.query("SELECT * FROM skills ORDER BY name")

    def match_skill(self, text: str) -> Any | None:
        m = _RUN_SKILL.match(text.strip())
        if not m or not (m.group("verb") or m.group("skill1") or m.group("skill2")):
            return None
        said = m.group("name")
        best = max(((_score(said, s["name"]), s) for s in self.skills()), default=None, key=lambda x: x[0])
        return best[1] if best and best[0] >= 0.85 else None

    def run_skill(self, skill: Any, task: Any, token: CancelToken) -> tuple[str, str]:
        steps = json.loads(skill["steps_json"])
        ctx = ToolContext(token=token, paths=self.paths, task_id=getattr(task, "id", None), settings=self.s)
        for i, step in enumerate(steps, 1):
            token.raise_if_cancelled()
            res = self.executor.run(step["tool"], step["args"], ctx)
            if not res.ok:
                return (f"I stopped the skill \"{skill['name']}\" at step {i} ({step['say']}): {res.summary}",
                        "sad")
            time.sleep(0.8)  # let the app catch up before the next click
        self.db.execute("UPDATE skills SET uses=uses+1, last_used_at=? WHERE id=?", (time.time(), skill["id"]))
        return f"Done - \"{skill['name']}\", all {len(steps)} steps.", "happy"

    def _list_skills(self) -> tuple[str, str]:
        rows = self.skills()
        if not rows:
            return ("I haven't learned any skills yet. Ask me to do something with a few steps, then say "
                    "\"save that as\" and a name."), "neutral"
        lines = [f"- {r['name']} ({len(json.loads(r['steps_json']))} steps, used {r['uses']}x)" for r in rows]
        return "Skills I know:\n" + "\n".join(lines), "neutral"

    def _forget_skill(self, name: str) -> tuple[str, str]:
        best = max(((_score(name, s["name"]), s) for s in self.skills()), default=None, key=lambda x: x[0])
        if not best or best[0] < 0.8:
            return f"I don't have a skill called \"{name}\".", "neutral"
        self.db.execute("DELETE FROM skills WHERE id=?", (best[1]["id"],))
        return f"Forgot the skill \"{best[1]['name']}\".", "neutral"


def attach_routines(neko: Any) -> Routines:
    r = Routines(db=neko.db, bus=neko.bus, executor=neko.executor, paths=neko.paths, settings=neko.settings)
    neko.coordinator.extensions.append(r.handle)
    neko.coordinator.after_reply.append(r.after_reply)
    return r


__all__ = ["Routines", "attach_routines", "parse_reminder"]
