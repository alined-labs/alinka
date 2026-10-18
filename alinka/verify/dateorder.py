"""Which way round a numeric date like 01/09/2026 reads, decided in code from the document.

Numeric dates are day-first in Spanish documents and for every issuer outside the US
(CO, MX, AR, ES, BR...); only English documents from US issuers are month-first. The
issuer's country comes from what the document prints about the issuer (its tax-ID label
or format, its fiscal ID, its title, its bank account scheme and its currency), never
from the beneficiary list. When no signal settles it, the document's own unambiguous
dates (a 13 or more in one place) decide; when nothing does, or the signals contradict
each other, the order is unknown and an ambiguous date stays unparsed and raises risk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from alinka.types import Language, Printed

Order = Literal["dmy", "mdy"]
US = "US"

_NUMERIC = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
DATE_FIELDS = ("issue_date", "due_date", "service_period")

# (country, pattern) on the issuer's own fields. Patterns run on upper-cased text.
_TAX_ID = [
    (US, re.compile(r"\b(EIN|TIN|FEIN)\b|\b\d{2}-\d{7}\b")),
    ("CO", re.compile(r"\bNIT\b|\bC\.\s?C\.|\bCC-\d|\b\d{9}-\d\b")),
    ("MX", re.compile(r"\bRFC\b|\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b")),
    ("AR", re.compile(r"\bCUI[TL]\b|\b\d{2}-\d{8}-\d\b")),
    ("ES", re.compile(r"\b(NIF|CIF)\b|\bES[A-Z]\d{7}[A-Z0-9]?\b")),
    ("BR", re.compile(r"\b(CNPJ|CPF)\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")),
]
_DOCUMENT = [
    ("CO", re.compile(r"CUENTA DE COBRO|\bCUFE\b|FACTURA ELECTR[OÓ]NICA DE VENTA|\bDIAN\b")),
    ("MX", re.compile(r"\bCFDI\b|FOLIO FISCAL|\bCLABE\b")),
    ("AR", re.compile(r"\bCAE\b|\bAFIP\b|\bARCA\b")),
    ("BR", re.compile(r"\bNFS-?E\b|NOTA FISCAL|CHAVE DE ACESSO")),
    ("ES", re.compile(r"\bIBAN\s?ES\d")),
    (US, re.compile(r"\bABA\b|\bROUTING\b")),
]
_CURRENCY = {"COP": "CO", "MXN": "MX", "BRL": "BR", "ARS": "AR", "EUR": "ES"}


@dataclass(frozen=True)
class DateOrder:
    order: Order | None  # None: unknown, so an ambiguous numeric date is not parsed
    reason: str


def issuer_country(printed: Printed, currency: str | None) -> tuple[str | None, str]:
    """The issuer's country from the document, and the signal that gave it."""
    tax = " ".join(
        x.upper() for x in (printed.beneficiary_tax_id.quote, printed.beneficiary_tax_id.value) if x
    )
    for country, pattern in _TAX_ID:
        if pattern.search(tax):
            return country, f"issuer tax ID ({country})"
    doc = " ".join(
        x.upper()
        for f in (printed.doc_type, printed.fiscal_id, printed.bank_account)
        for x in (f.quote, f.value)
        if x
    )
    found = {country for country, pattern in _DOCUMENT if pattern.search(doc)}
    if len(found) == 1:
        country = found.pop()
        return country, f"document markers ({country})"
    if found:  # markers from different countries: no single answer
        return None, "conflicting document markers " + ",".join(sorted(found))
    if currency in _CURRENCY:
        return _CURRENCY[currency], f"currency {currency}"
    return None, "no issuer country on the document"


def evidence(printed: Printed) -> set[Order]:
    """Orders proven by the document's own unambiguous numeric dates (a part over 12)."""
    seen: set[Order] = set()
    for name in DATE_FIELDS:
        for a, b, _ in _NUMERIC.findall(getattr(printed, name).value or ""):
            first, second = int(a), int(b)
            if first > 12 >= second:
                seen.add("dmy")
            elif second > 12 >= first:
                seen.add("mdy")
    return seen


def date_order(printed: Printed, language: Language | None, currency: str | None) -> DateOrder:
    proof = evidence(printed)
    if language == Language.ES:
        order: Order | None = "dmy"
        reason = "Spanish document"
    else:
        country, why = issuer_country(printed, currency)
        if country is None:
            order, reason = None, why
        elif country == US:
            order, reason = "mdy", f"English document, {why}"
        else:
            order, reason = "dmy", why
    if order is None:
        if len(proof) == 1:
            order = next(iter(proof))
            return DateOrder(order, f"{reason}; the document's own dates are {order}")
        return DateOrder(None, f"{reason}; numeric dates are ambiguous")
    if proof and proof != {order}:
        return DateOrder(None, f"{reason}, but the document's own dates contradict {order}")
    return DateOrder(order, reason)


def is_ambiguous(day_or_month: int, month_or_day: int) -> bool:
    """Both parts could be a month and they differ: 01/09 but not 05/05 or 13/09."""
    return day_or_month <= 12 and month_or_day <= 12 and day_or_month != month_or_day


def ambiguous_fields(printed: Printed, order: Order | None) -> list[str]:
    """Date fields left unparsed because the order is unknown."""
    if order is not None:
        return []
    return [
        name
        for name in DATE_FIELDS
        if any(
            is_ambiguous(int(a), int(b))
            for a, b, _ in _NUMERIC.findall(getattr(printed, name).value or "")
        )
    ]
