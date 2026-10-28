"""Emotion tags: the model may start a reply with one tag such as ``[happy]``. The tag is hidden
from the user and used to colour the voice: speaking speed plus a blend of Kokoro voice styles
(brighter for excited, softer for calm or caring). Pure functions, no dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass

EMOTIONS = ("happy", "excited", "playful", "curious", "calm", "caring", "sad", "serious", "surprised")
_WORDS = "|".join(EMOTIONS)
# "[happy] Hi", "(happy) Hi", "*happy* Hi", and - as small models often write it - "happy! Hi" / "Calm. Hi"
_TAG = re.compile(rf"^\s*(?:\[({_WORDS})\]|\(({_WORDS})\)|\*({_WORDS})\*|({_WORDS})[.!:,]+(?=\s))\s*", re.IGNORECASE)
# Also seen live: "Caring I'm so sorry...", "Calm Mm-hm, ..." - a capitalised emotion word followed by a
# capitalised word. "Happy" is excluded here so "Happy birthday" / "Happy New Year" are left alone.
_BARE = re.compile(r"^\s*(Excited|Playful|Curious|Calm|Caring|Sad|Serious|Surprised)\s+(?=[A-Z])")
# ...and lower-case "happy Oh my goodness", "calm Mm-hm" (a real sentence never starts like that)
_BARE_LOWER = re.compile(rf"^\s*({_WORDS})\s+(?=[A-Za-z])")

_CUES: dict[str, tuple[str, ...]] = {
    "excited": ("congratulations", "amazing", "wow", "no way", "awesome", "incredible", "fantastic", "you did it"),
    "happy": ("great to", "glad", "happy to", "good to hear", "nice", "yay", "love that"),
    "caring": ("sorry to hear", "i'm sorry", "that sounds hard", "tough", "here for you", "here to listen",
               "take care", "exhausting", "aw,", "aww"),
    "sad": ("unfortunately", "sadly", "i'm afraid"),
    "curious": ("i wonder", "tell me more", "what do you think"),
    "playful": ("haha", "hehe", "just kidding", "teasing"),
    "surprised": ("oh!", "really?!", "whoa"),
}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️]+")


@dataclass(frozen=True)
class VoiceStyle:
    speed: float
    blend: tuple[tuple[str, float], ...]  # ((voice, weight), ...) mixed with the base voice


STYLES: dict[str, VoiceStyle] = {
    "neutral": VoiceStyle(1.0, ()),
    "happy": VoiceStyle(1.05, (("af_bella", 0.25),)),
    "excited": VoiceStyle(1.12, (("af_bella", 0.35),)),
    "playful": VoiceStyle(1.08, (("af_bella", 0.3),)),
    "curious": VoiceStyle(1.02, ()),
    "surprised": VoiceStyle(1.1, (("af_bella", 0.2),)),
    "calm": VoiceStyle(0.94, (("af_nicole", 0.3),)),
    "caring": VoiceStyle(0.92, (("af_nicole", 0.35),)),
    "sad": VoiceStyle(0.88, (("af_nicole", 0.4),)),
    "serious": VoiceStyle(0.96, ()),
}


def split_emotion(text: str) -> tuple[str, str]:
    """``"[happy] Hi!"`` -> ``("happy", "Hi!")``; untagged text -> ``("neutral", text)``."""
    m = _TAG.match(text or "")
    if m:
        word = next(g for g in m.groups() if g)
        return word.lower(), text[m.end():]
    b = _BARE.match(text or "") or _BARE_LOWER.match(text or "")
    if b:
        return b.group(1).lower(), text[b.end():]
    return "neutral", text


def infer_emotion(text: str) -> str:
    """Emotion from the words of a reply (used when the model's tag is missing)."""
    low = (text or "").lower()
    scores = {e: sum(low.count(c) for c in cues) for e, cues in _CUES.items()}
    best = max(scores, key=lambda e: scores[e])
    if scores[best] == 0:
        return "curious" if low.rstrip().endswith("?") else "neutral"
    return best


def resolve_emotion(tag: str, text: str) -> str:
    """Final voice emotion: the model's tag, unless it is missing or clearly contradicts the words
    (small models tag good news as "caring" quite often)."""
    inferred = infer_emotion(text)
    if tag == "neutral":
        return inferred
    positive, negative = {"excited", "happy", "playful"}, {"caring", "sad"}
    if (tag in negative and inferred in positive) or (tag in positive and inferred in negative):
        return inferred
    return tag


_INLINE = re.compile(rf"\s*[\[(]({_WORDS})[\])]\s*", re.IGNORECASE)


def strip_inline_tags(text: str) -> str:
    """Remove emotion tags the model put in the middle of a reply ("...again. [caring] Okay...")."""
    return _INLINE.sub(" ", text).strip()


def strip_emoji(text: str) -> str:
    return _EMOJI.sub("", text)


def looks_like_tag_prefix(text: str) -> bool:
    """While streaming: could this still turn into an emotion tag? (hold it back if so)"""
    s = text.lstrip()
    if not s or len(s) > 13:
        return False
    if s[0] in "[(*":
        if any(c in s[1:] for c in "])*"):
            return False
        word = s[1:].lower()
    else:
        word = s.lower()
        if re.fullmatch(rf"({_WORDS})[.!:,]+", word):
            return True  # "happy!" - wait for the following space to confirm it is a tag
        if not word.isalpha():
            return False
    return any(e.startswith(word) for e in EMOTIONS)
