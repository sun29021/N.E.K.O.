"""Markdown -> clean, printable PDF (study notes, cheat sheets) using Qt's text engine.

Installed as ``neko.documents.pdf_renderer`` by the UI bridge. Runs on the request thread:
QTextDocument and QPdfWriter don't need the GUI thread. Markdown only, no HTML/remote resources.
"""

from __future__ import annotations

import html
import time
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1d2330; }
h1 { color: #0E7C74; font-size: 20pt; margin-bottom: 4pt; }
h2 { color: #0E7C74; font-size: 14pt; margin-top: 12pt; margin-bottom: 4pt;
     border-bottom: 1px solid #9FD9D3; }
h3 { color: #8A5A00; font-size: 12pt; margin-top: 8pt; }
p, li { font-size: 10.5pt; line-height: 135%; }
strong { color: #8A5A00; }
code { font-family: Consolas, monospace; background: #F1F4F7; }
table { border-collapse: collapse; margin: 6pt 0; }
th { background: #E3F5F3; color: #0E7C74; padding: 3pt 6pt; border: 1px solid #B9DDD9; }
td { padding: 3pt 6pt; border: 1px solid #D5DCE3; font-size: 10pt; }
blockquote { color: #4a5568; margin-left: 10pt; }
.meta { color: #8a94a6; font-size: 8.5pt; }
"""


def render_markdown_pdf(markdown: str, title: str, out: Path) -> None:
    doc = QTextDocument()
    doc.setDefaultStyleSheet(CSS)
    doc.setDefaultFont(QFont("Segoe UI", 10))
    body = QTextDocument()
    body.setMarkdown(markdown)
    # Title + date line, then the Markdown rendered by Qt (escaped title: it may come from a file name).
    header = (f"<h1>{html.escape(title)}</h1><p class='meta'>Made by Neko on "
              f"{time.strftime('%d %B %Y')} - check important facts against your original material.</p>")
    doc.setHtml(header + body.toHtml().split("<body", 1)[-1].split(">", 1)[-1].rsplit("</body>", 1)[0])
    writer = QPdfWriter(str(out))
    writer.setTitle(title)
    writer.setCreator("N.E.K.O.")
    writer.setResolution(96)  # match QTextDocument's logical DPI, or text prints at half size
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(16, 14, 16, 14), QPageLayout.Unit.Millimeter))
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)
