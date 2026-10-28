"""User-initiated screen capture.

Only called from the HUD's capture button. The HUD hides itself first so it
is not in the picture, captures the screen under the cursor, shows itself
again with a brief 'captured' flash, and returns PNG bytes kept in memory.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QCursor, QGuiApplication


def capture_screen_under_cursor() -> bytes | None:
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    pix = screen.grabWindow(0)
    if pix.isNull():
        return None
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(ba.data())
