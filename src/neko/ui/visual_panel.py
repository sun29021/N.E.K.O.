"""Side panel that opens next to the orb when the user says "show me ...".

Holographic glass card in Neko's teal/gold style: a title, an optional picture and the answer as
Markdown. It slides in beside the orb, closes itself after a while (not while the mouse is over
it), and "show me again" reopens the last one. Content is untrusted text: it is rendered as Markdown
only (no HTML, no remote loading) - pictures arrive as bytes fetched by the engine.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

TEAL = QColor("#2FE6D6")
GOLD = QColor("#E8B04A")


class VisualPanel(QWidget):
    def __init__(self, *, always_on_top: bool = True, close_after_s: int = 90) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Neko - visual")
        self.resize(420, 560)
        self._close_after_s = close_after_s
        self._accent = TEAL
        self._scan = 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(10)
        self.title = QLabel(self)
        self.title.setWordWrap(True)
        self.title.setStyleSheet(f"color:{GOLD.name()}; font-size:17px; font-weight:600; letter-spacing:1px;"
                                 "background:transparent;")
        self.picture = QLabel(self)
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet("background:transparent;")
        self.body = QTextBrowser(self)
        self.body.setOpenLinks(False)
        self.body.setStyleSheet(
            "QTextBrowser{background:transparent; border:none; color:#D9F7F4; font-size:13px;}"
            "QScrollBar:vertical{background:transparent; width:6px;}"
            "QScrollBar::handle:vertical{background:rgba(47,230,214,90); border-radius:3px;}")
        self.source = QLabel(self)
        self.source.setStyleSheet("color:rgba(217,247,244,120); font-size:10px; background:transparent;")
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(8)
        lay.addWidget(self.title)
        lay.addWidget(self.picture)
        lay.addWidget(self.body, 1)
        lay.addLayout(self.buttons)
        lay.addWidget(self.source)
        self.close_btn = QPushButton("×", self)
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("QPushButton{color:#2FE6D6; background:transparent; border:none; font-size:18px;}"
                                     "QPushButton:hover{color:#FFC94A;}")
        self.close_btn.clicked.connect(self.dismiss)

        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self._auto_close)
        self._fx = QTimer(self)
        self._fx.timeout.connect(self._tick)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._fade.finished.connect(lambda: self.hide() if self._closing else None)
        self._closing = False

    # ------------------------------------------------------------------ content
    def show_visual(self, payload: dict[str, Any], anchor: QRect | None = None, accent: str | None = None) -> None:
        self._accent = QColor(accent) if accent else TEAL
        self.title.setText(str(payload.get("title") or "Here you go"))
        self.body.setMarkdown(str(payload.get("markdown") or ""))
        img = payload.get("image")
        pm = QPixmap()
        if isinstance(img, (bytes, bytearray)) and pm.loadFromData(bytes(img)):
            self.picture.setPixmap(pm.scaled(376, 220, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
            self.picture.show()
        else:
            self.picture.clear()
            self.picture.hide()
        while self.buttons.count():
            item = self.buttons.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for path in payload.get("files") or []:  # files Neko just made (study PDFs): open on click
            label = "Open " + ("cheat sheet" if "cheat sheet" in path.lower() else "notes") + " PDF"
            btn = QPushButton(label, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("QPushButton{color:#04121A; background:#2FE6D6; border:none; padding:6px 12px;"
                              "font-weight:600;} QPushButton:hover{background:#FFC94A;}")
            btn.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
            self.buttons.addWidget(btn)
        self.buttons.addStretch(1)
        src = str(payload.get("source") or "")
        kind = payload.get("kind")
        self.source.setText(src if kind == "study" else f"picture & summary: {src}" if src else "")
        self.source.setVisible(bool(src))
        self._open(anchor)

    def _place(self, anchor: QRect | None) -> QPoint:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if anchor is None:
            return QPoint(screen.right() - self.width() - 24, screen.top() + 60)
        x = anchor.left() - self.width() - 12                      # left of the orb ...
        if x < screen.left() + 8:
            x = anchor.right() + 12                                # ... or right of it near the left edge
        y = max(screen.top() + 8, min(anchor.center().y() - self.height() // 2, screen.bottom() - self.height() - 8))
        return QPoint(x, y)

    def _open(self, anchor: QRect | None) -> None:
        self._closing = False
        end = self._place(anchor)
        start = QPoint(end.x() + (40 if anchor is not None and end.x() < anchor.left() else -40), end.y())
        self._fade.stop()
        self._slide.stop()
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._scan = 0.0
        self._fx.start(30)
        for anim, a, b, ms in ((self._fade, 0.0, 0.97, 420), (self._slide, start, end, 480)):
            anim.setDuration(ms)
            anim.setStartValue(a)
            anim.setEndValue(b)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
        if self._close_after_s > 0:
            self._auto.start(self._close_after_s * 1000)

    def _auto_close(self) -> None:
        if self.underMouse():
            self._auto.start(10_000)   # still reading: wait
            return
        self.dismiss()

    def dismiss(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._auto.stop()
        self._fade.stop()
        self._fade.setDuration(500)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.start()

    # ------------------------------------------------------------------ look
    def _tick(self) -> None:
        self._scan += 0.035
        if self._scan >= 1.0:
            self._fx.stop()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        self.close_btn.move(self.width() - 36, 10)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        cut = 18.0
        path = QPainterPath()  # sci-fi card: clipped top-left and bottom-right corners
        path.moveTo(r.left() + cut, r.top())
        path.lineTo(r.right(), r.top())
        path.lineTo(r.right(), r.bottom() - cut)
        path.lineTo(r.right() - cut, r.bottom())
        path.lineTo(r.left(), r.bottom())
        path.lineTo(r.left(), r.top() + cut)
        path.closeSubpath()
        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, QColor(6, 22, 28, 232))
        bg.setColorAt(1, QColor(3, 8, 14, 240))
        p.fillPath(path, bg)
        a = QColor(self._accent)
        a.setAlpha(170)
        p.setPen(QPen(a, 1.4))
        p.drawPath(path)
        g = QColor(GOLD)
        g.setAlpha(200)
        p.setPen(QPen(g, 2.2))
        p.drawLine(int(r.left() + cut + 6), int(r.top() + 1), int(r.left() + cut + 70), int(r.top() + 1))
        p.drawLine(int(r.right() - cut - 70), int(r.bottom() - 1), int(r.right() - cut - 6), int(r.bottom() - 1))
        faint = QColor(self._accent)
        faint.setAlpha(18)
        p.setPen(QPen(faint, 1))
        for y in range(int(r.top()) + 6, int(r.bottom()), 4):  # holographic scan lines
            p.drawLine(int(r.left()) + 2, y, int(r.right()) - 2, y)
        if self._fx.isActive():  # entrance sweep
            y = r.top() + r.height() * self._scan
            sweep = QColor(self._accent)
            sweep.setAlpha(int(140 * (1 - self._scan)))
            p.setPen(QPen(sweep, 2))
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        p.end()
