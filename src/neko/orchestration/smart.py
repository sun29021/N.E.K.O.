"""Understanding what the user is pointing at (pure functions, unit-tested).

* ``screen_reference``: "what's the problem on this thing?", "explain this error", "what am I looking
  at" -> the user means their screen (unless they named a file, folder or drive).
* ``resolve_folder``: "in D drive project folder analyse my HISAB project" -> D:\\PROJECT\\HISAB.
  Matches explicit paths, "X drive", and project folder names found inside the allowed folders.
* ``coding_request``: should this go to the coding agent, and may it change files?
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCREEN = re.compile(
    r"\b(on|in) (my|the) screen\b|\bwhat (am i|i'?m) (looking at|seeing)\b|\b(look|see) (at )?(this|that)\b|"
    r"\b(this|that|these|those) (thing|error|window|dialog|message|pop-?up|page|screen|chart|graph|picture|"
    r"image|app|program|warning|notification|box|button|setting|thing here)\b|\bwhat('?s| is) (this|that)\b(?! (file|folder))",
    re.IGNORECASE,
)
_DRIVE_OR_FILE = re.compile(
    r"[a-z]:\\|\b[a-z] ?drive\b|\b(folder|directory|file|files|repo|repository|project|codebase|document)s?\b",
    re.IGNORECASE)
_PATH = re.compile(r"\b([A-Za-z]):\\[^\n\"'<>|?*]*")
_DRIVE = re.compile(r"\b([a-z]) ?drive\b", re.IGNORECASE)


def screen_reference(text: str) -> bool:
    return bool(_SCREEN.search(text)) and not _DRIVE_OR_FILE.search(text)


@dataclass
class FolderGuess:
    path: str | None
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


def _children(root: str) -> list[Path]:
    try:
        return [p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith((".", "$"))]
    except OSError:
        return []


def resolve_folder(text: str, roots: list[str]) -> FolderGuess:
    m = _PATH.search(text)
    if m:
        p = m.group(0).rstrip(" .,;")
        return FolderGuess(p, [p], "explicit path")
    low = text.lower()
    drive = _DRIVE.search(text)
    scoped = [r for r in roots if not drive or r.upper().startswith(drive.group(1).upper() + ":")] or roots
    hits = []
    for root in scoped:
        for child in _children(root):
            name = child.name.lower()
            simple = re.sub(r"[^a-z0-9]", "", name)
            if (len(name) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", low)) or (
                    len(simple) >= 4 and simple in re.sub(r"[^a-z0-9]", "", low)):
                hits.append(str(child))
    if len(hits) == 1:
        return FolderGuess(hits[0], hits, "project name mentioned")
    if len(hits) > 1:
        return FolderGuess(None, hits, "several projects match")
    # "project folder" / "projects" in a drive -> the root itself, with its projects as candidates
    for root in scoped:
        base = os.path.basename(root.rstrip("\\/")).lower()
        if base and base in low:
            kids = [str(c) for c in _children(root)]
            if re.search(r"\b(my|this|the) project\b", low) and kids:
                return FolderGuess(None, kids, "which project?")
            return FolderGuess(root, kids, "folder name mentioned")
    if drive and scoped:
        kids = [str(c) for r in scoped for c in _children(r)]
        return FolderGuess(None, kids, "drive mentioned")
    return FolderGuess(None, [], "")


_CODE_WORDS = re.compile(
    r"\b(analy[sz]e|review|audit|explain|understand|improve|refactor|debug|fix|implement|add|build|write|"
    r"create|change|update|upgrade|optimi[sz]e|test)\b.*\b(project|code|codebase|app|program|feature|"
    r"function|bug|repo|script|module)s?\b|\bwhich features?\b|\bwhat features?\b",
    re.IGNORECASE)
_EDIT_WORDS = re.compile(
    r"\b(fix|implement|add|build|write|create|change|update|refactor|modify|edit|rename|delete|remove)\b",
    re.IGNORECASE)
_QUESTION_ONLY = re.compile(r"\b(which|what|suggest|ideas?|recommend|could|should)\b.*\b(add|features?)\b",
                            re.IGNORECASE)


_WEATHER = re.compile(
    r"\b(weather|forecast|temperature|umbrella|humid(ity)?)\b|"
    r"\bwhether\b.*\b(today|tomorrow|tonight|outside|like|forecast|week|weekend)\b|"   # speech-to-text homophone
    r"\b(will|is) it (rain|be (hot|cold|sunny|cloudy|rainy))\b|\b(rain|raining|sunny|hot|cold) (today|tomorrow|tonight)\b",
    re.IGNORECASE)
_PLACE = re.compile(r"\b(?:in|at|for) ([A-Z][\w'-]+(?: [A-Z][\w'-]+)?)")


def weather_request(text: str) -> tuple[bool, str]:
    """(is_weather_question, place or ""). Handles "whether" (a common speech-recognition mix-up)."""
    if not _WEATHER.search(text):
        return False, ""
    m = _PLACE.search(text)
    place = m.group(1) if m and m.group(1).lower() not in ("today", "tomorrow", "the", "my") else ""
    return True, place


def coding_request(text: str) -> tuple[bool, bool]:
    """(is_coding_task, wants_file_changes). Suggesting features is analysis, not editing."""
    if not _CODE_WORDS.search(text):
        return False, False
    wants_edit = bool(_EDIT_WORDS.search(text)) and not _QUESTION_ONLY.search(text)
    return True, wants_edit


_SHOW_AGAIN = re.compile(
    r"\b(show|open|bring)\b.{0,20}\b(again|back|once more)\b|\b(re-?open|open) (the |that )?(panel|last one)\b",
    re.IGNORECASE)
_SHOW = re.compile(
    r"\b(show me|show us|can you show|visuali[sz]e|draw (me )?|diagram|illustrate|let me see|picture of|"
    r"image of|photo of|what does .{1,40} look like)\b",
    re.IGNORECASE)
_SHOW_LEAD = re.compile(
    r"^(hey |ok(ay)? |so |please |neko,? )*(can|could|would) you (please )?|^(please )?|"
    r"\b(show (me|us)|visuali[sz]e|draw( me)?|illustrate|let me see|a (picture|image|photo|diagram) of|"
    r"(picture|image|photo|diagram) of|what does|look like|how)\b|[?.!]+$",
    re.IGNORECASE)


def visual_request(text: str) -> str:
    """"again" (reopen the last visual), "show" (answer in the side panel) or ""."""
    if _SHOW_AGAIN.search(text):
        return "again"
    if _SHOW.search(text) and not screen_reference(text):
        return "show"
    return ""


def visual_topic(text: str) -> str:
    """"show me a picture of the Eiffel Tower" -> "the Eiffel Tower" (for a picture lookup)."""
    topic = _SHOW_LEAD.sub(" ", text)
    topic = re.sub(r"\b(a|an|the|some|me|please|works?|working|forms?|formed|happens?|grows?|made|is|are|does|"
                   r"do|actually|really|exactly)\b", " ", topic, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", topic).strip(" ,.?!")


_DOC = re.compile(
    r"\b(this|that|the|my|these|those)\s+(\w+\s+)?(file|pdf|document|doc|paper|chapter|lecture|slides?|book|"
    r"assignment|presentation|handout|worksheet|syllabus|notes?)\b|\.(pdf|docx?|pptx?|txt)\b|\bpdf\b|"
    r"\bwhat('?s| is) (in )?(this|that|the) (file|one)\b|"
    r"\b(read|open|summari[sz]e|summurize|analy[sz]e|explain|check|study)\b.{0,40}\b(manual|document|handbook|"
    r"slides|presentation|ebook|notes|chapter|book)\b|"
    r"\b(manual|document|handbook|slides|presentation|ebook|pdf)\b.{0,60}\b(read|open|summari[sz]e|summurize|"
    r"analy[sz]e|explain|check|study)\b",
    re.IGNORECASE)
_STUDY = re.compile(
    r"\b(cheat ?sheet|study (notes?|guide)|revision( notes?)?|simpl(er|ify|ified|e version)|easy[- ]to[- ]read|"
    r"exam|test tomorrow|quiz|make (me )?(a )?(short|simple|summary)|key points|"
    r"\d\s?(-|/|to|or)\s?\d\s?pages?|(one|two|three|four|1|2|3|4)[- ]pages?)\b",
    re.IGNORECASE)
_FILE_PATH = re.compile(r"\b[A-Za-z]:\\[^\n\"'<>|?*]+?\.[A-Za-z0-9]{2,5}\b")


def document_request(text: str) -> tuple[bool, bool, str]:
    """(about_a_document, wants_study_material, explicit_file_path_or_"")."""
    path = _FILE_PATH.search(text)
    is_doc = bool(path) or bool(_DOC.search(text))
    if not is_doc:
        return False, False, ""
    return True, bool(_STUDY.search(text)), path.group(0) if path else ""


def pick_named_file(text: str, files: list[str]) -> list[str]:
    """Files whose name shares a meaningful word with the request ("the physics pdf")."""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())} - {
        "this", "that", "file", "files", "make", "simple", "simpler", "exam", "tomorrow", "sheet", "cheat",
        "notes", "page", "pages", "pdf", "document", "analyse", "analyze", "analysis", "read", "tell", "about",
        "what", "have", "based", "with", "from", "easy", "study", "please", "could", "would", "neko"}
    hits = []
    for f in files:
        stem = re.sub(r"[^a-z0-9]+", " ", os.path.splitext(os.path.basename(f))[0].lower())
        if words & set(stem.split()):
            hits.append(f)
    return hits


def is_long_job(text: str) -> bool:
    """Work that can take minutes (project/coding work, study notes from a document): it may run in the
    background while the user keeps chatting."""
    return coding_request(text)[0] or document_request(text)[1] or upgrade_request(text)


_MUSIC_CTRL = [
    # first, so "play next" never searches YouTube for a song called "next"
    ("next", re.compile(r"^\W*(?:(?:hey|ok|neko|please)\W+)*(?:play\s+(?:the\s+)?next(?:\s+(?:one|song|track))?|"
                        r"next(?:\s+(?:one|song|track))?|skip(?:\s+(?:it|this|this one|this song|the song))?|"
                        r"(?:change|another)\s+(?:the\s+)?song)(?:\s+please)?\W*$", re.I)),
    ("pause", re.compile(r"\b(pause|hold)\b.{0,15}\b(music|song|it|that|playback)\b|^\s*pause\s*[.!]?\s*$", re.I)),
    ("resume", re.compile(r"\b(resume|continue|unpause)\b.{0,15}\b(music|song|it|playing)\b|"
                          r"^\s*(resume|unpause)\s*[.!]?\s*$|\bplay (it )?again\b", re.I)),
    ("stop", re.compile(r"\b(stop|turn off|kill|end)\b.{0,15}\b(music|song|playing|playback)\b", re.I)),
    ("louder", re.compile(r"\b(louder|turn (it|the music|that) up|volume up|increase the volume)\b", re.I)),
    ("quieter", re.compile(r"\b(quieter|softer|turn (it|the music|that) down|volume down|lower the volume|"
                           r"decrease the volume)\b", re.I)),
]
_PLAY = re.compile(r"\b(?:play|put on|listen to|start playing)\s+(?P<q>.+)", re.IGNORECASE)
_NOT_MUSIC = re.compile(r"\b(game|games|video game|chess|cards|football|cricket|role|part|trick|fair|"
                        r"along|around|with (me|you)|a role)\b", re.IGNORECASE)
_VAGUE = re.compile(r"^(some|any|a|the)?\s*(music|song|songs|something|anything|this|this song|that song|it)$",
                    re.IGNORECASE)


def music_request(text: str) -> tuple[str, str]:
    """("play", query) | (control action, "") | ("ask", "") for "play some music" | ("", "")."""
    for action, rx in _MUSIC_CTRL:
        if rx.search(text):
            return action, ""
    m = _PLAY.search(text)
    if not m or _NOT_MUSIC.search(m.group("q")):
        return "", ""
    q = re.sub(r"\b(on|from) (youtube|yt|spotify)\b|\bfor me\b|\bplease\b|\bsong\b(?= by)", " ", m.group("q"),
               flags=re.IGNORECASE)
    q = re.sub(r"^(the|a)\s+song\s+", "", re.sub(r"\s+", " ", q)).strip(" ,.!?")
    if not q or _VAGUE.match(q):
        return "ask", ""
    return "play", q


_LEAD = r"^\W*(?:(?:hey|ok(?:ay)?|please|neko|nico|can you|could you|would you|will you|go ahead and|just)[\s,]+)*"
_PC_RULES: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(_LEAD + r"(?:cancel|abort|stop)\s+(?:the\s+)?(?:shut\s?down|restart|reboot)\b", re.I), "pc_control",
     {"action": "cancel_shutdown"}),
    (re.compile(_LEAD + r"(?:shut\s?down|turn off|power off)\s+(?:my |the |this )?(?:pc|computer|laptop)\b", re.I),
     "pc_control", {"action": "shutdown"}),
    (re.compile(_LEAD + r"(?:restart|reboot)\s+(?:my |the |this )?(?:pc|computer|laptop)\b", re.I), "pc_control",
     {"action": "restart"}),
    (re.compile(_LEAD + r"(?:put\s+(?:my |the )?(?:pc|computer|laptop)\s+to\s+sleep|sleep mode)\b", re.I),
     "pc_control", {"action": "sleep"}),
    (re.compile(_LEAD + r"lock\s+(?:my |the |this )?(?:pc|computer|laptop|screen)\b", re.I), "pc_control",
     {"action": "lock"}),
    (re.compile(_LEAD + r"(?:unmute(?:\s+(?:the |my )?(?:pc|sound|volume|audio|computer|speakers?))?|turn\s+(?:the\s+|my\s+)?"
                r"(?:sound|audio|speakers?)\s+(?:back\s+)?on|sound\s+on)\W*$", re.I), "pc_control", {"action": "unmute"}),
    (re.compile(_LEAD + r"(?:mute(?:\s+(?:the |my )?(?:pc|sound|volume|audio|computer|speakers?))?|turn\s+(?:the\s+|my\s+)?"
                r"(?:sound|audio|speakers?)\s+off|sound\s+off)\W*$", re.I), "pc_control", {"action": "mute"}),
    (re.compile(_LEAD + r"(?:turn\s+(?:the\s+)?volume\s+up|volume\s+up|increase\s+(?:the\s+)?volume|"
                r"turn\s+(?:it\s+)?up(?:\s+the\s+volume)?|make\s+it\s+louder)\b", re.I), "pc_control",
     {"action": "volume_up"}),
    (re.compile(_LEAD + r"(?:turn\s+(?:the\s+)?volume\s+down|volume\s+down|decrease\s+(?:the\s+)?volume|"
                r"lower\s+(?:the\s+)?volume|turn\s+(?:it\s+)?down|make\s+it\s+quieter)\b", re.I), "pc_control",
     {"action": "volume_down"}),
    (re.compile(_LEAD + r"(?:next|skip)\s+(?:song|track)\b", re.I), "pc_control", {"action": "next_track"}),
    (re.compile(_LEAD + r"previous\s+(?:song|track)\b", re.I), "pc_control", {"action": "previous_track"}),
]
_WINDOW = re.compile(_LEAD + r"(?P<a>close|minimi[sz]e|maximi[sz]e|switch to|go to|focus|bring up)\s+(?:the\s+|my\s+)?"
                     r"(?P<n>.+?)(?:\s+window|\s+app)?\W*$", re.I)
_OPEN = re.compile(_LEAD + r"(?:open|launch|start|run|open up|pull up)\s+(?:the\s+|my\s+|a\s+)?(?P<t>.+?)\W*$", re.I)
_GOOGLE = re.compile(_LEAD + r"(?:google|search (?:google|the web|online|youtube) for|look up)\s+(?P<q>.+?)\W*$", re.I)
_TYPE = re.compile(_LEAD + r"(?:type|write)\s+(?:this|out|the text)?\s*[:\-]?\s*[\"\u201c](?P<t>.+?)[\"\u201d]\W*$", re.I)
_NOT_PC = re.compile(r"\b(yourself|you|project|file|pdf|document|chapter|notes?|folder)\b", re.I)


def pc_command(text: str) -> tuple[str, dict[str, Any]] | None:
    """Deterministic PC commands: ("tool", args) or None. 'open spotify', 'volume up', 'lock my pc',
    'close chrome', 'shut down my pc' (asks first), 'search google for cats'."""
    for rx, tool, args in _PC_RULES:
        if rx.search(text):
            return tool, dict(args)
    m = _GOOGLE.search(text)
    if m:
        site = "youtube" if "youtube" in text.lower() else "google"
        q = urllib.parse.quote_plus(m.group("q").strip())
        return "open_anything", {"target": ("https://www.youtube.com/results?search_query=" if site == "youtube"
                                            else "https://www.google.com/search?q=") + q}
    m = _TYPE.search(text)
    if m:
        return "type_text", {"text": m.group("t")}
    m = _WINDOW.search(text)
    if m and not _NOT_PC.search(m.group("n")):
        a = m.group("a").lower()
        action = {"close": "close", "switch to": "focus", "go to": "focus", "focus": "focus", "bring up": "focus"}.get(
            a, "minimize" if a.startswith("minim") else "maximize")
        if action == "focus" and re.search(r"\b(sleep|bed)\b", m.group("n"), re.I):
            return None
        return "window_control", {"name": m.group("n").strip(), "action": action}
    m = _OPEN.search(text)
    if m and len(m.group("t").split()) <= 6:
        return "open_anything", {"target": m.group("t").strip()}
    return None


_UPGRADE = re.compile(
    r"\b(upgrade|improve|update|extend|teach|modify|reprogram)\s+(yourself|your\s?self|your (own )?code)\b|"
    r"\b(add|build|give)\b.{0,40}\b(to|for)\s+yourself\b|\bgive yourself\b.{0,30}\b(ability|feature|skill|power)\b|"
    r"\bself[- ]upgrade\b", re.IGNORECASE)


def upgrade_request(text: str) -> bool:
    """'Upgrade yourself so you can read Excel files' -> Claude Code improves N.E.K.O. (with approval)."""
    return bool(_UPGRADE.search(text))


_GENDER = re.compile(r"\b(use|switch to|change to|talk (?:in|with|like)|speak (?:in|with|like)|be|sound like|give me)\b.{0,15}"
                     r"\b(?P<g>male|man|boy|guy|female|woman|girl|lady)(?:'s)?\b(?:\s+voice)?|"
                     r"\b(?P<g2>male|female)\s+voice\b", re.IGNORECASE)
_BANGLA = re.compile(r"\b(speak|talk|reply|answer|say it|respond)\b.{0,20}\b(bangla|bengali|bangali)\b|"
                     r"\bbangla\s*(?:y|te|e)?\s+(kotha\s+)?(bolo|bolben|bolun|kao|koro)\b|\u09ac\u09be\u0982\u09b2\u09be\u09df|"
                     r"\u09ac\u09be\u0982\u09b2\u09be\u09df\s+\u09ac\u09b2\u09cb", re.IGNORECASE)
_ENGLISH = re.compile(r"\b(speak|talk|reply|answer|respond)\b.{0,20}\benglish\b|\benglish\s*e\s+(bolo|kotha)\b|"
                      r"\u0987\u0982\u09b0\u09c7\u099c\u09bf\u09a4\u09c7", re.IGNORECASE)


def voice_command(text: str) -> tuple[str, str] | None:
    """('gender', 'male'|'female') or ('language', 'bn'|'en') for 'use a male voice', 'speak Bangla'..."""
    m = _GENDER.search(text)
    if m and re.search(r"\b(voice|sound|talk|speak|be)\b", text, re.IGNORECASE):
        g = (m.group("g") or m.group("g2") or "").lower()
        return "gender", "male" if g in ("male", "man", "boy", "guy") else "female"
    if _BANGLA.search(text):
        return "language", "bn"
    if _ENGLISH.search(text):
        return "language", "en"
    return None
