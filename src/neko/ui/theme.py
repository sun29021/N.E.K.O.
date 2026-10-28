"""Design tokens and stylesheet (docs/UI_UX_SPEC.md section 3).

Two original themes:
* **aurum** (default): a golden holographic look - warm black surfaces, molten-gold accent,
  white-hot highlights. Approval uses ice-blue so it can never be mistaken for normal activity.
* **nebula**: deep-space indigo with a cyan 'synapse' accent and violet secondary.
Rose is reserved for errors and amber/ice for warnings and approvals, so colour always carries
meaning. Fonts are Windows built-ins. Call ``set_theme`` before building any window.
"""

from __future__ import annotations

from ..core.types import AssistantState

_PALETTES = {
    "aurum": {
        "bg": "#0A0805", "surface": "#14100A", "surface_hi": "#1F180D", "border": "#4A3613",
        "text": "#F6EEDD", "text_dim": "#B3A07A", "accent": "#FFB224", "accent_2": "#FF7A1A",
        "ok": "#8FE388", "warn": "#7FD4FF", "error": "#FF5C6C", "focus": "#FFFFFF",
    },
    "nebula": {
        "bg": "#0B0E1A", "surface": "#121729", "surface_hi": "#1A2140", "border": "#2A3360",
        "text": "#E6EAF7", "text_dim": "#8C95B8", "accent": "#4DE3D8", "accent_2": "#9C7BFF",
        "ok": "#5BE38C", "warn": "#FFB547", "error": "#FF5C7A", "focus": "#FFFFFF",
    },
}

# (primary, secondary, hot) per state
_STATE_PALETTES: dict[str, dict[AssistantState, tuple[str, str, str]]] = {
    "aurum": {
        AssistantState.IDLE: ("#FFAA2B", "#B35A08", "#FFE6A8"),
        AssistantState.LISTENING: ("#FFC64D", "#D9780F", "#FFF6DA"),
        AssistantState.TRANSCRIBING: ("#FFD36B", "#C46A0C", "#FFF3CF"),
        AssistantState.THINKING: ("#FF9A1F", "#C2410C", "#FFE08A"),
        AssistantState.TOOL: ("#FFB84A", "#A8530A", "#FFE9B8"),
        AssistantState.AWAITING_APPROVAL: ("#7FD4FF", "#1F6FA8", "#E6F7FF"),
        AssistantState.SPEAKING: ("#FFB224", "#E0620C", "#FFF1C9"),
        AssistantState.RECOVERING: ("#E8C77A", "#7A5A1C", "#FFF0CC"),
        AssistantState.ERROR: ("#FF5C6C", "#7A1F2B", "#FFC2C8"),
        AssistantState.OFFLINE: ("#6E6350", "#2E281D", "#9A8F7A"),
    },
    "nebula": {
        AssistantState.IDLE: ("#4DE3D8", "#2B6F8F", "#E0FFFC"),
        AssistantState.LISTENING: ("#5BE38C", "#1E7A55", "#E5FFEE"),
        AssistantState.TRANSCRIBING: ("#7FE7FF", "#2D5C99", "#E8FBFF"),
        AssistantState.THINKING: ("#9C7BFF", "#4B2FA8", "#EDE6FF"),
        AssistantState.TOOL: ("#6FA8FF", "#29489E", "#E3EEFF"),
        AssistantState.AWAITING_APPROVAL: ("#FFB547", "#8A5A12", "#FFF0D6"),
        AssistantState.SPEAKING: ("#4DE3D8", "#7A4BFF", "#E0FFFC"),
        AssistantState.RECOVERING: ("#FFD27A", "#6B5220", "#FFF3D6"),
        AssistantState.ERROR: ("#FF5C7A", "#7A1F33", "#FFC7D2"),
        AssistantState.OFFLINE: ("#5A6283", "#2A2F45", "#8D94B0"),
    },
}

THEME = "aurum"
COLORS: dict[str, str] = dict(_PALETTES[THEME])
STATE_COLORS: dict[AssistantState, tuple[str, str, str]] = dict(_STATE_PALETTES[THEME])


def state_colors(state: AssistantState) -> tuple[str, str, str]:
    return STATE_COLORS[state]


def set_theme(name: str) -> str:
    """Switch palettes in place (modules hold references to COLORS) and return the QSS."""
    global THEME, QSS
    THEME = name if name in _PALETTES else "aurum"
    COLORS.clear()
    COLORS.update(_PALETTES[THEME])
    STATE_COLORS.clear()
    STATE_COLORS.update(_STATE_PALETTES[THEME])
    QSS = build_qss()
    return QSS

STATE_LABELS: dict[AssistantState, str] = {
    AssistantState.IDLE: "Ready",
    AssistantState.LISTENING: "Listening...",
    AssistantState.TRANSCRIBING: "Transcribing...",
    AssistantState.THINKING: "Thinking...",
    AssistantState.TOOL: "Using a tool...",
    AssistantState.AWAITING_APPROVAL: "Waiting for your approval",
    AssistantState.SPEAKING: "Speaking",
    AssistantState.RECOVERING: "Recovering...",
    AssistantState.ERROR: "Something went wrong",
    AssistantState.OFFLINE: "Model server offline",
}

FONT_UI = "Segoe UI Variable Text, Segoe UI, sans-serif"
FONT_MONO = "Cascadia Mono, Consolas, monospace"

# spacing scale (px): 4 8 12 16 24 32 ; radii: 8 (controls) 14 (panels) 999 (pills)
def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def build_qss() -> str:
    return f"""
* {{ font-family: {FONT_UI}; font-size: 10pt; color: {COLORS['text']}; }}
QMainWindow, QDialog, QWidget#Surface {{ background: {COLORS['bg']}; }}
QFrame#Panel {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 14px; }}
QLabel#Dim {{ color: {COLORS['text_dim']}; }}
QLabel#Title {{ font-size: 13pt; font-weight: 600; letter-spacing: 2px; }}
QLabel#Pill {{ background: {COLORS['surface_hi']}; border: 1px solid {COLORS['border']}; border-radius: 9px;
               padding: 2px 8px; color: {COLORS['text_dim']}; font-size: 8.5pt; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {COLORS['surface_hi']}; border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {COLORS['accent_2']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 1px solid {COLORS['accent']}; }}
QPushButton {{ background: {COLORS['surface_hi']}; border: 1px solid {COLORS['border']}; border-radius: 8px;
               padding: 6px 12px; }}
QPushButton:hover {{ border-color: {COLORS['accent']}; }}
QPushButton:focus {{ border: 2px solid {COLORS['focus']}; }}
QPushButton:pressed {{ background: {COLORS['border']}; }}
QPushButton#Primary {{ background: {COLORS['accent']}; color: #1A1003; font-weight: 600; border: none; }}
QPushButton#Danger {{ background: {COLORS['error']}; color: #2A0610; font-weight: 700; border: none; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {COLORS['text_dim']}; }}
QPushButton#Ghost:hover {{ color: {COLORS['text']}; }}
QTabWidget::pane {{ border: 1px solid {COLORS['border']}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {COLORS['text_dim']}; }}
QTabBar::tab:selected {{ color: {COLORS['text']}; border-bottom: 2px solid {COLORS['accent']}; }}
QTableWidget, QListWidget, QTreeWidget {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']};
    border-radius: 8px; gridline-color: {COLORS['border']}; alternate-background-color: {COLORS['surface_hi']}; }}
QHeaderView::section {{ background: {COLORS['surface_hi']}; border: none; padding: 6px; color: {COLORS['text_dim']}; }}
QProgressBar {{ background: {COLORS['surface_hi']}; border: none; border-radius: 4px; height: 8px; text-align: center;
               color: {COLORS['text']}; font-weight: 600; }}
QProgressBar::chunk {{ background: {_rgba(COLORS['accent'], 0.45)}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {COLORS['border']}; border-radius: 5px; min-height: 30px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QToolTip {{ background: {COLORS['surface_hi']}; color: {COLORS['text']}; border: 1px solid {COLORS['border']}; }}
"""


QSS = build_qss()

# Motion (ms). Reduced-motion mode disables continuous animation entirely.
MOTION = {"frame_ms": 33, "state_fade_ms": 220, "expand_ms": 180}
