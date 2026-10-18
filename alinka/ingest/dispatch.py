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
