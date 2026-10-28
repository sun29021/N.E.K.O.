"""Build the three printable N.E.K.O. guides (A4 PDFs) with Qt's built-in web engine - offline, no browser.

    .venv\\Scripts\\python scripts\\guides\\make_guides.py            -> docs\\guides\\*.pdf
    .venv\\Scripts\\python scripts\\guides\\make_guides.py --preview  -> also PNG previews of every page (scratch)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs" / "guides"
sys.path.insert(0, str(HERE))

GUIDES = {
    "1 - Installing NEKO.pdf": "guide_install",
    "2 - NEKO user manual - Laptop (owner).pdf": "guide_laptop",
    "3 - NEKO user manual - Office PC.pdf": "guide_office",
}


def build(preview_dir: Path | None = None) -> list[Path]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF, QTimer, QUrl
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    # render every page first: a mistake in a guide stops here with a clear error instead of hanging Qt
    jobs = [(name, __import__(module).render()) for name, module in GUIDES.items()]
    done: list[Path] = []
    page = QWebEnginePage()
    layout = QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))

    def next_job() -> None:
        if not jobs:
            app.quit()
            return
        name, html_text = jobs.pop(0)
        target = OUT / name
        page.setProperty("target", str(target))
        page.setHtml(html_text, QUrl.fromLocalFile(str(HERE) + os.sep))

    def loaded(ok: bool) -> None:
        if not ok:
            print("page failed to load")
            app.quit()
            return
        QTimer.singleShot(300, lambda: page.printToPdf(page.property("target"), layout))

    def printed(path: str, ok: bool) -> None:
        print(("ok  " if ok else "FAIL") + f" {Path(path).name}")
        if ok:
            done.append(Path(path))
        next_job()

    page.loadFinished.connect(loaded)
    page.pdfPrintingFinished.connect(printed)
    QTimer.singleShot(0, next_job)
    QTimer.singleShot(180_000, app.quit)
    app.exec()
    if preview_dir is not None:
        previews(done, preview_dir)
    return done


def previews(pdfs: list[Path], folder: Path, width: int = 900) -> None:
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    folder.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        doc = QPdfDocument()
        doc.load(str(pdf))
        size = doc.pagePointSize(0)
        for i in range(doc.pageCount()):
            img = doc.render(i, QSize(width, int(width * size.height() / size.width())))
            img.save(str(folder / f"{pdf.stem[:1]}-p{i + 1:02d}.png"))
        print(f"{pdf.name}: {doc.pageCount()} pages")


if __name__ == "__main__":
    prev = Path(os.environ.get("TEMP", ".")) / "neko-guide-previews" if "--preview" in sys.argv else None
    build(prev)
