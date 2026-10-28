"""Tool armory window: cards for everything Neko can reach, grouped, with a live status pill."""

from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

PILL = {"connected": ("#3DDC97", "connected"), "needs key": ("#FFC94A", "needs a key"), "off": ("#8A96A0", "off"),
        "missing": ("#FF6B6B", "not installed"), "offline": ("#5B86FF", "offline"), "starting": ("#2FE6D6", "starting...")}


class ArmoryWindow(QWidget):
    def __init__(self, neko: Any) -> None:
        super().__init__()
        self.neko = neko
        self.setWindowTitle("Neko - tool armory")
        self.resize(1040, 760)
        self.setStyleSheet("QWidget{background:#06090E;color:#D9F7F4;font-family:'Segoe UI';}"
                           "QFrame#Card{background:#0B1118;border:1px solid #16262E;border-radius:10px;}"
                           "QFrame#Card:hover{border-color:#2FE6D6;}QFrame#Card QLabel{background:transparent;}"
                           "QLineEdit{background:#0B141C;border:1px solid #17323A;border-radius:6px;padding:7px;}"
                           "QPushButton{background:#0B141C;border:1px solid #1E4048;border-radius:6px;padding:6px 12px;}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self.title)
        sub = QLabel("Everything she can reach. Say what you want in plain words and she uses the right tool.")
        sub.setStyleSheet("color:#6B8A90;")
        outer.addWidget(sub)
        row = QGridLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tools... (music, pdf, volume, weather)")
        self.search.textChanged.connect(self.refresh)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(self.search, 0, 0)
        row.addWidget(refresh, 0, 1)
        outer.addLayout(row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self) -> None:
        from ..diagnostics.armory import armory

        items = armory(self.neko)
        q = self.search.text().strip().lower()
        if q:
            items = [i for i in items if q in f"{i.group} {i.name} {i.what}".lower()]
        on = sum(1 for i in items if i.status == "connected")
        self.title.setText(f"<span style='font-size:24px;font-family:Georgia'>Tool armory</span>"
                           f"&nbsp;&nbsp;<span style='color:#6B8A90'>{on} of {len(items)} ready</span>")
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setSpacing(6)
        for group in dict.fromkeys(i.group for i in items):
            head = QLabel(group.upper())
            head.setStyleSheet("color:#6B8A90;letter-spacing:2px;font-size:11px;margin-top:10px;")
            lay.addWidget(head)
            grid = QGridLayout()
            grid.setSpacing(10)
            for k, it in enumerate(i for i in items if i.group == group):
                grid.addWidget(self._card(it), k // 3, k % 3)
            lay.addLayout(grid)
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def _card(self, it: Any) -> QFrame:
        color, label = PILL.get(it.status, ("#8A96A0", it.status))
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        top = QLabel(f"<b>{html.escape(it.name[:1].upper() + it.name[1:])}</b>&nbsp;&nbsp;"
                     f"<span style='color:{color};border:1px solid {color};border-radius:8px;font-size:10px'>"
                     f"&nbsp;{label}&nbsp;</span>")
        top.setTextFormat(Qt.TextFormat.RichText)
        what = QLabel(it.what[:150])
        what.setTextFormat(Qt.TextFormat.PlainText)
        what.setWordWrap(True)
        what.setStyleSheet("color:#9FB4BA;font-size:11px;")
        v.addWidget(top)
        v.addWidget(what)
        if it.status != "connected" and it.how:
            how = QLabel("→ " + it.how)
            how.setTextFormat(Qt.TextFormat.PlainText)
            how.setStyleSheet("color:#FFC94A;font-size:10px;")
            v.addWidget(how)
        card.setMinimumHeight(86)
        return card


__all__ = ["ArmoryWindow"]
