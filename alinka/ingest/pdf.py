"""PDF sanitizer: page renders, the visible-text index and hidden-content flags.

Every text span comes from `Page.get_texttrace()`. A span is dropped from the visible
text, and flagged, when a person could not see it: opacity 0, render mode 3, an
optional-content layer, a colour within 5% of the background behind it, a size under
2 pt, a box outside the CropBox, or a render test showing only one colour where the
text should be (something is painted over it). Annotations, form fields, embedded
files, a CropBox that differs from the MediaBox and instruction-like metadata are
flagged too. The model only ever sees the renders and the kept text.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

import pymupdf
from PIL import Image

from alinka.ingest.base import Ingested, PageData, TextSpan, clip, find_instructions
from alinka.types import Box, Channel

DPI = 150
SCALE = DPI / 72
MIN_SIZE_PT = 2.0
MIN_OPACITY = 0.05
BACKGROUND_DELTA = 0.05  # text colour this close to the background is invisible
FLAT_RANGE = 12  # a crop whose channels vary less than this (of 255) is one colour
CROP_TOLERANCE_PT = 1.0
METADATA_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")


@dataclass
class _Span:
    text: str
    rect: pymupdf.Rect
    size: float
    color: tuple[float, float, float]
    opacity: float
    kind: int  # 0 fill, 1 stroke, 3 invisible
    layer: str | None
    char_keys: tuple[tuple[int, int, int], ...]


def ingest_pdf(data: bytes) -> Ingested:
    """Sanitize one PDF given as bytes. Never raises on odd content; bad files raise."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    out = Ingested(channel=Channel.PDF, doc_sha256=hashlib.sha256(data).hexdigest())
    # Text on a switched-off layer never reaches the trace, so trace a copy with every layer on.
    traced = pymupdf.open(stream=data, filetype="pdf") if doc.get_ocgs() else doc
    try:
        _check_document(doc, out)
        for config in traced.layer_ui_configs() if traced is not doc else ():
            traced.set_layer_ui_config(config["number"], 0)
        for page in doc:
            out.pages.append(_ingest_page(page, traced[page.number], out))
    finally:
        if traced is not doc:
            traced.close()
        doc.close()
    for page in out.pages:
        for snippet in find_instructions(page.text):
            out.instructions.append(f"p{page.number}: {snippet}")
    return out


def _check_document(doc: pymupdf.Document, out: Ingested) -> None:
    meta = doc.metadata or {}
    for key in METADATA_KEYS:
        for snippet in find_instructions(meta.get(key) or ""):
            out.instructions.append(f"metadata {key}: {snippet}")
    for snippet in find_instructions(doc.get_xml_metadata() or ""):
        out.instructions.append(f"XMP metadata: {snippet}")
    if doc.embfile_count():
        out.hidden_content.append(f"embedded files: {doc.embfile_count()}")


def _ingest_page(page: pymupdf.Page, traced: pymupdf.Page, out: Ingested) -> PageData:
    n = page.number + 1
    rect = page.rect
    pix = page.get_pixmap(dpi=DPI, alpha=False)
    png = pix.tobytes("png")
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    if _differs(page.cropbox, page.mediabox):
        out.hidden_content.append(f"p{n}: CropBox differs from MediaBox")
    for annot in page.annots():
        info = annot.info or {}
        text = info.get("content") or info.get("title") or ""
        out.hidden_content.append(f"p{n}: annotation ({annot.type[1]}): '{clip(text)}'")
        for snippet in find_instructions(text):
            out.instructions.append(f"p{n} annotation: {snippet}")
    for widget in page.widgets():
        value = str(widget.field_value or "")
        out.hidden_content.append(f"p{n}: form field '{widget.field_name}': '{clip(value)}'")

    by_reason: dict[str, list[str]] = defaultdict(list)
    hidden: list[_Span] = []
    kept: list[_Span] = []
    for span in _spans(traced):
        reason = _hidden_reason(span, rect, image)
        if reason:
            by_reason[reason].append(span.text)
            hidden.append(span)
        else:
            kept.append(span)
    for reason, texts in by_reason.items():
        out.hidden_content.append(f"p{n}: {reason}: '{clip(' '.join(texts))}'")

    spans = [TextSpan(text=s.text, box=_norm(s.rect, rect, n)) for s in kept]
    return PageData(
        number=n,
        width=rect.width,
        height=rect.height,
        png=png,
        spans=spans,
        text=_visible_text(page, hidden),
    )


def _spans(page: pymupdf.Page) -> list[_Span]:
    seen: set[tuple[str, int, int, int, int]] = set()
    spans: list[_Span] = []
    for raw in page.get_texttrace():
        text = "".join(chr(c[0]) for c in raw["chars"] if c[0] > 0)
        if not text.strip():
            continue
        r = pymupdf.Rect(raw["bbox"])
        key = (text, *(round(v) for v in r))
        if key in seen:  # fill and stroke copies of the same glyphs (2 Tr)
            continue
        seen.add(key)
        color = tuple(raw.get("color") or (0.0,))
        if len(color) == 1:
            color = (color[0], color[0], color[0])
        spans.append(
            _Span(
                text=text,
                rect=r,
                size=float(raw.get("size") or 0.0),
                color=color[:3],  # type: ignore[arg-type]
                opacity=float(raw.get("opacity", 1.0)),
                kind=int(raw.get("type", 0)),
                layer=raw.get("layer") or None,
                char_keys=tuple(_char_key(c[0], c[2]) for c in raw["chars"]),
            )
        )
    return spans


def _hidden_reason(span: _Span, page_rect: pymupdf.Rect, image: Image.Image) -> str | None:
    if span.opacity <= MIN_OPACITY:
        return "span with opacity 0"
    if span.kind == 3:
        return "span in render mode 3 (invisible)"
    if span.layer:
        return f"span on optional-content layer '{span.layer}'"
    if span.size < MIN_SIZE_PT or span.rect.height < MIN_SIZE_PT:
        return "span under 2 pt"
    inside = span.rect & page_rect
    if inside.is_empty or inside.get_area() < 0.5 * span.rect.get_area():
        return "span outside the CropBox"
    crop = _crop(image, inside)
    if crop is None:
        return None
    background = _background(image, inside)
    if (
        max(abs(c - b / 255) for c, b in zip(span.color, background, strict=True))
        <= BACKGROUND_DELTA
    ):
        return "span coloured like the background"
    if all(hi - lo < FLAT_RANGE for lo, hi in crop.getextrema()):
        return "span covered by another object"
    return None


def _crop(image: Image.Image, r: pymupdf.Rect) -> Image.Image | None:
    box = (int(r.x0 * SCALE), int(r.y0 * SCALE), int(r.x1 * SCALE) + 1, int(r.y1 * SCALE) + 1)
    box = (max(box[0], 0), max(box[1], 0), min(box[2], image.width), min(box[3], image.height))
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return None
    return image.crop(box)


def _background(image: Image.Image, r: pymupdf.Rect) -> tuple[int, int, int]:
    """The most common colour around and under the span."""
    crop = _crop(image, pymupdf.Rect(r.x0 - 3, r.y0 - 3, r.x1 + 3, r.y1 + 3)) or image
    colors = crop.getcolors(maxcolors=crop.width * crop.height) or [(1, (255, 255, 255))]
    return max(colors)[1]


def _differs(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
    return any(abs(x - y) > CROP_TOLERANCE_PT for x, y in zip(a, b, strict=True))


def _norm(r: pymupdf.Rect, page: pymupdf.Rect, n: int) -> Box:
    def f(v: float, size: float) -> float:
        return round(min(max(v / size, 0.0), 1.0), 4)

    return Box(
        page=n,
        x0=f(r.x0, page.width),
        y0=f(r.y0, page.height),
        x1=f(r.x1, page.width),
        y1=f(r.y1, page.height),
    )


def _visible_text(page: pymupdf.Page, hidden: list[_Span]) -> str:
    """MuPDF's own lines and reading order, minus every character of a hidden span."""
    drop = {key for span in hidden for key in span.char_keys}
    blocks: list[str] = []
    for block in page.get_text("rawdict").get("blocks", []):
        lines: list[str] = []
        for line in block.get("lines", []):
            chars = [
                ch["c"]
                for span in line["spans"]
                for ch in span["chars"]
                if ch.get("synthetic") or _char_key(ord(ch["c"]), ch["origin"]) not in drop
            ]
            text = " ".join("".join(chars).split())
            if text:
                lines.append(text)
        if lines:
            blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _char_key(code: int, origin: tuple[float, float]) -> tuple[int, int, int]:
    return (code, round(origin[0] * 10), round(origin[1] * 10))
