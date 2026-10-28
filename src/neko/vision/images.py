"""Image preparation for vision models.

Screenshots are captured only when the user presses the capture button (the
UI uses Qt's ``QScreen.grabWindow``; see ui/capture.py). Images stay in memory,
go only to the local vision model chosen by the router, and are not written
to disk unless ``vision.retain_screenshots`` is on.

Large screens are downscaled so the longest side is ``max_side`` (default
1344 px); text-heavy captures can instead be tiled so small text stays
legible. Qt is used when available; otherwise images are passed through.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PreparedImage:
    data: bytes          # PNG bytes
    width: int
    height: int
    scaled: bool
    tiles: int = 1


def prepare_png(png: bytes, max_side: int = 1344) -> PreparedImage:
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PySide6.QtGui import QImage
    except ImportError:
        return PreparedImage(png, 0, 0, False)
    img = QImage.fromData(png)
    if img.isNull():
        return PreparedImage(png, 0, 0, False)
    w, h = img.width(), img.height()
    if max(w, h) <= max_side:
        return PreparedImage(png, w, h, False)
    scaled = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    scaled.save(buf, "PNG")
    return PreparedImage(bytes(ba.data()), scaled.width(), scaled.height(), True)


def tile_boxes(width: int, height: int, tile: int = 1024, overlap: int = 64) -> list[tuple[int, int, int, int]]:
    """Return (x, y, w, h) boxes covering the image with overlap, for OCR-style
    analysis of dense screens. Pure function so it is unit-testable."""
    boxes = []
    step = tile - overlap
    for y in range(0, max(1, height - overlap), step):
        for x in range(0, max(1, width - overlap), step):
            boxes.append((x, y, min(tile, width - x), min(tile, height - y)))
    return boxes
