"""The animated core: a golden holographic sphere ("Aurum" theme).

An original design. Layers, back to front (all additive light, so overlaps glow):
  1. soft volumetric haze
  2. a rotating 3D wireframe sphere: meridians + latitude rings, depth-faded so the back
     half is dim and the front half bright
  3. "neural filaments": straight light-threads between nearby surface points
  4. sparks: points scattered over the sphere surface that twinkle
  5. fragmented circuit arcs and tick marks orbiting just outside the sphere
  6. radial spokes from the core to the shell
  7. the core: a bright torus ring with a white-hot centre that reacts to audio

States change colour, speed and intensity (see STATE_COLORS in theme.py):
  idle slow drift · listening brighter core follows the mic · thinking faster spin, filaments
  pulse · tool circuit arcs lock into segments · approval steady pulse in a distinct colour ·
  speaking core and sparks follow the voice · error/offline motion stops.
Reduced motion: one static frame, state shown by colour + label only.
Rendering is plain QPainter at ~30 fps and only while the widget is visible.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..core.types import AssistantState
from .theme import MOTION, state_colors


def _rot(p: tuple[float, float, float], yaw: float, pitch: float) -> tuple[float, float, float]:
    x, y, z = p
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    return x, y, z


def _sphere_point(rng: random.Random) -> tuple[float, float, float]:
    u, v = rng.uniform(-1, 1), rng.uniform(0, math.tau)
    s = math.sqrt(1 - u * u)
    return s * math.cos(v), u, s * math.sin(v)


class CoreOrb(QWidget):
    SPEED = {
        AssistantState.THINKING: 2.4, AssistantState.TOOL: 1.6, AssistantState.TRANSCRIBING: 1.8,
        AssistantState.LISTENING: 1.2, AssistantState.SPEAKING: 1.3,
        AssistantState.ERROR: 0.0, AssistantState.OFFLINE: 0.0,
    }

    def __init__(self, parent: QWidget | None = None, *, reduced_motion: bool = False, size: int = 120) -> None:
        super().__init__(parent)
        self.setMinimumSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("N.E.K.O. core")
        self.state = AssistantState.IDLE
        self.reduced_motion = reduced_motion
        self.level = 0.0
        self._t = 0.0
        rng = random.Random(29)  # fixed seed: the same "constellation" every launch
        self._sparks = [(_sphere_point(rng), rng.uniform(0, math.tau), rng.uniform(0.45, 1.0)) for _ in range(190)]
        # ---- neural network: neurons on the shell, axon links to nearby neurons, plus links to the core
        self._rng = rng
        self._nodes: list[tuple[float, float, float]] = [_sphere_point(rng) for _ in range(110)]
        self._nodes.append((0.0, 0.0, 0.0))            # last node = the core
        self.CORE = len(self._nodes) - 1
        self._links: list[tuple[int, int]] = []
        for i, a in enumerate(self._nodes[:-1]):
            near = sorted(range(len(self._nodes) - 1), key=lambda j: math.dist(a, self._nodes[j]))[1:4]
            for j in near:
                if (j, i) not in self._links and (i, j) not in self._links:
                    self._links.append((i, j))
        for i in rng.sample(range(self.CORE), 16):
            self._links.append((self.CORE, i))
        self._adj: list[list[tuple[int, int]]] = [[] for _ in self._nodes]  # node -> [(link, other end)]
        for li, (a, b) in enumerate(self._links):
            self._adj[a].append((li, b))
            self._adj[b].append((li, a))
        self._core_links = [li for li, (a, _b) in enumerate(self._links) if a == self.CORE]
        self._act = [0.0] * len(self._nodes)         # neuron activation (flash brightness), decays
        self._pulses: list[list[float]] = []         # [link, from_node, progress 0..1, speed, strength]
        self._spawn_acc = 0.0
        self._filaments = [(self._nodes[a], self._nodes[b], rng.uniform(0, math.tau))
                           for a, b in self._links if a != self.CORE]
        # dense bands of short light "shards" on two tilted rings (the data stream look)
        self._shards = []
        for tilt in (0.55, -0.95):
            for _ in range(130):
                a = rng.uniform(0, math.tau)
                r = rng.uniform(0.82, 1.06)
                ln = rng.uniform(0.02, 0.09)
                self._shards.append((tilt, a, r, ln, rng.uniform(0, math.tau)))
        self._arcs = [(rng.uniform(0, 360), rng.uniform(12, 70), rng.uniform(1.04, 1.16), rng.choice((-1, 1)))
                      for _ in range(11)]
        self._ticks = [rng.uniform(0, math.tau) for _ in range(36)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if not reduced_motion:
            self._timer.start(MOTION["frame_ms"])

    # ------------------------------------------------------------------ API
    def set_state(self, state: AssistantState) -> None:
        self.state = state
        self.setAccessibleDescription(state.value)
        self.update()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, level))

    # ---- neural activity -------------------------------------------------------------------
    def _fire(self, node: int, strength: float, exclude_link: int | None = None, fanout: int = 2) -> None:
        """Neuron ``node`` fires: it flashes and sends signals down some of its links."""
        self._act[node] = min(1.5, self._act[node] + strength)
        if strength < 0.12 or len(self._pulses) > 170:
            return
        options = [(li, o) for li, o in self._adj[node] if li != exclude_link]
        for li, _other in self._rng.sample(options, min(fanout, len(options))):
            self._pulses.append([li, node, 0.0, self._rng.uniform(1.6, 3.2), strength * 0.72])

    def stimulate(self, strength: float = 0.5, origin: str = "core") -> None:
        """Feed activity into the network. origin: "core" (N.E.K.O. producing output), "shell"
        (input arriving, e.g. your voice) or "random" (background thought)."""
        strength = max(0.05, min(1.2, strength))
        if origin == "core":
            self._act[self.CORE] = min(1.5, self._act[self.CORE] + strength * 0.6)
            for li in self._rng.sample(self._core_links, min(len(self._core_links), 1 + int(strength * 4))):
                self._pulses.append([li, self.CORE, 0.0, self._rng.uniform(2.2, 3.6), strength])
        elif origin == "shell":
            node = self._rng.randrange(self.CORE)
            self._fire(node, strength, fanout=2)
        else:
            self._fire(self._rng.randrange(self.CORE), strength, fanout=1)

    def _advance(self, dt: float) -> None:
        decay = math.exp(-dt * 3.2)
        self._act = [a * decay for a in self._act]
        alive = []
        for pulse in self._pulses:
            pulse[2] += pulse[3] * dt
            if pulse[2] >= 1.0:
                a, b = self._links[int(pulse[0])]
                target = b if int(pulse[1]) == a else a
                cascade = 0.85 if self.state in (AssistantState.THINKING, AssistantState.TOOL) else 0.6
                if self._rng.random() < cascade:
                    self._fire(target, pulse[4], exclude_link=int(pulse[0]))
                else:
                    self._act[target] = min(1.5, self._act[target] + pulse[4])
            else:
                alive.append(pulse)
        self._pulses = alive
        # spontaneous activity per state (signals per second)
        rate, origin, power = {
            AssistantState.IDLE: (0.8, "random", 0.35),
            AssistantState.THINKING: (9.0, "random", 0.7),
            AssistantState.TOOL: (5.0, "core", 0.9),
            AssistantState.TRANSCRIBING: (6.0, "shell", 0.5),
            AssistantState.LISTENING: (1.0 + 14.0 * self.level, "shell", 0.4 + 0.6 * self.level),
            AssistantState.SPEAKING: (2.0 + 12.0 * self.level, "core", 0.4 + 0.6 * self.level),
            AssistantState.AWAITING_APPROVAL: (0.5, "core", 0.3),
            AssistantState.RECOVERING: (1.5, "random", 0.4),
        }.get(self.state, (0.0, "random", 0.0))
        self._spawn_acc += rate * dt
        while self._spawn_acc >= 1.0:
            self._spawn_acc -= 1.0
            self.stimulate(power, origin)

    def set_reduced_motion(self, on: bool) -> None:
        self.reduced_motion = on
        if on:
            self._timer.stop()
        elif self.isVisible():
            self._timer.start(MOTION["frame_ms"])
        self.update()

    def showEvent(self, e):  # noqa: N802
        if not self.reduced_motion:
            self._timer.start(MOTION["frame_ms"])
        super().showEvent(e)

    def hideEvent(self, e):  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    ACTIVE = {AssistantState.LISTENING, AssistantState.THINKING, AssistantState.SPEAKING,
              AssistantState.TRANSCRIBING, AssistantState.TOOL}

    def _tick(self) -> None:
        # Adaptive frame rate: calm 12 fps when idle, smooth 24 fps while active (saves CPU/battery).
        interval = 42 if (self.state in self.ACTIVE or len(self._pulses) > 6) else 83
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        self._t += interval / 1000 * self.SPEED.get(self.state, 1.0)
        if self.state == AssistantState.SPEAKING and self.level < 0.05:
            self.level = 0.35 + 0.3 * abs(math.sin(self._t * 7.0) * math.sin(self._t * 2.1))
        self._advance(interval / 1000)
        self.update()

    # ------------------------------------------------------------------ painting helpers
    @staticmethod
    def _col(c: QColor, alpha: float) -> QColor:
        out = QColor(c)
        out.setAlphaF(max(0.0, min(1.0, alpha)))
        return out

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        R = min(w, h) / 2 * 0.80
        cx, cy = w / 2, h / 2
        primary, secondary, hot = (QColor(x) for x in state_colors(self.state))
        t = 0.0 if self.reduced_motion else self._t
        yaw, pitch = t * 0.35, 0.38 + 0.06 * math.sin(t * 0.4)
        energy = 0.55 + 0.45 * self.level
        if self.state == AssistantState.AWAITING_APPROVAL:
            energy = 0.6 + 0.3 * (0.5 + 0.5 * math.sin(t * 2.6))
        if self.state in (AssistantState.ERROR, AssistantState.OFFLINE):
            energy = 0.45

        def proj(pt: tuple[float, float, float], scale: float = 1.0) -> tuple[QPointF, float]:
            x, y, z = _rot(pt, yaw, pitch)
            return QPointF(cx + x * R * scale, cy - y * R * scale), z

        # 1. haze
        haze = QRadialGradient(QPointF(cx, cy), R * 1.25)
        haze.setColorAt(0.0, self._col(primary, 0.42 * energy))
        haze.setColorAt(0.55, self._col(secondary, 0.16 * energy))
        haze.setColorAt(1.0, self._col(secondary, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(haze))
        p.drawEllipse(QPointF(cx, cy), R * 1.25, R * 1.25)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # Batched drawing: primitives are grouped into (colour, brightness level, width) buckets
        # and each bucket is drawn with ONE drawLines/drawPoints call. Per-primitive calls cost
        # ~22 ms/frame (66% of a core at 30 fps); batching makes this a small fraction of that.
        LEVELS = 6
        lines: dict[tuple[int, int, float], list[QLineF]] = {}
        dots: dict[tuple[int, int, float], list[QPointF]] = {}
        palette = (primary, hot)

        def add_line(a: QPointF, b: QPointF, hot_col: bool, alpha: float, width: float) -> None:
            # widths 0.8/1.0/1.6 are wireframe (bloomed below); filaments use 0.91, shards 1.5
            lvl = max(0, min(LEVELS - 1, int(alpha * energy * LEVELS)))
            lines.setdefault((int(hot_col), lvl, width), []).append(QLineF(a, b))

        def add_dot(q: QPointF, hot_col: bool, alpha: float, size: float) -> None:
            lvl = max(0, min(LEVELS - 1, int(alpha * energy * LEVELS)))
            dots.setdefault((int(hot_col), lvl, size), []).append(q)

        # 2. wireframe sphere (meridians + latitudes), depth-faded
        def great_circle(points: list[tuple[float, float, float]], width: float, base: float) -> None:
            prev = None
            for pt in points:
                q, z = proj(pt)
                if prev is not None:
                    add_line(prev, q, False, base * (0.25 + 0.75 * (z + 1) / 2), width)
                prev = q

        n = 28
        ring = [i * math.tau / n for i in range(n + 1)]
        for k in range(7):
            phi = k * math.pi / 7
            great_circle([(math.cos(phi) * math.cos(a), math.sin(a), math.sin(phi) * math.cos(a)) for a in ring], 1.0, 0.6)
        for lat in (-0.6, -0.25, 0.25, 0.6):
            rr = math.sqrt(1 - lat * lat)
            great_circle([(rr * math.cos(a), lat, rr * math.sin(a)) for a in ring], 0.8, 0.45)
        great_circle([(math.cos(a), 0.0, math.sin(a)) for a in ring], 1.6, 0.85)

        # 3. neural network: axons (dim until neurons at either end fire), travelling signals, neurons
        node_q: list[QPointF] = []
        node_z: list[float] = []
        for i, pt in enumerate(self._nodes):
            q, z = proj(pt)
            node_q.append(q)
            node_z.append(z if i != self.CORE else 1.0)
        act = self._act
        for a, b in self._links:
            depth = ((node_z[a] + node_z[b]) / 2 + 1) / 2
            glow = min(1.0, (act[a] + act[b]) * 0.6)
            base = 0.10 if a != self.CORE else 0.05
            add_line(node_q[a], node_q[b], glow > 0.55, (base + 0.8 * glow) * depth, 0.91)
        for li, frm, prog, _sp, strength in self._pulses:
            a, b = self._links[int(li)]
            src, dst = (a, b) if int(frm) == a else (b, a)
            pa, pb = self._nodes[src], self._nodes[dst]
            head = tuple(pa[k] + (pb[k] - pa[k]) * prog for k in range(3))
            tail_p = max(0.0, prog - 0.22)
            tail = tuple(pa[k] + (pb[k] - pa[k]) * tail_p for k in range(3))
            qh, zh = proj(head)  # type: ignore[arg-type]
            qt, _ = proj(tail)   # type: ignore[arg-type]
            depth = 0.45 + 0.55 * (zh + 1) / 2
            add_line(qt, qh, True, min(1.0, 0.35 + strength) * depth, 2.2)
            add_dot(qh, True, min(1.0, 0.5 + strength) * depth, 3.0 + 2.0 * strength)
        for i in range(self.CORE):
            if act[i] > 0.06:
                depth = 0.4 + 0.6 * (node_z[i] + 1) / 2
                add_dot(node_q[i], act[i] > 0.4, min(1.0, act[i]) * depth, round(2.0 + 5.0 * min(1.0, act[i])))

        # 3b. shard bands
        for tilt, a0, r, ln, ph in self._shards:
            a = a0 + t * 0.25
            ct, st = math.cos(tilt), math.sin(tilt)
            x1, z1 = r * math.cos(a), r * math.sin(a)
            x2, z2 = r * math.cos(a + ln), r * math.sin(a + ln)
            qa, za = proj((x1, -z1 * st, z1 * ct))
            qb, _ = proj((x2, -z2 * st, z2 * ct))
            fl = 0.5 + 0.5 * math.sin(t * 2.2 + ph)
            add_line(qa, qb, fl > 0.92, (0.2 + 0.7 * fl) * ((za + 1) / 2), 1.5)

        # 4. sparks
        for pt, ph, scale in self._sparks:
            q, z = proj(pt, scale)
            depth = (z + 1) / 2
            tw = 0.5 + 0.5 * math.sin(t * 3.0 + ph)
            size = round((1.5 + 3.0 * tw * depth) * (1 + self.level))
            add_dot(q, tw > 0.9, (0.3 + 0.7 * tw) * depth, float(max(1, size)))

        for (is_hot, lvl, width), segs in lines.items():
            a = (lvl + 1) / LEVELS
            col = palette[is_hot]
            if (width in (0.8, 1.0, 1.6) and not is_hot and len(segs) > 20) or width == 2.2:  # wireframe + signals
                p.setPen(QPen(self._col(col, a * 0.22), width * 3.5))
                p.drawLines(segs)
            p.setPen(QPen(self._col(col, a), width))
            p.drawLines(segs)
        for (is_hot, lvl, size), pts in dots.items():
            pen = QPen(self._col(palette[is_hot], (lvl + 1) / LEVELS), size)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(pts)

        # 5. fragmented circuit arcs + ticks outside the shell
        lock = self.state == AssistantState.TOOL
        for start, span, rad, direction in self._arcs:
            rr = R * rad
            rect = QRectF(cx - rr, cy - rr * 0.97, rr * 2, rr * 1.94)
            ang = (start + direction * t * 25) % 360
            if lock:
                ang = round(ang / 45) * 45
            pen = QPen(self._col(primary, 0.55 * energy), 1.8 if rad > 1.1 else 1.2)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(ang * 16), int(span * 16))
        p.setPen(QPen(self._col(secondary, 0.6 * energy), 2.0))
        for i, ph in enumerate(self._ticks):
            a = ph + t * 0.15 * (1 if i % 2 else -1)
            r1, r2 = R * 1.19, R * (1.23 if i % 3 else 1.28)
            p.drawLine(QPointF(cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                       QPointF(cx + r2 * math.cos(a), cy + r2 * math.sin(a)))

        # 6. core: a glowing ring around a dark "eye", with a halo; flares when it fires signals
        core_fire = min(1.0, self._act[self.CORE])
        energy = min(1.25, energy + 0.35 * core_fire)
        cr = R * (0.16 + 0.05 * self.level + 0.03 * core_fire + 0.008 * math.sin(t * 2))
        halo = QRadialGradient(QPointF(cx, cy), cr * 2.6)
        halo.setColorAt(0.0, self._col(primary, 0.0))
        halo.setColorAt(0.38, self._col(hot, 0.55 * energy))
        halo.setColorAt(0.55, self._col(primary, 0.25 * energy))
        halo.setColorAt(1.0, self._col(primary, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), cr * 2.6, cr * 2.6)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for width, alpha, col, scale in ((R * 0.10, 0.25, primary, 1.0), (R * 0.045, 0.9, hot, 1.0),
                                         (R * 0.015, 1.0, QColor("#FFFFFF"), 1.0), (R * 0.02, 0.55, primary, 1.45)):
            p.setPen(QPen(self._col(col, alpha * energy), max(1.0, width)))
            p.drawEllipse(QPointF(cx, cy), cr * scale, cr * scale * 0.94)
        # inner swirl arcs
        p.setPen(QPen(self._col(hot, 0.7 * energy), max(1.0, R * 0.012)))
        for k in range(3):
            rr = cr * (0.55 + 0.12 * k)
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), int(((t * 90 * (k + 1)) % 360) * 16), int(110 * 16))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        eye = QRadialGradient(QPointF(cx, cy), cr * 0.85)
        eye.setColorAt(0.0, self._col(QColor("#120800"), 0.65))
        eye.setColorAt(1.0, self._col(QColor("#120800"), 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(eye))
        p.drawEllipse(QPointF(cx, cy), cr * 0.85, cr * 0.85)
        p.end()
