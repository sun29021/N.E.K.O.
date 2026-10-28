"""Neko's brain map: a slowly rotating 3D-style knowledge graph (QPainter, numpy layout).

Glowing spheres = things she knows (memories, projects, documents, words, tools, brains, voice), lines =
how they connect. Drag to rotate, scroll to zoom, click a node to inspect it (only it and its links
light up), double-click a document/project to open it, type in the search box to find something, click
the legend to hide/show a kind.
"""

from __future__ import annotations

import math
import os
import random
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

COLORS = {"core": "#FFC94A", "topic": "#E8B04A", "memory": "#2FE6D6", "project": "#3DDC97",
          "document": "#5B86FF", "word": "#9B7BFF", "tool": "#FF6FB5", "brain": "#FF8A3D", "voice": "#EDEDED"}
NAMES = {"core": "Core", "topic": "Topics", "memory": "Memories", "project": "Projects", "document": "Documents",
         "word": "Vocabulary", "tool": "Tools", "brain": "Brains", "voice": "Voice"}
BG = QColor(4, 7, 12)


def layout_3d(ids: list[str], edges: list[tuple[int, int]], weights: list[float], steps: int = 260,
              seed: int = 7) -> Any:
    """Force-directed layout in 3D: linked nodes attract, all nodes repel, heavy hubs sit near the centre."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = len(ids)
    pos = rng.normal(0, 1, (n, 3))
    if n < 2:
        return pos * 0
    w = np.asarray(weights, dtype=float)
    e = np.asarray(edges, dtype=int).reshape(-1, 2)
    for step in range(steps):
        d = pos[:, None, :] - pos[None, :, :]
        dist2 = (d ** 2).sum(-1) + 0.01
        rep = (d / dist2[..., None] ** 1.5).sum(1) * 0.045
        att = np.zeros_like(pos)
        if len(e):
            v = pos[e[:, 1]] - pos[e[:, 0]]
            np.add.at(att, e[:, 0], v * 0.06)
            np.add.at(att, e[:, 1], -v * 0.06)
        grav = -pos * (0.01 + 0.02 * (w[:, None] - 1).clip(0, 3))
        cool = 1.0 - step / steps
        move = (rep + att + grav) * (0.6 * cool + 0.05)
        norm = np.linalg.norm(move, axis=1, keepdims=True).clip(1e-6)
        pos += move * np.minimum(1.0, 0.25 / norm)
    pos -= pos.mean(0)
    return pos / max(1e-6, float(np.abs(pos).max()))


class BrainCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(600, 420)
        self.graph: Any = None
        self.ids: list[str] = []
        self.pos: Any = None
        self.deg: dict[str, int] = {}
        self.adj: dict[str, set[str]] = {}
        self.yaw, self.pitch, self.zoom = 0.0, -0.25, 1.0
        self.spin = True
        self.hidden: set[str] = set()
        self.selected: str | None = None
        self.hover: str | None = None
        self.matches: set[str] = set()
        self.on_select: Any = None
        self._drag: QPointF | None = None
        self._proj: list[tuple[float, float, float, float, str]] = []  # x, y, r, depth, id
        self._legend: list[tuple[QRectF, str]] = []
        self._stars = [(random.random(), random.random(), random.random()) for _ in range(140)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_graph(self, graph: Any) -> None:
        self.graph = graph
        self.ids = list(graph.nodes)
        index = {nid: i for i, nid in enumerate(self.ids)}
        edges = [(index[a], index[b]) for a, b in graph.edges if a in index and b in index]
        self.adj = {nid: set() for nid in self.ids}
        for a, b in graph.edges:
            if a in self.adj and b in self.adj:
                self.adj[a].add(b)
                self.adj[b].add(a)
        self.deg = {nid: len(v) for nid, v in self.adj.items()}
        weights = [graph.nodes[i].weight + math.sqrt(self.deg[i]) / 3 for i in self.ids]
        self.pos = layout_3d(self.ids, edges, weights)
        self.update()

    # ------------------------------------------------------------------ interaction
    def _tick(self) -> None:
        if self.spin and self._drag is None:
            self.yaw += 0.0035
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802, ANN001
        for rect, kind in self._legend:
            if rect.contains(e.position()):
                self.hidden.symmetric_difference_update({kind})
                return
        self._drag = e.position()
        self._press = e.position()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802, ANN001
        if self._drag is not None:
            d = e.position() - self._drag
            self.yaw += d.x() * 0.006
            self.pitch = max(-1.4, min(1.4, self.pitch + d.y() * 0.006))
            self._drag = e.position()
        else:
            self.hover = self._hit(e.position())
            self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802, ANN001
        moved = (e.position() - getattr(self, "_press", e.position())).manhattanLength()
        self._drag = None
        if moved < 5:
            self.select(self._hit(e.position()))

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802, ANN001
        nid = self._hit(e.position())
        if nid and (nid.startswith("doc:") or nid.startswith("proj:")):
            path = nid.split(":", 1)[1]
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))  # you double-clicked it

    def wheelEvent(self, e) -> None:  # noqa: N802, ANN001
        self.zoom = max(0.4, min(4.0, self.zoom * (1.12 if e.angleDelta().y() > 0 else 1 / 1.12)))

    def select(self, nid: str | None) -> None:
        self.selected = nid
        if self.on_select:
            self.on_select(nid)

    def _hit(self, p: QPointF) -> str | None:
        best, bd = None, 1e9
        for x, y, r, _z, nid in self._proj:
            d = math.hypot(p.x() - x, p.y() - y)
            if d <= max(r, 6) + 3 and d < bd:
                best, bd = nid, d
        return best

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, _e) -> None:  # noqa: N802, ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), BG)
        for sx, sy, sb in self._stars:  # faint star dust
            c = QColor(120, 160, 200, int(25 + 50 * sb))
            p.setPen(c)
            p.drawPoint(QPointF(sx * w, sy * h))
        if self.graph is None or self.pos is None or not len(self.ids):
            p.setPen(QColor("#2FE6D6"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Building her brain map...")
            p.end()
            return
        cy, sy_ = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        scale = min(w, h) * 0.42 * self.zoom
        proj: dict[str, tuple[float, float, float, float]] = {}
        for i, nid in enumerate(self.ids):
            x, y, z = self.pos[i]
            x, z = x * cy - z * sy_, x * sy_ + z * cy
            y, z = y * cp - z * sp, y * sp + z * cp
            f = 2.8 / (2.8 + z)
            proj[nid] = (w / 2 + x * scale * f, h / 2 + y * scale * f, f, z)
        focus = self.selected or self.hover
        lit = ({focus} | self.adj.get(focus, set())) if focus else set()
        visible = {nid for nid in self.ids if self.graph.nodes[nid].kind not in self.hidden}
        # links
        for a, b in self.graph.edges:
            if a not in visible or b not in visible:
                continue
            xa, ya, fa, _ = proj[a]
            xb, yb, fb, _ = proj[b]
            hot = focus is not None and (a == focus or b == focus)
            col = QColor(COLORS[self.graph.nodes[a if a == focus else b].kind]) if hot else QColor(47, 230, 214)
            col.setAlpha(170 if hot else (14 if focus else int(18 + 22 * min(fa, fb))))
            p.setPen(QPen(col, 1.4 if hot else 0.7))
            p.drawLine(QPointF(xa, ya), QPointF(xb, yb))
        # nodes, back to front
        order = sorted(visible, key=lambda nid: -proj[nid][3])
        self._proj = []
        for nid in order:
            node = self.graph.nodes[nid]
            x, y, f, z = proj[nid]
            r = (2.2 + 1.9 * math.sqrt(self.deg.get(nid, 0) + 1) * node.weight ** 0.5) * f * (0.8 + 0.2 * self.zoom)
            dim = focus is not None and nid not in lit
            base = QColor(COLORS.get(node.kind, "#2FE6D6"))
            if nid in self.matches:
                base = QColor("#FFFFFF")
            alpha = 60 if dim else 255
            if node.kind in ("core", "topic") or nid == focus:  # glow
                glow = QRadialGradient(QPointF(x, y), r * 3.2)
                gc = QColor(base)
                gc.setAlpha(40 if dim else 90)
                glow.setColorAt(0, gc)
                gc.setAlpha(0)
                glow.setColorAt(1, gc)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(glow))
                p.drawEllipse(QPointF(x, y), r * 3.2, r * 3.2)
            g = QRadialGradient(QPointF(x - r * 0.35, y - r * 0.35), r * 1.4)
            hi = QColor(base).lighter(160)
            hi.setAlpha(alpha)
            lo = QColor(base).darker(170)
            lo.setAlpha(alpha)
            g.setColorAt(0, hi)
            g.setColorAt(0.55, QColor(base.red(), base.green(), base.blue(), alpha))
            g.setColorAt(1, lo)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), r, r)
            self._proj.append((x, y, r, z, nid))
            big = self.deg.get(nid, 0) >= 6 or node.kind == "core"
            if (big and not dim) or nid in lit or nid in self.matches:
                p.setPen(QColor(230, 240, 245, 230 if not dim else 90))
                p.setFont(QFont("Segoe UI", max(7, int((8 + (3 if big else 0)) * f))))
                p.drawText(QPointF(x - r, y + r + 12 * f), node.label[:34])
        self._draw_legend(p)
        p.end()

    def _draw_legend(self, p: QPainter) -> None:
        counts = self.graph.counts()
        x, y = self.width() - 168, 16
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 16, 24, 210))
        p.drawRoundedRect(QRectF(x - 10, y - 8, 160, 24 + 20 * len(COLORS)), 8, 8)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(140, 160, 170))
        p.drawText(QPointF(x, y + 6), "FILTER  (click to hide)")
        self._legend = []
        for i, kind in enumerate(COLORS):
            yy = y + 22 + i * 20
            off = kind in self.hidden
            c = QColor(COLORS[kind])
            c.setAlpha(70 if off else 255)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(x + 5, yy - 4), 5, 5)
            p.setPen(QColor(120, 130, 140) if off else QColor(220, 230, 235))
            p.drawText(QPointF(x + 18, yy), NAMES[kind])
            p.drawText(QPointF(x + 120, yy), str(counts.get(kind, 0)))
            self._legend.append((QRectF(x - 6, yy - 14, 150, 20), kind))


class BrainWindow(QWidget):
    """The brain map window: inspector + search on the left, the 3D graph on the right."""

    def __init__(self, neko: Any) -> None:
        super().__init__()
        self.neko = neko
        self.setWindowTitle("Neko - brain")
        self.resize(1280, 780)
        self.setStyleSheet("QWidget{background:#04070C;color:#D9F7F4;font-family:'Segoe UI';}"
                           "QLineEdit{background:#0B141C;border:1px solid #17323A;border-radius:6px;padding:6px;}"
                           "QListWidget{background:#070D14;border:none;}"
                           "QListWidget::item:selected{background:#123038;}"
                           "QPushButton{background:#0B141C;border:1px solid #1E4048;border-radius:6px;padding:5px 10px;}"
                           "QPushButton:hover{border-color:#2FE6D6;}")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        side = QVBoxLayout()
        side.setContentsMargins(14, 14, 8, 14)
        title = QLabel("<b style='font-size:15px;letter-spacing:2px;color:#FFC94A'>NEKO BRAIN</b>")
        self.stats = QLabel("")
        self.stats.setStyleSheet("color:#6B8A90;font-size:11px;")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search her brain...")
        self.search.textChanged.connect(self._search)
        self.inspector = QLabel("Click a node to focus it: only that node and its links light up.")
        self.inspector.setWordWrap(True)
        self.inspector.setTextFormat(Qt.TextFormat.RichText)
        self.inspector.setStyleSheet("background:#070D14;border-radius:8px;padding:10px;font-size:12px;")
        self.links = QListWidget()
        self.links.itemClicked.connect(lambda it: self.canvas.select(it.data(Qt.ItemDataRole.UserRole)))
        bar = QHBoxLayout()
        for text, fn in (("Fit", self._fit), ("Pause", self._toggle_spin), ("Rebuild", self.rebuild)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
            if text == "Pause":
                self._spin_btn = b
        for wdg in (title, self.stats, self.search):
            side.addWidget(wdg)
        side.addLayout(bar)
        side.addWidget(QLabel("<span style='color:#6B8A90;font-size:11px'>INSPECTOR</span>"))
        side.addWidget(self.inspector)
        side.addWidget(QLabel("<span style='color:#6B8A90;font-size:11px'>CONNECTED TO</span>"))
        side.addWidget(self.links, 1)
        panel = QWidget()
        panel.setLayout(side)
        panel.setFixedWidth(300)
        self.canvas = BrainCanvas()
        self.canvas.on_select = self._inspect
        root.addWidget(panel)
        root.addWidget(self.canvas, 1)
        QTimer.singleShot(50, self.rebuild)

    def rebuild(self) -> None:
        from ..memory.brain import build_brain

        g = build_brain(self.neko)
        self.canvas.set_graph(g)
        self.stats.setText(f"{len(g.nodes)} nodes - {len(g.edges)} connections")
        self._inspect(None)

    def _fit(self) -> None:
        self.canvas.zoom, self.canvas.pitch = 1.0, -0.25
        self.canvas.select(None)

    def _toggle_spin(self) -> None:
        self.canvas.spin = not self.canvas.spin
        self._spin_btn.setText("Spin" if not self.canvas.spin else "Pause")

    def _search(self, text: str) -> None:
        g = self.canvas.graph
        if g is None:
            return
        q = text.strip().lower()
        self.canvas.matches = {nid for nid, n in g.nodes.items() if q and q in n.label.lower()} if q else set()
        if len(self.canvas.matches) == 1:
            self.canvas.select(next(iter(self.canvas.matches)))

    def _inspect(self, nid: str | None) -> None:
        self.links.clear()
        g = self.canvas.graph
        if g is None or nid is None or nid not in g.nodes:
            self.inspector.setText("Click a node to focus it: only that node and its links light up. "
                                   "Double-click a document or project to open it.")
            return
        n = g.nodes[nid]
        color = COLORS.get(n.kind, "#2FE6D6")
        import html

        detail = html.escape(n.detail).replace("\n", "<br>")
        self.inspector.setText(f"<span style='color:{color}'>&#9679;</span> <b>{html.escape(n.label)}</b><br>"
                               f"<span style='color:#6B8A90'>{NAMES.get(n.kind, n.kind)} - "
                               f"{len(self.canvas.adj.get(nid, ()))} connections</span><br><br>{detail[:600]}")
        for other in sorted(self.canvas.adj.get(nid, ()), key=lambda o: -self.canvas.deg.get(o, 0)):
            on = g.nodes[other]
            it = QListWidgetItem(f"●  {on.label}")
            it.setForeground(QColor(COLORS.get(on.kind, "#2FE6D6")))
            it.setData(Qt.ItemDataRole.UserRole, other)
            self.links.addItem(it)


__all__ = ["BrainCanvas", "BrainWindow", "layout_3d"]
