"""Orb-only presence: a frameless, transparent, always-on-top window showing just the HoloCore,
with a soft subtitle line under it that fades out after she has finished talking.

Interaction (no panel):
  drag             move it anywhere
  double-click     open the Command Center
  click            stop her talking / stop the current answer
  right-click      menu: type a message, always-listen, mute voice, capture screen, resume, quit
  start typing     while the orb has focus, a small input appears next to it (Enter sends, Esc closes)

It exposes the same attributes/signals as HudWindow, so the Controller works with either.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QLineEdit, QMenu, QVBoxLayout, QWidget

from ..core.types import AssistantState
from .holo import HoloCore
from .theme import STATE_LABELS


class _Caption(QLabel):
    """Subtitle text with a dark outline so it is readable over any wallpaper."""

    def paintEvent(self, _e):  # noqa: N802
        if not self.text():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        f = self.font()
        metrics = self.fontMetrics()
        lines = self._wrap(self.text(), metrics)
        y = metrics.ascent() + 2
        for line in lines:
            x = (self.width() - metrics.horizontalAdvance(line)) / 2
            path.addText(x, y, f, line)
            y += metrics.lineSpacing()
        p.setPen(QPen(QColor(0, 0, 0, 200), 3.2))
        p.drawPath(path)
        p.fillPath(path, QColor("#EAFDFB"))
        p.end()

    def _wrap(self, text: str, metrics) -> list[str]:  # noqa: ANN001
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if metrics.horizontalAdvance(trial) > self.width() - 8 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines[-3:]  # last three lines only, like live subtitles


class _NullButton:
    """Stands in for the HUD's mic button (the orb has none)."""

    def setToolTip(self, _t: str) -> None:  # noqa: N802
        pass


class OrbWindow(QWidget):
    submitted = Signal(str)
    mic_pressed = Signal()
    mic_released = Signal()
    capture_requested = Signal()
    stop_requested = Signal()
    emergency_requested = Signal()
    expand_requested = Signal()
    listen_toggled = Signal(bool)
    mute_toggled = Signal(bool)
    resume_requested = Signal()
    quit_requested = Signal()
    music_requested = Signal(str)        # pause / resume / stop from the right-click menu
    brain_requested = Signal()
    armory_requested = Signal()

    def __init__(self, *, always_on_top: bool, opacity: float, reduced_motion: bool, name: str, size: int = 260,
                 idle_hide_s: int = 240) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(name)
        self.setWindowOpacity(opacity)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.orb = HoloCore(self, reduced_motion=reduced_motion, size=size)
        lay.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.caption = _Caption(self)
        self.caption.setFixedSize(int(size * 1.6), 64)
        f = QFont("Segoe UI Variable Text", 10)
        f.setWeight(QFont.Weight.DemiBold)
        self.caption.setFont(f)
        lay.addWidget(self.caption, 0, Qt.AlignmentFlag.AlignHCenter)
        self.resize(int(size * 1.6), size + 64)
        self.status = self  # Controller calls hud.status.setText(...)
        self.mic = _NullButton()
        self._drag: QPoint | None = None
        self._moved = False
        self._listening = False
        self._muted = False
        self._stopped = False
        self._fade = QTimer(self)
        self._fade.setSingleShot(True)
        self._fade.timeout.connect(lambda: self._set_caption(""))
        self._text = ""
        # quick input popup
        self.input = QLineEdit()
        self.input.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                                  | Qt.WindowType.WindowStaysOnTopHint)
        self.input.setPlaceholderText(f"Message {name}...  (Enter to send, Esc to close)")
        self.input.setMinimumWidth(360)
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        self.setToolTip(f"{name} - double-click: Command Center, right-click: menu, type to chat")
        # fade away when idle, materialise again on activity
        self._opacity = opacity
        self._vanished = False
        self._idle_hide_s = idle_hide_s
        self.music_state = "stopped"   # kept up to date by the controller (for the menu)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self.vanish)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(lambda: self.hide() if self._vanished else None)
        if idle_hide_s > 0:
            self._idle.start(idle_hide_s * 1000)

    # ------------------------------------------------------------------ presence
    def _activity(self) -> None:
        if self._idle_hide_s > 0:
            self._idle.start(self._idle_hide_s * 1000)
        if self._vanished or not self.isVisible():
            self.appear()

    def start_hidden(self) -> None:
        """Start invisible (e.g. at Windows sign-in); the first activity - her name, a reply - brings her in."""
        self._vanished = True
        self._idle.stop()
        self.setWindowOpacity(0.0)
        self.hide()

    def appear(self) -> None:
        """Cyberpunk entrance: fade in while the rings draw themselves with glitch scan lines."""
        if not self._vanished and self.isVisible():
            return
        self._vanished = False
        self._anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.orb.materialize()
        self._anim.setDuration(650)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(self._opacity)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def vanish(self) -> None:
        """Idle for a while: dissolve and get out of the way (she still listens for her name)."""
        if self._vanished or self.orb.state != AssistantState.IDLE or self.input.isVisible():
            if not self._vanished and self._idle_hide_s > 0:
                self._idle.start(30_000)  # busy right now - check again soon
            return
        self._vanished = True
        self.orb.dematerialize()
        self._anim.stop()
        self._anim.setDuration(1200)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.start()

    # ------------------------------------------------------------------ HUD-compatible API
    def setText(self, text: str) -> None:  # noqa: N802 - status line -> caption
        self._show_caption(text, hold_ms=6000)

    def set_state(self, state: AssistantState, detail: str = "") -> None:
        self.orb.set_state(state)
        if state != AssistantState.IDLE:
            self._activity()
        if state in (AssistantState.ERROR, AssistantState.OFFLINE, AssistantState.AWAITING_APPROVAL):
            self._show_caption(f"{STATE_LABELS[state]} {detail}".strip(), hold_ms=8000)
        elif state == AssistantState.LISTENING and detail:
            self._show_caption(detail, hold_ms=4000)

    def show_subtitle(self, text: str) -> None:
        """Words she is speaking right now (word by word, in time with her voice)."""
        if self._vanished:
            self._activity()
        self._show_caption(text, hold_ms=2500)

    def append_token(self, text: str) -> None:
        if self._vanished:
            self._activity()
        self._text += text
        self._show_caption(self._text, hold_ms=12000)

    def set_reply(self, text: str) -> None:
        self._text = text
        self._activity()
        self._show_caption(text, hold_ms=12000) if text else None

    def set_model(self, model: str | None, location: str | None) -> None:
        self.setToolTip(f"{self.windowTitle()} - {model or 'no model'} ({(location or 'local').upper()})\n"
                        "double-click: Command Center, right-click: menu, type to chat")

    def set_mic(self, text: str, active: bool = False) -> None:
        self._listening = active

    def set_stopped(self, stopped: bool) -> None:
        self._stopped = stopped

    # ------------------------------------------------------------------ caption
    def _show_caption(self, text: str, hold_ms: int) -> None:
        self._set_caption(text.replace("\n", " ").strip())
        self._fade.start(hold_ms)

    def _set_caption(self, text: str) -> None:
        self.caption.setText(text)
        self.caption.update()
        if not text:
            self._text = ""

    # ------------------------------------------------------------------ input
    def open_input(self, first_char: str = "") -> None:
        self._activity()
        g = self.frameGeometry()
        self.input.move(g.center().x() - self.input.width() // 2, g.bottom() + 6)
        self.input.setText(first_char)
        self.input.show()
        self.input.raise_()
        self.input.activateWindow()
        self.input.setFocus()

    def _submit(self) -> None:
        text = self.input.text().strip()
        self.input.hide()
        self.input.clear()
        if text:
            self._text = ""
            self.submitted.emit(text)

    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        if obj is self.input and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.input.hide()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.stop_requested.emit()
        elif e.text() and e.text().isprintable():
            self.open_input(e.text())
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
            self._moved = True

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and not self._moved:
            QTimer.singleShot(250, self._single_click)  # wait to see if it's a double-click
        self._drag = None

    def _single_click(self) -> None:
        if not getattr(self, "_dbl", False):
            self.stop_requested.emit()
        self._dbl = False

    def mouseDoubleClickEvent(self, _e):  # noqa: N802
        self._dbl = True
        self.expand_requested.emit()

    def contextMenuEvent(self, e):  # noqa: N802
        m = QMenu(self)
        items = [("Type a message...", lambda: self.open_input()),
                 ("Ask about my screen", self.capture_requested.emit),
                 None]
        for it in items:
            if it is None:
                m.addSeparator()
                continue
            a = QAction(it[0], m)
            a.triggered.connect(it[1])
            m.addAction(a)
        listen = QAction("Always listen (say \"Neko\")", m, checkable=True, checked=self._listening)
        listen.toggled.connect(self.listen_toggled.emit)
        m.addAction(listen)
        mute = QAction("Mute her voice", m, checkable=True, checked=self._muted)
        mute.toggled.connect(lambda on: (setattr(self, "_muted", on), self.mute_toggled.emit(on)))
        m.addAction(mute)
        if self.music_state in ("playing", "paused", "loading"):  # music controls, one click
            m.addSeparator()
            for text, action in ((("Pause music", "pause") if self.music_state != "paused" else ("Resume music", "resume")),
                                 ("Stop music", "stop")):
                a = QAction(text, m)
                a.triggered.connect(lambda _=False, act=action: self.music_requested.emit(act))
                m.addAction(a)
        m.addSeparator()
        if self._stopped:
            a = QAction("Resume actions (emergency stop is on)", m)
            a.triggered.connect(self.resume_requested.emit)
            m.addAction(a)
        else:
            a = QAction("EMERGENCY STOP", m)
            a.triggered.connect(self.emergency_requested.emit)
            m.addAction(a)
        for text, sig in (("Neko's brain", self.brain_requested), ("Tool armory", self.armory_requested),
                          ("Open Command Center", self.expand_requested), ("Hide", None), ("Quit N.E.K.O.", self.quit_requested)):
            a = QAction(text, m)
            a.triggered.connect(sig.emit if sig is not None else self.hide)
            m.addAction(a)
        m.exec(e.globalPos())
