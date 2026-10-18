"""Page images rendered at request time from the source documents with PyMuPDF.

The pages are the ones the reader saw and `Field.boxes` refer to: a PDF's own pages, the
photo turned upright, or the code-rendered pages of an email or chat. ?scale=1|2|3
renders them at 150, 300 or 450 dpi; a photo has no dpi and is served at its own size
at every scale. Recent renders stay in memory.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pymupdf

from alinka.ingest.dispatch import IMAGE_SUFFIXES, ingest_path, render_pages

ROOT = Path(__file__).resolve().parents[2]
DPI = {1: 150, 2: 300, 3: 450}
TEXT_SUFFIXES = {".eml", ".txt"}

Page = tuple[bytes, str, int]  # document bytes, PyMuPDF file type, 0-based page


def _file(path: str | None) -> Path | None:
    """A repo-relative source document; None when it is missing or outside the repo."""
    if not path:
        return None
    file = (ROOT / path).resolve()
    if ROOT not in file.parents or not file.is_file():
        return None
    return file


@lru_cache(maxsize=32)
def _pages(path: str | None) -> tuple[Page, ...] | None:
    """Every page of the document as something PyMuPDF renders; None when it can't."""
    file = _file(path)
    if file is None:
        return None
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        data = file.read_bytes()
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return tuple((data, "pdf", i) for i in range(doc.page_count))
    if suffix in IMAGE_SUFFIXES:
        return tuple((png, "png", 0) for png in render_pages(file))
    if suffix in TEXT_SUFFIXES:
        return tuple(
            (p.source_pdf, "pdf", p.source_page) if p.source_pdf else (p.png, "png", 0)
            for p in ingest_path(file).pages
            if p.source_pdf or p.png
        )
    return None


def _placeholder(label: str, dpi: int) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 in points
    page.insert_text((72, 96), label, fontsize=14)
    page.insert_text((72, 120), "Vista previa no disponible (fixture).", fontsize=11)
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    doc.close()
    return png


@lru_cache(maxsize=64)
def render_page(path: str | None, n: int, label: str, scale: int = 1) -> bytes | None:
    """PNG bytes of page n (1-based) at the scale's dpi, a placeholder when the source
    can't be rendered, or None when n is out of range for a document that exists."""
    dpi = DPI[scale]
    pages = _pages(path)
    if pages is None:
        return _placeholder(f"{label} · página {n}", dpi) if n == 1 else None
    if not 1 <= n <= len(pages):
        return None
    data, filetype, index = pages[n - 1]
    if filetype == "png":  # a photo: more pixels would add no detail
        return data
    with pymupdf.open(stream=data, filetype=filetype) as doc:
        return doc[index].get_pixmap(dpi=dpi, alpha=False).tobytes("png")


@lru_cache(maxsize=256)
def page_sizes(path: str | None) -> tuple[tuple[int, int], ...]:
    """Pixel width and height of every page at scale 1; one A4 page for the placeholder."""
    k = DPI[1] / 72
    pages = _pages(path)
    if pages is None:
        return ((round(595 * k), round(842 * k)),)
    sizes = []
    for data, filetype, index in pages:
        if filetype == "png":
            image = pymupdf.Pixmap(data)
            sizes.append((image.width, image.height))
            continue
        with pymupdf.open(stream=data, filetype=filetype) as doc:
            rect = doc[index].rect
        sizes.append((round(rect.width * k), round(rect.height * k)))
    return tuple(sizes)
