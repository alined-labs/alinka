"""Grounding: a quote counts only if code finds it in the visible text, with its boxes."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import pymupdf

from alinka.ingest.base import Ingested, PageData
from alinka.types import Box, Field

OCR_MATCH_MIN = 0.85
_SPACE = re.compile(r"\s+")
_DASHES = str.maketrans(
    {"–": "-", "—": "-", "‐": "-", "‑": "-", "’": "'", "‘": "'", "“": '"', "”": '"'}
)


def norm(text: str) -> str:
    """Compare text loosely on form, never on content: NFKC, dashes, quotes, spaces, case."""
    s = unicodedata.normalize("NFKC", text).translate(_DASHES)
    return _SPACE.sub(" ", s).strip().casefold()


def _squash(text: str) -> str:
    return _SPACE.sub("", norm(text))


def ground(field: Field, doc: Ingested, pdfs: dict[int, pymupdf.Document]) -> Field:
    """Set `grounded` and `boxes`. The quote must be in the visible text and hold the value."""
    if field.value is None:
        return field
    quote = field.quote or ""
    if not quote.strip() or not _contains(quote, field.value):
        return field.model_copy(update={"grounded": False, "boxes": ()})
    pages = [p for p in doc.pages if _contains(p.text, quote)]
    if not pages:  # OCR misreads a character here and there: the value itself must still match
        pages = [
            p
            for p in doc.pages
            if p.ocr_confidence is not None and _ocr_match(p, quote, field.value)
        ]
    if not pages:
        return field.model_copy(update={"grounded": False, "boxes": ()})
    boxes: list[Box] = []
    for page in pages:
        boxes.extend(_boxes(page, quote, pdfs))
    return field.model_copy(update={"grounded": True, "boxes": tuple(boxes[:8])})


def _contains(haystack: str, needle: str) -> bool:
    # Line breaks in the text index split what a person reads as one run, so ignore spacing.
    return _squash(needle) in _squash(haystack)


def _ocr_match(page: PageData, quote: str, value: str) -> bool:
    text, want = _squash(page.text), _squash(quote)
    if _squash(value) not in text or not want:
        return False
    best = 0.0
    step = max(len(want) // 4, 1)
    for start in range(0, max(len(text) - len(want), 0) + 1, step):
        window = text[start : start + len(want) + 4]
        best = max(best, SequenceMatcher(None, want, window).ratio())
    return best >= OCR_MATCH_MIN


def _boxes(page: PageData, quote: str, pdfs: dict[int, pymupdf.Document]) -> list[Box]:
    if page.source_pdf is not None:
        key = id(page.source_pdf)
        if key not in pdfs:
            pdfs[key] = pymupdf.open(stream=page.source_pdf, filetype="pdf")
        pdf_page = pdfs[key][page.source_page]
        rect = pdf_page.rect
        hits = pdf_page.search_for(quote) or _line_hits(pdf_page, quote)
        return [
            Box(
                page=page.number,
                x0=round(max(r.x0 / rect.width, 0), 4),
                y0=round(max(r.y0 / rect.height, 0), 4),
                x1=round(min(r.x1 / rect.width, 1), 4),
                y1=round(min(r.y1 / rect.height, 1), 4),
            )
            for r in hits
        ]
    return _ocr_boxes(page, quote)


def _line_hits(pdf_page: pymupdf.Page, quote: str) -> list[pymupdf.Rect]:
    """A quote that wraps across lines: search each of its lines' longest pieces."""
    hits: list[pymupdf.Rect] = []
    for piece in quote.splitlines() or [quote]:
        piece = piece.strip()
        if len(piece) >= 3:
            hits.extend(pdf_page.search_for(piece))
    return hits


def _ocr_boxes(page: PageData, quote: str) -> list[Box]:
    """Find the quote as a run of OCR words and return one box per line it spans."""
    want = [_squash(w) for w in quote.split() if _squash(w)]
    words = [(_squash(s.text), s.box) for s in page.spans]
    if not want:
        return []
    for start in range(len(words)):
        if not words[start][0].endswith(want[0]) and words[start][0] != want[0]:
            continue
        run = words[start : start + len(want)]
        if len(run) == len(want) and all(
            w == q or (i in (0, len(want) - 1) and q in w)
            for i, ((w, _), q) in enumerate(zip(run, want, strict=True))
        ):
            return _merge_lines([box for _, box in run])
    if len(want) == 1:  # a value inside a longer OCR token
        return _merge_lines([box for w, box in words if want[0] in w][:1])
    return []


def _merge_lines(boxes: list[Box]) -> list[Box]:
    lines: list[list[Box]] = []
    for box in boxes:
        if lines and abs(lines[-1][-1].y0 - box.y0) < (box.y1 - box.y0) * 0.6:
            lines[-1].append(box)
        else:
            lines.append([box])
    return [
        Box(
            page=line[0].page,
            x0=min(b.x0 for b in line),
            y0=min(b.y0 for b in line),
            x1=max(b.x1 for b in line),
            y1=max(b.y1 for b in line),
        )
        for line in lines
    ]
