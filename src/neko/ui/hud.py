"""Compact floating HUD (docs/UI_UX_SPEC.md section 4).

Frameless, translucent, draggable, optionally always-on-top. It never covers
Windows security prompts: UAC runs on the secure desktop, and approval
dialogs are normal (not top-most) windows. Esc hides the HUD; the tray icon
brings it back.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core.types import AssistantState
from .orb import CoreOrb
from .theme import COLORS, STATE_LABELS


class HudWindow(QWidget):
    submitted = Signal(str)
    mic_pressed = Signal()
    mic_released = Signal()
    capture_requested = Signal()
    stop_requested = Signal()
    emergency_requested = Signal()
    expand_requested = Signal()

    def __init__(self, *, always_on_top: bool, opacity: float, reduced_motion: bool, name: str) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"{name} HUD")
        self.setWindowOpacity(opacity)
        self.resize(470, 240)
        self._drag: QPoint | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)
        self.orb = CoreOrb(self, reduced_motion=reduced_motion, size=150)
        root.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel(name)
        title.setObjectName("Title")
        head.addWidget(title)
        self.loc_pill = QLabel("LOCAL")
        self.loc_pill.setObjectName("Pill")
        self.loc_pill.setToolTip("Where your request is processed")
        self.model_pill = QLabel("no model")
        self.model_pill.setObjectName("Pill")
        self.mic_pill = QLabel("mic off")
        self.mic_pill.setObjectName("Pill")
        for w in (self.loc_pill, self.model_pill, self.mic_pill):
            head.addWidget(w)
        head.addStretch(1)
        for text, tip, sig in (("□", "Open Command Center (Ctrl+E)", self.expand_requested),):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.clicked.connect(sig.emit)
            head.addWidget(b)
        hide = QPushButton("–")
        hide.setObjectName("Ghost")
        hide.setToolTip("Hide HUD (Esc). Bring it back from the tray icon.")
        hide.setAccessibleName("Hide HUD")
        hide.clicked.connect(self.hide)
        head.addWidget(hide)
        col.addLayout(head)

        self.status = QLabel(STATE_LABELS[AssistantState.IDLE])
        self.status.setObjectName("Dim")
        self.status.setAccessibleName("Assistant status")
        col.addWidget(self.status)

        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(False)
        self.output.setMaximumHeight(90)
        self.output.setAccessibleName("Latest reply")
        col.addWidget(self.output)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask N.E.K.O. ...  (Enter to send)")
        self.input.setAccessibleName("Message")
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input, 1)
        self.mic = QPushButton("\U0001F399")
        self.mic.setToolTip("Hold to talk")
        self.mic.setAccessibleName("Hold to talk")
        self.mic.pressed.connect(self.mic_pressed.emit)
        self.mic.released.connect(self.mic_released.emit)
        row.addWidget(self.mic)
        cap = QPushButton("⧉")
        cap.setToolTip("Capture this screen and ask about it")
        cap.setAccessibleName("Capture screen")
        cap.clicked.connect(self.capture_requested.emit)
        row.addWidget(cap)
        self.stop = QPushButton("■")
        self.stop.setObjectName("Danger")
        self.stop.setToolTip("Stop the current reply / speech (Ctrl+.)  -  Shift+click: EMERGENCY STOP")
        self.stop.setAccessibleName("Stop")
        self.stop.clicked.connect(self._stop_clicked)
        row.addWidget(self.stop)
        col.addLayout(row)
        root.addLayout(col, 1)

        QShortcut(QKeySequence("Escape"), self, activated=self.hide)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.expand_requested.emit)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop_requested.emit)

    # ------------------------------------------------------------------ behaviour
    def _submit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.output.clear()
            self.submitted.emit(text)

    def _stop_clicked(self) -> None:
        from PySide6.QtWidgets import QApplication

        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.emergency_requested.emit()
        else:
            self.stop_requested.emit()

    def set_state(self, state: AssistantState, detail: str = "") -> None:
        self.orb.set_state(state)
        label = STATE_LABELS[state]
        self.status.setText(f"{label}  {detail}".strip() if detail else label)

    def append_token(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def set_reply(self, text: str) -> None:
        self.output.setPlainText(text)

    def set_model(self, model: str | None, location: str | None) -> None:
        self.model_pill.setText(model or "no model")
        loc = (location or "local").upper()
        self.loc_pill.setText(loc)
        color = COLORS["ok"] if loc == "LOCAL" else COLORS["warn"]
        self.loc_pill.setStyleSheet(f"color: {color};")

    def set_mic(self, text: str, active: bool = False) -> None:
        self.mic_pill.setText(text)
        self.mic_pill.setStyleSheet(f"color: {COLORS['ok'] if active else COLORS['text_dim']};")

    # ------------------------------------------------------------------ frameless window chrome
    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 18, 18)
        bg = QColor(COLORS["bg"])
        bg.setAlphaF(0.92)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawPath(path)
        p.end()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e):  # noqa: N802
        self._drag = None
