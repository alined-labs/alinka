"""Pick the sanitizer for a document by its file type."""

from __future__ import annotations

from pathlib import Path

from alinka.ingest.base import Ingested
from alinka.ingest.image import ingest_image
from alinka.ingest.pdf import ingest_pdf
from alinka.ingest.text import ingest_chat, ingest_email

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def ingest_bytes(data: bytes, suffix: str) -> Ingested:
    suffix = suffix.lower()
    if suffix == ".pdf" or data.startswith(b"%PDF"):
        return ingest_pdf(data)
    if suffix == ".eml":
        return ingest_email(data)
    if suffix in IMAGE_SUFFIXES:
        return ingest_image(data)
    if suffix in {".txt", ".chat"}:
        return ingest_chat(data)
    raise ValueError(f"unsupported document type {suffix!r}")


def ingest_path(path: str | Path) -> Ingested:
    path = Path(path)
    return ingest_bytes(path.read_bytes(), path.suffix)


def render_pages(path: str | Path) -> list[bytes]:
    """The page images the reader saw and `Field.boxes` refer to: PDF pages at 150 dpi,
    the photo itself, or the code-rendered text of an email or chat."""
    path = Path(path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        import io

        from PIL import Image, ImageOps

        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return [buffer.getvalue()]
    return [page.png for page in ingest_path(path).pages if page.png]
