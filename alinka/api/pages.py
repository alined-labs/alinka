"""Page images rendered at request time from the source documents with PyMuPDF."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DPI = 110
RASTER = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def _open(path: str | None) -> pymupdf.Document | None:
    """Open a repo-relative PDF or image; None when it is missing or not renderable here."""
    if not path:
        return None
    file = (ROOT / path).resolve()
    if ROOT not in file.parents or not file.is_file():
        return None
    if file.suffix.lower() not in RASTER | {".pdf"}:
        return None
    return pymupdf.open(file)


def _placeholder(label: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 in points
    page.insert_text((72, 96), label, fontsize=14)
    page.insert_text((72, 120), "Vista previa no disponible (fixture).", fontsize=11)
    png = page.get_pixmap(dpi=DPI).tobytes("png")
    doc.close()
    return png


@lru_cache(maxsize=256)
def render_page(path: str | None, n: int, label: str) -> bytes | None:
    """PNG bytes of page n (1-based), a placeholder when the source can't be rendered,
    or None when n is out of range for a document that exists."""
    doc = _open(path)
    if doc is None:
        return _placeholder(f"{label} · página {n}") if n == 1 else None
    try:
        if not 1 <= n <= doc.page_count:
            return None
        return doc[n - 1].get_pixmap(dpi=DPI).tobytes("png")
    finally:
        doc.close()


@lru_cache(maxsize=256)
def page_sizes(path: str | None) -> tuple[tuple[int, int], ...]:
    """Pixel width and height of every page at DPI; one A4 page for the placeholder."""
    doc = _open(path)
    if doc is None:
        return ((round(595 * DPI / 72), round(842 * DPI / 72)),)
    try:
        return tuple((round(p.rect.width * DPI / 72), round(p.rect.height * DPI / 72)) for p in doc)
    finally:
        doc.close()
