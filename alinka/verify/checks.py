"""Code checks on a reading: money spans, totals, the second reading, and the risk."""

from __future__ import annotations

import re

from alinka.extract.schema import FIELD_ORDER
from alinka.ingest.base import Ingested
from alinka.types import CRITICAL_FIELDS, Computed, Confidence, Printed
from alinka.verify.dateorder import Order
from alinka.verify.ground import norm
from alinka.verify.normalize import amount, parse_date

_MONEY = re.compile(
    r"(?<![\w.,])(?:\d{1,3}(?:[.,  ']\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\w,.]?\d)"
)
AMOUNT_FIELDS = ("subtotal", "tax_total", "total")
DATE_FIELDS = ("issue_date", "due_date")
OCR_CONFIDENCE_MIN = 60.0
AMBIGUOUS_DATE_RISK = 0.7


def money_spans(doc: Ingested, currency: str | None) -> set[int]:
    """Every amount the visible text prints, in minor units of `currency`."""
    found: set[int] = set()
    for page in doc.pages:
        for m in _MONEY.finditer(page.text):
            value = amount(m.group(0), currency)
            if value is not None:
                found.add(value)
    return found


def amount_in_regex(doc: Ingested, computed: Computed) -> bool | None:
    if computed.total_minor is None:
        return None
    return computed.total_minor in money_spans(doc, computed.currency)


def totals_reconcile(computed: Computed) -> bool | None:
    c = computed
    if c.total_minor is None or c.subtotal_minor is None or c.tax_minor is None:
        return None
    return c.subtotal_minor + c.tax_minor == c.total_minor


def same_value(
    name: str, a: str | None, b: str | None, currency: str | None, order: Order | None
) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if name in AMOUNT_FIELDS:
        x, y = amount(a, currency), amount(b, currency)
        if x is not None and y is not None:
            return x == y
    if name in DATE_FIELDS:
        x, y = parse_date(a, order), parse_date(b, order)
        if x is not None and y is not None:
            return x == y
    return norm(a) == norm(b) or norm(a).replace(" ", "") == norm(b).replace(" ", "")


def compare(
    reader: Printed, checker: Printed, currency: str | None, order: Order | None
) -> dict[str, bool]:
    """Field by field: does the second reading return the same value?"""
    return {
        name: same_value(
            name, getattr(reader, name).value, getattr(checker, name).value, currency, order
        )
        for name in FIELD_ORDER
    }


def risk(
    printed: Printed,
    *,
    ungrounded: list[str],
    disagreements: list[str],
    in_regex: bool | None,
    reconcile: bool | None,
    checker_failed: bool,
    ocr_confidence: float | None,
    ambiguous_dates: list[str] | None = None,
) -> tuple[float, list[str]]:
    """Combine independent doubts as 1 - prod(1 - p); any single strong doubt dominates."""
    parts: list[tuple[float, str]] = []
    parts += [(0.5, f"ungrounded {f}") for f in ungrounded]
    parts += [(0.5, f"readings disagree on {f}") for f in disagreements]
    for name in CRITICAL_FIELDS:
        field = getattr(printed, name)
        if field.value is not None and field.confidence == Confidence.MEDIUM:
            parts.append((0.2, f"medium confidence on {name}"))
        elif field.value is not None and field.confidence == Confidence.LOW:
            parts.append((0.4, f"low confidence on {name}"))
    if in_regex is False:
        parts.append((0.5, "total not among the page's amounts"))
    if reconcile is False:
        parts.append((0.4, "subtotal plus tax differs from total"))
    if checker_failed:
        parts.append((1.0, "second reading failed"))
    if ambiguous_dates:  # enough on its own for R10: a missing date can hide R09 or R16
        parts.append(
            (AMBIGUOUS_DATE_RISK, "ambiguous numeric dates: " + ", ".join(ambiguous_dates))
        )
    if ocr_confidence is not None and ocr_confidence < OCR_CONFIDENCE_MIN:
        parts.append((0.3, f"OCR confidence {ocr_confidence:.0f}"))
    keep = 1.0
    for p, _ in parts:
        keep *= 1 - p
    return round(1 - keep, 4), [note for _, note in parts]
