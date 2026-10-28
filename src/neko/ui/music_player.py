"""Background music player (Qt Multimedia, FFmpeg backend). Installed as ``neko.media.player``.

The engine calls ``play``/``control`` from its worker thread; those calls are forwarded to the GUI
thread through queued signals (Qt Multimedia objects must live on one thread). ``status`` is a
lock-protected snapshot, so the tool verifier can poll it from any thread.

Ducking: while Neko listens or speaks, the music drops to a quarter of its volume so she can hear
you and you can hear her; it comes back afterwards.
"""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

DUCK = 0.25
STEP = 0.15


class MusicPlayer(QObject):
    _play_req = Signal(str, str)
    _control_req = Signal(str)
    _duck_req = Signal(bool)
    now_playing = Signal(str)            # title ("" when stopped) - for the orb's caption
    state_changed = Signal(str)          # playing / paused / loading / stopped / error
    finished = Signal()                  # a song played to its end (not stopped by you): autoplay the next

    def __init__(self, volume: float = 0.6) -> None:
        super().__init__()
        self._player = QMediaPlayer(self)
        self._out = QAudioOutput(self)
        self._player.setAudioOutput(self._out)
        self._volume = max(0.0, min(1.0, volume))
        self._ducked = False
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {"state": "stopped", "title": ""}
        self._apply_volume()
        self._play_req.connect(self._do_play)
        self._control_req.connect(self._do_control)
        self._duck_req.connect(self._do_duck)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media)
        self._player.errorOccurred.connect(self._on_error)

    # ------------------------------------------------------------------ any thread
    def play(self, url: str, title: str) -> None:
        self._set(state="loading", title=title, error="")
        self._play_req.emit(url, title)

    def control(self, action: str) -> None:
        self._control_req.emit(action)

    def duck(self, on: bool) -> None:
        self._duck_req.emit(on)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status, volume=round(self._volume, 2))

    def _set(self, **kw: Any) -> None:
        with self._lock:
            before = self._status.get("state")
            self._status.update(kw)
            after = self._status.get("state")
        if after != before:
            self.state_changed.emit(str(after))

    # ------------------------------------------------------------------ GUI thread
    @Slot(str, str)
    def _do_play(self, url: str, title: str) -> None:
        self._player.stop()
        self._player.setSource(QUrl(url))
        self._player.play()
        self.now_playing.emit(title)

    @Slot(str)
    def _do_control(self, action: str) -> None:
        if action == "pause":
            self._player.pause()
        elif action == "resume":
            self._player.play()
        elif action == "stop":
            self._player.stop()
            self._player.setSource(QUrl())
            self._set(state="stopped", title="")
            self.now_playing.emit("")
        elif action in ("louder", "quieter"):
            self._volume = max(0.05, min(1.0, self._volume + (STEP if action == "louder" else -STEP)))
            self._apply_volume()

    @Slot(bool)
    def _do_duck(self, on: bool) -> None:
        self._ducked = on
        self._apply_volume()

    def _apply_volume(self) -> None:
        self._out.setVolume(self._volume * (DUCK if self._ducked else 1.0))

    def _on_state(self, st: QMediaPlayer.PlaybackState) -> None:
        if st == QMediaPlayer.PlaybackState.PlayingState:
            self._set(state="playing")
        elif st == QMediaPlayer.PlaybackState.PausedState:
            self._set(state="paused")
        elif self.status()["state"] not in ("loading", "error"):
            self._set(state="stopped")

    def _on_media(self, ms: QMediaPlayer.MediaStatus) -> None:
        if ms == QMediaPlayer.MediaStatus.EndOfMedia:
            self._set(state="stopped", title="")
            self.now_playing.emit("")
            self.finished.emit()

    def _on_error(self, _err: QMediaPlayer.Error, msg: str) -> None:
        self._set(state="error", error=msg[:200])

    def shutdown(self) -> None:
        self._player.stop()
