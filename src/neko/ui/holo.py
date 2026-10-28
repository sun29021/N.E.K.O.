"""HoloCore: the holographic ring interface (original design, after the owner's teal/gold reference).

Layout, centre outwards: a bright core with crosshair and three fine rings; a segmented inner
"circuit" ring; a double mid ring with tick marks, glowing segment bars and four triangle markers;
an outer gold ring with dense ticks; and gold "antenna" spikes radiating outward with dots on the tips.

Each activity has its own motion, not just a colour change:
  idle       slow breathing (scale + glow, ~5 s period), gentle counter-rotation
  listening  ripples travel INWARD, antenna spikes stretch with your voice, core brightens
  thinking   inner rings spin fast in opposite directions, segment bars flicker, data sparks fly out
  coding     rings rotate in discrete gear-like steps, bars fill like progress, a radar sweep scans
  tool       quick lock-step pulses
  speaking   ripples travel OUTWARD in time with her real voice, a waveform ring breathes with it
  approval   steady slow pulse;  error/offline: still and dim

Colour follows her emotion (from the reply) and fades smoothly; gold accents stay constant.
Batched drawing + adaptive frame rate keep CPU low; nothing is drawn while hidden.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..core.types import AssistantState as S

EMOTION_COLORS = {
    "neutral": "#2FE6D6", "calm": "#3EC6FF", "curious": "#9B7BFF", "happy": "#FFC94A",
    "excited": "#FF8A3D", "playful": "#FF6FB5", "caring": "#6EE7A8", "sad": "#5B86FF",
    "serious": "#B8F4FF", "surprised": "#FFE45C",
}
STATE_OVERRIDE = {S.ERROR: "#FF4D5E", S.OFFLINE: "#5E6B73", S.AWAITING_APPROVAL: "#FFB547"}
GOLD = QColor("#E8B04A")


def _lerp(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class HoloCore(QWidget):
    ACTIVE = {S.LISTENING, S.THINKING, S.SPEAKING, S.TRANSCRIBING, S.TOOL}

    def __init__(self, parent: QWidget | None = None, *, reduced_motion: bool = False, size: int = 240) -> None:
        super().__init__(parent)
        self.setMinimumSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("N.E.K.O.")
        self.state = S.IDLE
        self.mode = "idle"            # idle | listening | thinking | coding | tool | speaking | approval | still
        self.emotion = "neutral"
        self.reduced_motion = reduced_motion
        self.level = 0.0
        self._t = 0.0
        self._col = QColor(EMOTION_COLORS["neutral"])
        self._target = QColor(self._col)
        self._ripples: list[list[float]] = []      # [radius_fraction, direction(+1 out / -1 in), strength]
        self._sparks: list[list[float]] = []       # [angle, radius_fraction, speed, life]
        self._burst = 0.0
        rng = random.Random(7)
        self._rng = rng
        self._bars = [(rng.uniform(0, 360), rng.uniform(8, 28)) for _ in range(9)]
        self._spikes = [(rng.uniform(0, math.tau), rng.uniform(1.12, 1.42)) for _ in range(34)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if not reduced_motion:
            self._timer.start(50)

    # ------------------------------------------------------------------ API (same as CoreOrb)
    def set_state(self, state: S) -> None:
        self.state = state
        self.mode = {S.LISTENING: "listening", S.TRANSCRIBING: "listening", S.THINKING: "thinking",
                     S.TOOL: "tool", S.SPEAKING: "speaking", S.AWAITING_APPROVAL: "approval",
                     S.ERROR: "still", S.OFFLINE: "still"}.get(state, "idle")
        self._retarget()
        self.update()

    def set_mode(self, mode: str) -> None:
        """Override the motion style, e.g. "coding" while a coding task runs."""
        self.mode = mode

    def set_emotion(self, emotion: str) -> None:
        self.emotion = emotion if emotion in EMOTION_COLORS else "neutral"
        self._retarget()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, level))

    def stimulate(self, strength: float = 0.5, origin: str = "core") -> None:
        """Activity burst (generated text, tool calls, voice)."""
        self._burst = min(1.0, self._burst + strength * 0.4)
        if origin == "shell":
            self._ripples.append([1.15, -1.0, strength])
        else:
            for _ in range(1 + int(strength * 2)):
                self._sparks.append([self._rng.uniform(0, math.tau), 0.18, self._rng.uniform(0.9, 1.6), 1.0])
            if len(self._ripples) < 6:
                self._ripples.append([0.2, 1.0, strength])

    def materialize(self) -> None:
        """Cyberpunk entrance: rings draw in from nothing with glitch jitter and scan lines (~0.9 s)."""
        self._boot = 0.0
        self._boot_dir = 1.0

    def dematerialize(self) -> None:
        """Reverse of materialize, used while the window fades away."""
        self._boot = min(getattr(self, "_boot", 1.0), 1.0)
        self._boot_dir = -1.0

    def set_reduced_motion(self, on: bool) -> None:
        self.reduced_motion = on
        if on:
            self._timer.stop()
        elif self.isVisible():
            self._timer.start(50)
        self.update()

    def _retarget(self) -> None:
        self._target = QColor(STATE_OVERRIDE.get(self.state, EMOTION_COLORS.get(self.emotion, "#2FE6D6")))

    def showEvent(self, e):  # noqa: N802
        if not self.reduced_motion:
            self._timer.start(50)
        super().showEvent(e)

    def hideEvent(self, e):  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    # ------------------------------------------------------------------ simulation
    def _advance(self, dt: float) -> None:
        speed = {"thinking": 2.6, "coding": 1.6, "tool": 1.8, "listening": 1.2, "speaking": 1.3,
                 "still": 0.0, "approval": 0.6}.get(self.mode, 1.0)
        self._t += dt * speed if speed else 0.0
        self._breath_t = getattr(self, "_breath_t", 0.0) + dt
        boot = getattr(self, "_boot", 1.0)
        direction = getattr(self, "_boot_dir", 1.0)
        self._boot = max(0.0, min(1.0, boot + direction * dt / (0.9 if direction > 0 else 1.1)))
        self._col = _lerp(self._col, self._target, min(1.0, dt * 2.5))
        self._burst *= math.exp(-dt * 2.0)
        if self.mode == "speaking" and self.level < 0.05:
            self.level = 0.3 + 0.3 * abs(math.sin(self._breath_t * 6.5))
        # automatic ripples per mode
        rate = {"listening": 0.6 + 3.0 * self.level, "speaking": 0.8 + 3.0 * self.level, "thinking": 1.2,
                "coding": 0.7}.get(self.mode, 0.0)
        if rate and self._rng.random() < rate * dt:
            if self.mode == "listening":
                self._ripples.append([1.15, -1.0, 0.4 + 0.6 * self.level])
            else:
                self._ripples.append([0.2, 1.0, 0.4 + 0.6 * self.level])
        if self.mode == "thinking" and self._rng.random() < 6 * dt:
            self._sparks.append([self._rng.uniform(0, math.tau), 0.2, self._rng.uniform(0.9, 1.7), 1.0])
        for r in self._ripples:
            r[0] += r[1] * dt * 0.55
            r[2] *= math.exp(-dt * 0.9)
        self._ripples = [r for r in self._ripples if 0.12 < r[0] < 1.3 and r[2] > 0.04][-10:]
        for s in self._sparks:
            s[1] += s[2] * dt * 0.5
            s[3] -= dt * 0.8
        self._sparks = [s for s in self._sparks if s[3] > 0 and s[1] < 1.45][-60:]

    def _tick(self) -> None:
        entering = getattr(self, "_boot", 1.0) < 1.0 or getattr(self, "_boot_dir", 1.0) < 0
        interval = 42 if (self.state in self.ACTIVE or self.mode == "coding" or self._burst > 0.1 or entering) else 66
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        self._advance(interval / 1000)
        self.update()

    # ------------------------------------------------------------------ painting
    @staticmethod
    def _a(c: QColor, alpha: float) -> QColor:
        out = QColor(c)
        out.setAlphaF(max(0.0, min(1.0, alpha)))
        return out

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        bt = getattr(self, "_breath_t", 0.0)
        breath = 0.5 + 0.5 * math.sin(bt * math.tau / 5.0)          # ~5 s breathing
        still = self.mode == "still"
        boot = getattr(self, "_boot", 1.0)
        ease = 1 - (1 - boot) ** 3                                    # entrance easing
        scale = 1.0 + (0.025 * (breath - 0.5) * 2 if self.mode == "idle" else 0.0) + 0.03 * self.level
        scale *= 0.55 + 0.45 * ease
        R = min(w, h) / 2 * 0.62 * scale
        col = self._col
        t = 0.0 if self.reduced_motion else self._t
        glow = (0.78 + 0.22 * breath if self.mode == "idle" else 1.0) * (0.5 if still else 1.0) + 0.3 * self._burst
        glow *= ease
        if boot < 1.0 and self._rng.random() < 0.55 * (1 - boot):    # glitch: the whole HUD jitters sideways
            cx += self._rng.uniform(-10, 10) * (1 - boot)
        if boot <= 0.001:
            p.end()
            return
        lines: dict[tuple[str, float, float], list[QLineF]] = {}

        def L(a: QPointF, b: QPointF, which: str, alpha: float, width: float) -> None:
            lv = round(max(0.05, min(1.0, alpha * glow)) * 5) / 5
            lines.setdefault((which, lv, width), []).append(QLineF(a, b))

        def pol(r: float, ang: float) -> QPointF:
            return QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang))

        def arc(r: float, start_deg: float, span_deg: float, color: QColor, alpha: float, width: float,
                bloom: bool = True) -> None:
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            if bloom:  # soft glow under the line
                pen = QPen(self._a(color, alpha * glow * 0.22), width * 4)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))
            pen = QPen(self._a(color, alpha * glow), width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))

        # background haze
        haze = QRadialGradient(QPointF(cx, cy), R * 1.5)
        haze.setColorAt(0.0, self._a(col, 0.32 * glow))
        haze.setColorAt(0.6, self._a(col, 0.10 * glow))
        haze.setColorAt(1.0, self._a(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(haze))
        p.drawEllipse(QPointF(cx, cy), R * 1.5, R * 1.5)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        step = self.mode == "coding"
        def rot(speed: float, stepdeg: float = 15.0) -> float:
            a = t * speed
            return (math.floor(a / stepdeg) * stepdeg + (a % stepdeg) ** 3 / stepdeg ** 2) if step else a

        # outer gold ring + dense ticks
        arc(R * 1.08, 0, 360, GOLD, 0.55, 1.2)
        arc(R * 1.13, rot(-6) % 360, 300, GOLD, 0.35, 0.8)
        for i in range(120):
            a = math.radians(i * 3 + rot(-6))
            long = i % 10 == 0
            L(pol(R * 1.08, a), pol(R * (1.13 if long else 1.105), a), "gold", 0.7 if long else 0.35, 1.0)
        # antenna spikes (stretch with voice / activity)
        stretch = 1.0 + 0.35 * self.level + 0.25 * self._burst
        tips: list[QPointF] = []
        for ang0, ln in self._spikes:
            a = ang0 + t * 0.03
            tip = R * (1.0 + (ln - 1.0) * stretch)
            L(pol(R * 1.15, a), pol(tip, a), "gold", 0.6, 0.9)
            tips.append(pol(tip, a))
        # gold data blocks band (like the yellow bars in the reference)
        for i in range(28):
            a0 = 200 + i * 2.6 + rot(-5)
            arc(R * 0.79, a0, 1.6, GOLD, 0.85, R * 0.045, bloom=False)
        for i in range(18):
            a0 = 20 + i * 3.0 + rot(-5)
            arc(R * 1.02, a0, 1.8, GOLD, 0.6, R * 0.025, bloom=False)
        # mid double ring with ticks
        arc(R * 0.92, 0, 360, col, 0.8, 2.2)
        arc(R * 0.86, 0, 360, col, 0.45, 1.0)
        for i in range(72):
            a = math.radians(i * 5 + rot(10))
            L(pol(R * 0.86, a), pol(R * (0.92 if i % 6 == 0 else 0.89), a), "col", 0.5, 1.0)
        # glowing segment bars (fill like progress while coding)
        fill = (t * 0.12) % 1.0 if step else 1.0
        for k, (start, span) in enumerate(self._bars):
            s = (start + rot(14 if k % 2 else -9)) % 360
            flick = 0.6 + 0.4 * math.sin(t * (7 if self.mode == "thinking" else 2) + k)
            arc(R * 0.975, s, span * fill, col, 0.75 * flick, R * 0.05)
        # gold inner accent ring + triangle markers
        arc(R * 0.72, rot(-18) % 360, 250, GOLD, 0.55, 1.1)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(4):
            a = math.radians(k * 90 + rot(8))
            tip, base = pol(R * 0.80, a), R * 0.88
            l1, l2 = pol(base, a - 0.05), pol(base, a + 0.05)
            p.setBrush(QBrush(self._a(col, 0.8 * glow)))
            p.drawPolygon([tip, l1, l2])
        # inner circuit ring: segmented arcs, fast when thinking
        fast = {"thinking": 3.0, "coding": 1.5}.get(self.mode, 1.0)
        for k in range(6):
            arc(R * 0.58, (k * 60 + rot(35 * fast)) % 360, 38, col, 0.75, 2.4)
            arc(R * 0.48, (k * 60 + 30 - rot(50 * fast)) % 360, 22, col, 0.55, 1.4)
        arc(R * 0.40, rot(-70 * fast) % 360, 200, GOLD, 0.6, 1.0)
        # radar sweep while coding
        if step:
            sweep = math.radians((t * 90) % 360)
            for j in range(10):
                L(QPointF(cx, cy), pol(R * 0.9, sweep - j * 0.03), "col", 0.5 * (1 - j / 10), 1.2)
        # radial spokes
        for k in range(8):
            a = math.radians(k * 45 + rot(4))
            L(pol(R * 0.24, a), pol(R * 0.84, a), "col", 0.18, 0.8)
        # voice waveform ring
        if self.mode in ("speaking", "listening"):
            pts = []
            for i in range(73):
                a = i / 72 * math.tau
                amp = self.level * (0.5 + 0.5 * math.sin(a * 6 + bt * 9)) * R * 0.08
                pts.append(pol(R * 0.66 + amp, a))
            for i in range(72):
                L(pts[i], pts[i + 1], "hot", 0.7, 1.3)
        # ripples
        for r, _d, st in self._ripples:
            arc(R * r, 0, 360, col, 0.5 * st, 1.6)
        # glowing dots on the antenna tips
        dot = QPen(self._a(GOLD, 0.9 * glow), 3.2)
        dot.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(dot)
        p.drawPoints(tips)
        # data sparks
        p.setPen(Qt.PenStyle.NoPen)
        for ang, rf, _sp, life in self._sparks:
            q = pol(R * rf, ang + t * 0.05)
            p.setBrush(QBrush(self._a(QColor("#FFFFFF") if life > 0.7 else col, life * 0.9)))
            p.drawEllipse(q, 1.6 + 1.2 * life, 1.6 + 1.2 * life)
        for (which, lv, width), segs in lines.items():
            c = GOLD if which == "gold" else (QColor("#E9FFFD") if which == "hot" else col)
            p.setPen(QPen(self._a(c, lv), width))
            p.drawLines(segs)
        # core: concentric fine rings, crosshair, bright centre
        for k, rr in enumerate((0.30, 0.22, 0.15)):
            arc(R * rr * (1 + 0.04 * self._burst), 0, 360, col, 0.6 - k * 0.1, 1.0)
        p.setPen(QPen(self._a(col, 0.5 * glow), 0.8))
        p.drawLine(pol(R * 0.08, 0), pol(R * 0.32, 0))
        p.drawLine(pol(R * 0.08, math.pi), pol(R * 0.32, math.pi))
        p.drawLine(pol(R * 0.08, math.pi / 2), pol(R * 0.32, math.pi / 2))
        p.drawLine(pol(R * 0.08, -math.pi / 2), pol(R * 0.32, -math.pi / 2))
        core_r = R * (0.10 + 0.04 * self.level + 0.03 * self._burst + (0.01 * breath if self.mode == "idle" else 0))
        g = QRadialGradient(QPointF(cx, cy), core_r * 2.2)
        g.setColorAt(0.0, self._a(QColor("#FFFFFF"), 0.95 * min(1.0, glow + 0.2)))
        g.setColorAt(0.3, self._a(col, 0.9 * glow))
        g.setColorAt(1.0, self._a(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), core_r * 2.2, core_r * 2.2)
        # entrance/exit: scan lines + chromatic glitch slices
        if boot < 1.0:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for _ in range(int(3 + 9 * (1 - boot))):
                y = self._rng.uniform(cy - R * 1.2, cy + R * 1.2)
                x0 = self._rng.uniform(cx - R * 1.3, cx)
                length = self._rng.uniform(R * 0.3, R * 1.4)
                tint = QColor("#FF2E88") if self._rng.random() < 0.35 else col
                p.setPen(QPen(self._a(tint, 0.55 * (1 - boot)), self._rng.choice((1.0, 2.0, 3.0))))
                p.drawLine(QPointF(x0, y), QPointF(x0 + length, y))
            sweep_y = cy - R * 1.3 + (R * 2.6) * boot                 # bright scan bar sweeping down
            p.setPen(QPen(self._a(col, 0.8 * (1 - boot) + 0.2), 1.5))
            p.drawLine(QPointF(cx - R * 1.3, sweep_y), QPointF(cx + R * 1.3, sweep_y))
        p.end()
