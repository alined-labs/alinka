"""Printed strings to `Computed`: amounts, dates, currency and IDs, all in code."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from alinka.fx import usd_of
from alinka.money import MINOR_DIGITS, parse_amount
from alinka.rules import digits, norm_id
from alinka.types import Computed, Printed, RulesConfig
from alinka.verify.dateorder import Order, is_ambiguous
from alinka.verify.words import parse_words

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12, "ene": 1, "abr": 4, "ago": 8, "dic": 12,
}  # fmt: skip
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})")),
    ("num", re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")),
    ("mdy", re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")),
    (
        "dmy",
        re.compile(rf"\b(\d{{1,2}})(?:\s+de)?\s+({_MONTH})\.?(?:\s+de(?:l)?)?,?\s+(\d{{4}})\b"),
    ),
]

_CODE = re.compile(r"\b(USD|COP|MXN|EUR|BRL)\b")
_CURRENCY_WORDS = [
    ("USD", re.compile(r"\b(us\s*\$|u\.s\.|dolar|dolares|dollars?|estadounidenses)\b")),
    ("MXN", re.compile(r"(m\.\s?n\.|\bmexican|\bmexicanos?\b)")),
    ("COP", re.compile(r"(m/\s?cte|\bcolombian|\bcolombianos?\b)")),
    ("EUR", re.compile(r"(€|\beuros?\b)")),
    ("BRL", re.compile(r"(r\$|\breais\b|\breales\b|\bbrasilen)")),
]


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def find_dates(text: str | None, order: Order | None = "dmy") -> list[date]:
    """Every date in `text`, in order of appearance. With `order` None (unknown), a
    numeric date whose day and month could swap, such as 01/09/2026, is left out."""
    if not text:
        return []
    s = _fold(text)
    found: list[tuple[int, date]] = []
    taken: list[range] = []
    for kind, pattern in _DATE_PATTERNS:
        for m in pattern.finditer(s):
            if any(m.start() in r for r in taken):
                continue
            a, b, c = m.groups()
            try:
                if kind == "iso":
                    d = date(int(a), int(b), int(c))
                elif kind == "num":
                    day, month = int(a), int(b)
                    if order is None and is_ambiguous(day, month):
                        taken.append(range(m.start(), m.end()))
                        continue
                    if month > 12 or (order == "mdy" and day <= 12):
                        day, month = month, day
                    d = date(int(c), month, day)
                elif kind == "mdy":
                    d = date(int(c), _MONTHS[a], int(b))
                else:
                    d = date(int(c), _MONTHS[b], int(a))
            except ValueError:
                continue
            found.append((m.start(), d))
            taken.append(range(m.start(), m.end()))
    return [d for _, d in sorted(found, key=lambda x: x[0])]


def parse_date(text: str | None, order: Order | None = "dmy") -> date | None:
    dates = find_dates(text, order)
    return dates[0] if dates else None


def detect_currency(*texts: str | None) -> str | None:
    """ISO code from the printed currency first, then from the other texts given."""
    for text in texts:
        if not text:
            continue
        if m := _CODE.search(text.upper()):
            return m.group(1)
        folded = _fold(text)
        for code, pattern in _CURRENCY_WORDS:
            if pattern.search(folded):
                return code
    return None


def amount(text: str | None, currency: str | None) -> int | None:
    if text is None or currency not in MINOR_DIGITS:
        return None
    return parse_amount(text, currency)


def compute(printed: Printed, cfg: RulesConfig, fx_table: tuple, order: Order | None) -> Computed:
    p = printed
    currency = detect_currency(
        p.currency.value, p.total.quote, p.total.value, p.amount_in_words.value
    )
    total = amount(p.total.value, currency)
    words_minor = None
    words_unparseable = False
    if p.amount_in_words.value and currency:
        words_minor = parse_words(p.amount_in_words.value, MINOR_DIGITS[currency])
        words_unparseable = words_minor is None
    period = find_dates(p.service_period.value, order)
    usd_minor, fx = None, None
    if total is not None and currency:
        got = usd_of(total, currency, cfg.as_of, cfg.fx_max_age_days, fx_table)
        if got is not None:
            usd_minor, fx = got
    account = digits(p.bank_account.value or "")
    return Computed(
        currency=currency,
        total_minor=total,
        subtotal_minor=amount(p.subtotal.value, currency),
        tax_minor=amount(p.tax_total.value, currency),
        words_minor=words_minor,
        words_unparseable=words_unparseable,
        issue_date=parse_date(p.issue_date.value, order),
        due_date=parse_date(p.due_date.value, order),
        period_start=period[0] if period else None,
        period_end=period[-1] if len(period) > 1 else None,
        invoice_number_norm=norm_id(p.invoice_number.value),
        beneficiary_tax_id_norm=norm_id(p.beneficiary_tax_id.value),
        buyer_tax_id_norm=norm_id(p.buyer_tax_id.value),
        bank_account_norm=account or None,
        usd_minor=usd_minor,
        fx=fx,
    )
