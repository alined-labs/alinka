"""Shared helpers for every dataset builder: formats, fiscal IDs, rendering and channels.

Everything here is deterministic: the same spec gives the same bytes, so recorded model
responses (keyed by the document hash) stay valid when a builder runs again.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from pathlib import Path
from random import Random

import pymupdf
import segno
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from num2words import num2words
from PIL import Image, ImageFilter
from weasyprint import HTML

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data"
VERIFY = "https://verifica.alinka.invalid"
FICTIONAL_ES = "(empresa ficticia)"
FICTIONAL_EN = "(fictitious company)"

ENV = Environment(
    loader=FileSystemLoader(HERE / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# --- The world ----------------------------------------------------------------


def company() -> dict:
    return yaml.safe_load((DATA / "company.yaml").read_text())


def vendors() -> dict[str, dict]:
    raw = yaml.safe_load((DATA / "vendors.yaml").read_text())["beneficiaries"]
    return {b["id"]: b for b in raw}


# --- Formats ------------------------------------------------------------------

# Thousands and decimal separators by locale.
SEPARATORS = {
    "es-CO": (".", ","),
    "es-ES": (".", ","),
    "es-AR": (".", ","),
    "pt-BR": (".", ","),
    "es-MX": (",", "."),
    "en-US": (",", "."),
}


def money(minor: int, locale: str) -> str:
    """1.234.567,89 (es-CO, es-ES, es-AR, pt-BR) or 1,234.56 (es-MX, en-US)."""
    thousands, decimal = SEPARATORS[locale]
    sign = "-" if minor < 0 else ""
    units, cents = divmod(abs(minor), 100)
    return f"{sign}{units:,}".replace(",", thousands) + f"{decimal}{cents:02d}"


MONTHS_ES = (
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre"
)


def fdate(d: date, style: str) -> str:
    """dmy 15/10/2026, iso 2026-10-15, long_en October 15, 2026, long_es 15 de octubre de 2026."""
    if style == "dmy":
        return d.strftime("%d/%m/%Y")
    if style == "iso":
        return d.isoformat()
    if style == "long_en":
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    if style == "long_es":
        return f"{d.day} de {MONTHS_ES.split()[d.month - 1]} de {d.year}"
    raise ValueError(style)


def words_es(units: int) -> str:
    """Spanish cardinal in capitals, with the apocopes num2words misses (VEINTIÚN MIL)."""
    w = num2words(units, lang="es")
    w = re.sub(r"veintiuno(?= (mil|millón|millones)\b)", "veintiún", w)
    w = re.sub(r"\buno(?= (mil|millón|millones)\b)", "un", w)
    w = re.sub(r"veintiuno$", "veintiún", w)
    w = re.sub(r"\buno$", "un", w)
    return w.upper()


CURRENCY_ES = {
    "COP": ("PESOS", "M/CTE"),
    "MXN": ("PESOS", "M.N."),
    "USD": ("DÓLARES ESTADOUNIDENSES", ""),
    "EUR": ("EUROS", ""),
    "BRL": ("REAIS", ""),
}


def amount_words_es(minor: int, currency: str) -> str:
    """'SON: UN MILLÓN DOSCIENTOS MIL PESOS M/CTE' style; cents as NN/100."""
    units, cents = divmod(minor, 100)
    noun, suffix = CURRENCY_ES[currency]
    if currency == "MXN":
        return f"({words_es(units)} {noun} {cents:02d}/100 {suffix})"
    tail = f" CON {cents:02d}/100" if cents else ""
    return f"SON: {words_es(units)} {noun}{tail} {suffix}".strip()


def amount_words_en(minor: int, currency: str = "USD") -> str:
    units, cents = divmod(minor, 100)
    noun = {"USD": "US Dollars", "EUR": "Euros", "BRL": "Brazilian Reais"}[currency]
    w = num2words(units, lang="en").replace(",", "").replace(" and ", " ")
    return f"{w[0].upper()}{w[1:]} and {cents:02d}/100 {noun}"


# --- Fictional fiscal identifiers --------------------------------------------------


def _digest(seed: str, algo: str = "sha384") -> str:
    return hashlib.new(algo, seed.encode()).hexdigest()


def cufe(seed: str) -> str:
    """96 hex characters, the shape of a Colombian CUFE (a SHA-384)."""
    return _digest(f"cufe:{seed}")


def cfdi_uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{VERIFY}/cfdi/{seed}")).upper()


def digits(seed: str, n: int) -> str:
    return str(int(_digest(f"digits:{seed}"), 16))[:n].rjust(n, "0")


def sello(seed: str, n: int = 172) -> str:
    """A base64-looking digital seal block, made up from a hash."""
    import base64

    raw = b"".join(hashlib.sha512(f"{seed}:{i}".encode()).digest() for i in range(4))
    return base64.b64encode(raw).decode()[:n]


def qr_svg(url: str, scale: int = 2) -> str:
    return segno.make(url, error="m").svg_inline(scale=scale)


# --- Rendering ------------------------------------------------------------------


def render_html(template: str, ctx: dict) -> str:
    return ENV.get_template(template).render(**ctx)


def write_pdf(template: str, ctx: dict, out: Path) -> None:
    """Jinja2 to WeasyPrint. Metadata dates are fixed by the template, so bytes repeat."""
    html = render_html(template, ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(HERE / "templates")).write_pdf(out)


def write_image(pdf: Path, out: Path, seed: str, dpi: int = 150) -> None:
    """Page 1 rasterized as a phone scan: slight rotation, blur and JPEG compression."""
    rng = Random(seed)
    with pymupdf.open(pdf) as doc:
        img = doc[0].get_pixmap(dpi=dpi).pil_image().convert("RGB")
    img = img.rotate(rng.uniform(-1.6, 1.6), resample=Image.BICUBIC, expand=True, fillcolor="white")
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 0.8)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(68, 80), optimize=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())


def write_eml(
    out: Path,
    *,
    sender: str,
    to: str,
    subject: str,
    sent: datetime,
    text: str,
    html: str,
    msg_id: str,
) -> None:
    """A multipart/alternative email with plain-text and HTML parts and a fixed boundary."""
    msg = EmailMessage(policy=SMTP)
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = format_datetime(sent)
    msg["Message-ID"] = f"<{msg_id}@mail.alinka.invalid>"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    msg.set_boundary(f"=_alinka_{_digest(msg_id, 'sha1')[:16]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(msg.as_bytes())


def write_chat(out: Path, lines: list[tuple[datetime, str, str]]) -> None:
    """A WhatsApp-style export: '[15/10/2026, 09:41] Name: message'."""
    body = "".join(f"[{t.strftime('%d/%m/%Y, %H:%M')}] {who}: {text}\n" for t, who, text in lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")


def write_jsonl(out: Path, rows: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
