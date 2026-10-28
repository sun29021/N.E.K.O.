"""Music: "Neko, play Blinding Lights" -> find it on YouTube and stream the audio in the background.

* ``find_song``: YouTube search through the optional ``yt-dlp`` package. Nothing is downloaded to
  disk; it only asks YouTube for the song's audio stream address.
* The player itself lives in the desktop app (Qt Multimedia, ``ui/music_player.py``) and is plugged in
  here as ``player``, so this package stays free of GUI imports.
* Tools: ``play_music`` (verified: the player really reports playing) and ``music_control``
  (pause / resume / stop / louder / quieter). Both need ``privacy.allow_network`` for streaming.

Note: YouTube's terms only allow playback in their own apps; this is a personal-use convenience the
owner asked for and it can stop working whenever YouTube changes its site.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from ..core.errors import ToolError
from ..core.types import RiskLevel
from ..tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec


class MusicPlayer(Protocol):
    def play(self, url: str, title: str) -> None: ...
    def control(self, action: str) -> None: ...
    def status(self) -> dict[str, Any]: ...   # {"state": "playing"|"paused"|"loading"|"stopped"|"error", ...}


player: MusicPlayer | None = None  # set by the desktop app
# set by the desktop app too: unmutes / raises a ~0 % volume before playing, returns what it changed
prepare_sound: Callable[[], str] | None = None

MAX_SONG_SECONDS = 3 * 3600  # skip 10-hour loops and live streams


_SONGISH = re.compile(r"\b(song|songs|music|official|audio|lyrics?|video song|full song|mv|remix|feat\.?|ft\.?)\b",
                      re.IGNORECASE)
_NOT_SONG = re.compile(r"\b(reaction|reacts?|reply|review|explained|tutorial|lesson|lecture|interview|podcast|"
                       r"karaoke|how to|news|trailer|documentary|premiere)\b", re.IGNORECASE)


def _song_score(e: dict[str, Any], rank: int) -> float:
    """Prefer real songs: YouTube's Music category, song-like titles, normal song length."""
    title = str(e.get("title") or "")
    score = -rank * 0.6
    if "Music" in (e.get("categories") or []):
        score += 2.0
    if _SONGISH.search(title):
        score += 1.0
    if _NOT_SONG.search(title):
        score -= 2.5
    dur = e.get("duration") or 0
    if 90 <= dur <= 900:
        score += 0.5
    return score


def find_songs(query: str, timeout_s: float = 20.0, n: int = 5) -> list[dict[str, Any]]:
    """Playable YouTube matches, best song first: [{"title", "url", "page", "duration", "channel"}]."""
    try:
        import yt_dlp  # optional dependency
    except ImportError as exc:
        raise ToolError("playing from YouTube needs the 'yt-dlp' package (pip install yt-dlp)") from exc
    search = query if _SONGISH.search(query) else f"{query} song"  # "oporadhi" -> "oporadhi song"
    opts = {"format": "bestaudio[ext=m4a]/bestaudio", "noplaylist": True, "quiet": True, "no_warnings": True,
            "skip_download": True, "default_search": f"ytsearch{n}", "socket_timeout": timeout_s,
            "noprogress": True, "logger": _QuietLogger()}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search, download=False)
    except Exception as exc:  # noqa: BLE001 - yt-dlp raises many kinds
        raise ToolError(f"YouTube search failed: {str(exc)[:160]}") from exc
    entries = [e for e in (info.get("entries") or [info]) if e]
    ok = [(i, e) for i, e in enumerate(entries)
          if not e.get("is_live") and e.get("url") and (e.get("duration") or 0) <= MAX_SONG_SECONDS]
    ok.sort(key=lambda ie: _song_score(ie[1], ie[0]), reverse=True)
    songs = [{"title": str(e.get("title") or query), "url": e["url"], "page": e.get("webpage_url", ""),
              "duration": int(e.get("duration") or 0), "channel": str(e.get("channel") or e.get("uploader") or ""),
              "id": str(e.get("id") or "")}
             for _i, e in ok]
    if not songs:
        raise ToolError(f"I couldn't find a playable song for \"{query}\" on YouTube")
    return songs


# ---------------------------------------------------------------------- up next (like YouTube's autoplay)
_queue: list[dict[str, Any]] = []     # songs to play next: {"id", "title", "duration"}
_played: list[str] = []               # video ids already played this session (no repeats)
_current: dict[str, Any] = {}
_qlock = threading.Lock()


def related_songs(video_id: str, timeout_s: float = 20.0, n: int = 25) -> list[dict[str, Any]]:
    """YouTube's own mix for a song ("Up next"), without the song itself or anything already played."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise ToolError("playing from YouTube needs the 'yt-dlp' package (pip install yt-dlp)") from exc
    opts = {"extract_flat": "in_playlist", "playlistend": n, "quiet": True, "no_warnings": True,
            "skip_download": True, "socket_timeout": timeout_s, "logger": _QuietLogger()}
    url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"couldn't get the next songs: {str(exc)[:160]}") from exc
    out = []
    for e in info.get("entries") or []:
        vid, title, dur = str(e.get("id") or ""), str(e.get("title") or ""), int(e.get("duration") or 0)
        if (not vid or vid == video_id or vid in _played or e.get("live_status") == "is_live"
                or _NOT_SONG.search(title) or dur > 900):
            continue
        out.append({"id": vid, "title": title, "duration": dur})
    return out


def _stream(video_id: str, timeout_s: float = 20.0) -> dict[str, Any]:
    """Audio stream for one YouTube video id, in the same shape as find_songs() results."""
    import yt_dlp

    opts = {"format": "bestaudio[ext=m4a]/bestaudio", "noplaylist": True, "quiet": True, "no_warnings": True,
            "skip_download": True, "socket_timeout": timeout_s, "logger": _QuietLogger()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        e = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return {"title": str(e.get("title") or ""), "url": e["url"], "page": e.get("webpage_url", ""),
            "duration": int(e.get("duration") or 0), "channel": str(e.get("channel") or e.get("uploader") or ""),
            "id": video_id}


def _now_playing(song: dict[str, Any]) -> None:
    """Remember the song and line up what comes after it, in the background."""
    global _current
    _current = song
    if song.get("id"):
        _played.append(song["id"])
        del _played[:-200]

        def fill(vid: str = song["id"]) -> None:
            try:
                songs = related_songs(vid)
            except ToolError:
                return
            with _qlock:
                if _current.get("id") == vid:  # still the same song
                    _queue[:] = songs

        threading.Thread(target=fill, daemon=True, name="neko-up-next").start()


def has_up_next() -> bool:
    return bool(_queue or _current.get("id"))


def _next(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if player is None:
        return ToolResult(False, "music needs the desktop app (run 'python -m neko ui')")
    with _qlock:
        if not _queue and _current.get("id"):
            _queue[:] = related_songs(_current["id"])  # asked before the background list arrived
        upcoming = list(_queue)
    if not upcoming:
        return ToolResult(False, "there's no song lined up - tell me what to play")
    fixed = prepare_sound() if prepare_sound is not None else ""
    problem = ""
    for item in upcoming[:3]:
        ctx.token.raise_if_cancelled()
        with _qlock:
            if item in _queue:
                _queue.remove(item)
        try:
            song = _stream(item["id"])
        except Exception as exc:  # noqa: BLE001 - unavailable / region-blocked: try the next one
            problem = str(exc)[:120]
            continue
        player.play(song["url"], song["title"])
        started, problem = _wait_started()
        if started:
            _now_playing(song)
            return ToolResult(True, f"Playing {song['title']}",
                              {**{k: song[k] for k in ("title", "page", "duration", "channel")}, "fixed_sound": fixed})
    return ToolResult(False, f"the next songs wouldn't play ({problem})")


def find_song(query: str, timeout_s: float = 20.0) -> dict[str, Any]:
    """Best YouTube match: {"title", "url" (audio stream), "page", "duration", "channel"}."""
    return find_songs(query, timeout_s)[0]


class _QuietLogger:
    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


def _wait_started(timeout_s: float = 9.0) -> tuple[bool, str]:
    assert player is not None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:  # streaming needs a moment to buffer
        st = player.status()
        if st.get("state") == "playing":
            return True, ""
        if st.get("state") == "error":
            return False, str(st.get("error", "")) or "player error"
        time.sleep(0.2)
    return False, "didn't start in time"


def _play(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if player is None:
        return ToolResult(False, "music needs the desktop app (run 'python -m neko ui')")
    songs = find_songs(args["query"])
    problem = ""
    # seen live: the song played on a muted PC at 0 % volume and nobody heard it
    fixed = prepare_sound() if prepare_sound is not None else ""
    for song in songs[:3]:  # seen live: a stream link occasionally fails ("Could not open file") - try the next
        ctx.token.raise_if_cancelled()
        player.play(song["url"], song["title"])
        started, problem = _wait_started()
        if started:
            _now_playing(song)
            return ToolResult(True, f"Playing {song['title']}",
                              {**{k: song[k] for k in ("title", "page", "duration", "channel")}, "fixed_sound": fixed})
    return ToolResult(False, f"found songs but none would play ({problem})")

def _verify_play(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    if player is None:
        return False, "no player"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:  # streaming needs a moment to buffer
        st = player.status()
        if st.get("state") == "playing":
            return True, f"player is playing {st.get('title', '')}"
        if st.get("state") == "error":
            return False, f"player error: {st.get('error', '')}"
        time.sleep(0.25)
    return False, "the player didn't start within 10 s"


CONTROLS = ("pause", "resume", "stop", "louder", "quieter")


def _control(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if player is None:
        return ToolResult(False, "music needs the desktop app")
    action = args["action"]
    if action not in CONTROLS:
        return ToolResult(False, f"unknown music action {action}")
    before = player.status()
    if before.get("state") in (None, "stopped") and action != "stop":
        return ToolResult(False, "nothing is playing right now")
    player.control(action)
    return ToolResult(True, f"Music: {action}", player.status())


def _verify_control(args: dict[str, Any], result: ToolResult, ctx: ToolContext) -> tuple[bool, str]:
    if player is None:
        return False, "no player"
    want = {"pause": "paused", "resume": "playing", "stop": "stopped"}.get(args["action"])
    deadline = time.monotonic() + 3
    while want and time.monotonic() < deadline:
        if player.status().get("state") == want:
            return True, f"player is {want}"
        time.sleep(0.1)
    return (True, "volume changed") if not want else (False, f"player did not become {want}")


def register_media_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="play_music", description="Find a song on YouTube and play its audio in the background.",
        params={"query": {"type": "string", "required": True, "max_length": 200,
                          "description": "song and/or artist"}},
        handler=_play, risk=RiskLevel.LOW, category="media", side_effects="plays audio",
        needs_network=True, verifier=_verify_play, timeout_s=45,
    ))
    registry.register(ToolSpec(
        name="play_next_song", description="Skip to the next song (YouTube's 'Up next' for the current song).",
        params={}, handler=_next, risk=RiskLevel.LOW, category="media", side_effects="plays audio",
        needs_network=True, verifier=_verify_play, timeout_s=60,
    ))
    registry.register(ToolSpec(
        name="music_control", description="Pause, resume, stop, or change the volume of the music.",
        params={"action": {"type": "string", "required": True, "enum": list(CONTROLS)}},
        handler=_control, risk=RiskLevel.LOW, category="media", side_effects="changes music playback",
        verifier=_verify_control, timeout_s=10,
    ))


__all__ = ["CONTROLS", "MusicPlayer", "find_song", "has_up_next", "player", "register_media_tools", "related_songs"]
