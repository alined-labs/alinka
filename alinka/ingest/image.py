"""Image sanitizer: Tesseract (spa+eng) builds the visible-text index with word boxes.

OCR output is recorded in the response cache like a model call. The model sees the photo itself (re-encoded as PNG, at most 1568 px on the long edge)
and the OCR text; grounding and boxes come from the OCR words. Text in EXIF or PNG
metadata that reads like an instruction is flagged.
"""

from __future__ import annotations

import hashlib
import io
import shutil
from collections import defaultdict

import pytesseract
from PIL import Image, ImageOps

from alinka.cache import CacheMiss, Fresh, cache_key, get_cache, sha256_text
from alinka.ingest.base import Ingested, PageData, TextSpan, clip, find_instructions
from alinka.ingest.text import strip_controls
from alinka.types import Box, Channel

LANG = "spa+eng"
MAX_EDGE = 1568
OCR_TIMEOUT_S = 60
OCR_MODEL = f"tesseract-{LANG}"
OCR_FIELDS = ("text", "conf", "left", "top", "width", "height", "block_num", "par_num", "line_num")
EXIF_TEXT_TAGS = (0x010E, 0x013B, 0x9286, 0x9C9C, 0x9C9F)  # description, artist, comment, XP*


def ingest_image(data: bytes) -> Ingested:
    out = Ingested(channel=Channel.IMAGE, doc_sha256=hashlib.sha256(data).hexdigest())
    image = Image.open(io.BytesIO(data))
    _check_metadata(image, out)
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size

    ocr = _ocr(image, out.doc_sha256)
    lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    spans: list[TextSpan] = []
    confidences: list[float] = []
    for i, word in enumerate(ocr["text"]):
        word = (word or "").strip()
        conf = float(ocr["conf"][i])
        if not word or conf < 0:
            continue
        x, y, w, h = ocr["left"][i], ocr["top"][i], ocr["width"][i], ocr["height"][i]
        spans.append(
            TextSpan(
                text=word,
                box=Box(
                    page=1,
                    x0=round(x / width, 4),
                    y0=round(y / height, 4),
                    x1=round((x + w) / width, 4),
                    y1=round((y + h) / height, 4),
                ),
            )
        )
        confidences.append(conf)
        lines[(ocr["block_num"][i], ocr["par_num"][i], ocr["line_num"][i])].append(word)
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    text, controls = strip_controls(text)
    out.unicode_controls.extend(controls)
    for snippet in find_instructions(text):
        out.instructions.append(f"p1: {snippet}")

    preview = image.copy()
    preview.thumbnail((MAX_EDGE, MAX_EDGE))
    buffer = io.BytesIO()
    preview.save(buffer, format="PNG", optimize=True)
    out.pages.append(
        PageData(
            number=1,
            width=float(width),
            height=float(height),
            png=buffer.getvalue(),
            spans=spans,
            text=text,
            ocr_confidence=round(sum(confidences) / len(confidences), 1) if confidences else 0.0,
        )
    )
    return out


def _ocr(image: Image.Image, image_sha256: str) -> dict[str, list]:
    """Tesseract word data, through the response cache so replay needs no Tesseract and
    every machine sees the same text. Without a recording, OCR runs locally if it can."""
    cache = get_cache()
    prompt_hash = sha256_text(f"image_to_data lang={LANG} {OCR_FIELDS}")
    key = cache_key(OCR_MODEL, prompt_hash, image_sha256)
    hit = cache.get(key)
    if hit is not None:
        return hit.response
    if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None:
        raise CacheMiss(f"no OCR recording for {image_sha256[:12]} and no Tesseract here")

    def run() -> Fresh:
        data = pytesseract.image_to_data(
            image, lang=LANG, output_type=pytesseract.Output.DICT, timeout=OCR_TIMEOUT_S
        )
        return Fresh(response={k: list(data[k]) for k in OCR_FIELDS}, stop_reason="end_turn")

    if cache.mode == "replay":
        return run().response
    request = {"role": "ocr", "lang": LANG, "image_sha256": image_sha256}
    return cache.call(
        model=OCR_MODEL, prompt_hash=prompt_hash, input_hash=image_sha256, request=request, fn=run
    ).response


def _check_metadata(image: Image.Image, out: Ingested) -> None:
    texts: list[tuple[str, str]] = []
    for key, value in (image.info or {}).items():
        if isinstance(value, str):
            texts.append((str(key), value))
    exif = image.getexif()
    for tag in EXIF_TEXT_TAGS:
        value = exif.get(tag)
        if isinstance(value, bytes):
            value = value.decode("utf-16-le" if tag >= 0x9C9B else "utf-8", errors="ignore")
        if isinstance(value, str):
            texts.append((f"EXIF 0x{tag:04X}", value))
    for key, value in texts:
        for snippet in find_instructions(value):
            out.instructions.append(f"image metadata {key}: {clip(snippet)}")
