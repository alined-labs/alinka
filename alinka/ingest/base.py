"""What every sanitizer returns. Internal to Lane C; only `InvoiceFacts` leaves the reader."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from alinka.types import Box, Channel


@dataclass(frozen=True)
class TextSpan:
    """One run of visible text and where it sits, normalised to 0..1, origin top-left."""

    text: str
    box: Box


@dataclass
class PageData:
    number: int  # 1-based
    width: float  # points (PDF) or pixels (image)
    height: float
    png: bytes | None = None
    spans: list[TextSpan] = field(default_factory=list)
    text: str = ""  # visible text in reading order, built by code


@dataclass
class Ingested:
    channel: Channel
    doc_sha256: str
    pages: list[PageData] = field(default_factory=list)
    hidden_content: list[str] = field(default_factory=list)
    unicode_controls: list[str] = field(default_factory=list)
    html_text_mismatch: bool = False
    instructions: list[str] = field(default_factory=list)

    @property
    def visible_text(self) -> str:
        return "\n\n".join(f"--- page {p.number} ---\n{p.text}" for p in self.pages)


# Text addressed to a system or an AI rather than to a person paying an invoice.
_INSTRUCTION_PATTERNS = [
    r"\b(ignore|disregard|forget)\b.{0,40}\b(instructions?|rules?|prompts?|checks?)\b",
    r"\b(ignora|ignorar|olvida|olvidar|omite|omitir|salta|saltar)\b.{0,40}\b(instrucci[oó]n(es)?|reglas?|aprobaci[oó]n|verificaci[oó]n|controles?)\b",
    r"\b(skip|bypass|override)\b.{0,30}\b(approval|review|verification|checks?|rules?)\b",
    r"\b(system prompt|prompt del sistema|developer mode|modo desarrollador)\b",
    r"\b(as an ai|you are an? (ai|assistant|agent|language model)|eres un[ao]? (ia|asistente|agente|modelo))\b",
    r"\b(ai|llm|gpt|claude|assistant|agent|bot)\b.{0,40}\b(must|should|shall|approve|pay)\b",
    r"\b(ia|asistente|agente|modelo|sistema)\b.{0,40}\b(debe|deber[aá]|aprueb[ae]|aprobar|pag[ae]|pagar)\b",
    r"\b(approve|pay)\b.{0,20}\b(immediately|right away|without (review|approval))\b",
    r"\b(aprobar|aprueba|apruebe|pagar|paga|pague)\b.{0,25}\b(de inmediato|inmediatamente|sin (revisi[oó]n|aprobaci[oó]n))\b",
    r"\b(mark|marcar|marca)\b.{0,20}\b(as )?(approved|paid|aprobad[ao]|pagad[ao])\b",
    r"\b(already approved|ya (fue |est[aá] )?aprobad[ao])\b",
]
_INSTRUCTION_RE = re.compile("|".join(f"(?:{p})" for p in _INSTRUCTION_PATTERNS), re.IGNORECASE)


def find_instructions(text: str) -> list[str]:
    """Return the snippets of `text` that read like instructions to a system or an AI."""
    flat = " ".join(text.split())
    return [clip(m.group(0)) for m in _INSTRUCTION_RE.finditer(flat)]


def clip(text: str, limit: int = 80) -> str:
    """One line, at most `limit` characters, for a flag message."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
