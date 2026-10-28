"""Fast, deterministic intent classification (no model call).

On a 4 GB GPU, spending a second model call on classification would double
latency, so v0.1 uses transparent rules. Each result carries the rule that
fired, so routing stays explainable. A small LLM classifier can be plugged in
later behind the same function signature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.types import TaskKind


@dataclass
class Intent:
    kind: TaskKind
    rule: str
    memory_action: str | None = None     # remember | forget | recall
    memory_text: str = ""
    sensitive: bool = False
    deep: bool = False                   # user asked for careful, slower reasoning


_REMEMBER = re.compile(r"^\s*(please\s+)?(remember|note)\s+(that\s+)?(?P<x>.+)$", re.IGNORECASE | re.DOTALL)
_FORGET = re.compile(r"^\s*(please\s+)?forget\s+(about\s+|that\s+)?(?P<x>.+)$", re.IGNORECASE | re.DOTALL)
_RECALL = re.compile(r"\b(what do you (know|remember) about|do you remember)\b", re.IGNORECASE)
_BN_REMEMBER = re.compile(r"(মনে রাখো|মনে রেখো)")

_CODING = re.compile(
    r"\b(code|python|javascript|typescript|function|class|bug|stack ?trace|traceback|exception|compile|"
    r"refactor|regex|sql|powershell script|unit test|git|error:|syntaxerror|typeerror|npm|pip)\b|```",
    re.IGNORECASE,
)
_PLANNING = re.compile(
    r"\b(plan|step[- ]by[- ]step|strategy|compare|pros and cons|design|architecture|schedule|roadmap|"
    r"break (it|this) down|analy[sz]e|why does|explain in detail)\b",
    re.IGNORECASE,
)
_COMMAND = re.compile(
    r"^\s*(open|launch|start|list|show|find|search|move|rename|create|write|run|check)\b", re.IGNORECASE
)
_SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|yo|thanks|thank you|good (morning|night|evening)|how are you|ok|okay|cool|nice)\b[\s!.?]*$",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(r"\b(password|bank|salary|medical|diagnos|passport|nid|private key|pin code)\b", re.IGNORECASE)


_DEEP = re.compile(r"\b(think (hard|carefully|deeply|it through)|deep ?think|in depth|in-depth|thoroughly)\b",
                   re.IGNORECASE)


def classify(text: str, *, has_image: bool = False) -> Intent:
    if _DEEP.search(text) and not has_image:
        return Intent(TaskKind.PLANNING, "deep-think request", sensitive=bool(_SENSITIVE.search(text)), deep=True)
    sensitive = bool(_SENSITIVE.search(text))
    if has_image:
        return Intent(TaskKind.VISION, "image attached", sensitive=sensitive)
    if m := _REMEMBER.match(text):
        return Intent(TaskKind.MEMORY, "remember command", "remember", m.group("x").strip(), sensitive)
    if _BN_REMEMBER.search(text):
        return Intent(TaskKind.MEMORY, "remember command (bn)", "remember", _BN_REMEMBER.sub("", text).strip(), sensitive)
    if m := _FORGET.match(text):
        return Intent(TaskKind.MEMORY, "forget command", "forget", m.group("x").strip(), sensitive)
    if _RECALL.search(text):
        return Intent(TaskKind.MEMORY, "recall question", "recall", text, sensitive)
    if _SMALL_TALK.match(text):
        return Intent(TaskKind.SMALL_TALK, "greeting/short reply", sensitive=sensitive)
    if _CODING.search(text):
        return Intent(TaskKind.CODING, "coding keywords", sensitive=sensitive)
    if _COMMAND.match(text):
        return Intent(TaskKind.COMMAND, "imperative command verb", sensitive=sensitive)
    if _PLANNING.search(text) or len(text) > 600:
        return Intent(TaskKind.PLANNING, "planning keywords or long request", sensitive=sensitive)
    return Intent(TaskKind.QUESTION, "default", sensitive=sensitive)
