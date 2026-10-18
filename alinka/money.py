"""Money as integer minor units with an ISO 4217 code. A model never does this arithmetic."""

from __future__ import annotations

import re
from decimal import ROUND_CEILING, Decimal

# ISO 4217 minor-unit digits: the world's currencies, plus ones a document may claim.
MINOR_DIGITS: dict[str, int] = {
    "COP": 2, "MXN": 2, "BRL": 2, "EUR": 2, "USD": 2,
    "ARS": 2, "CLP": 0, "PEN": 2, "UYU": 2, "GBP": 2, "CAD": 2, "JPY": 0, "CHF": 2,
}  # fmt: skip

_SYMBOLS = re.compile(r"[A-Za-z$€£R \s]+")
_SEPARATORS = ".,'’ "


def minor_digits(currency: str) -> int:
    """Digits after the decimal point; 2, the ISO 4217 default, for codes not listed."""
    return MINOR_DIGITS.get(currency.upper(), 2)


def parse_amount(text: str | None, currency: str = "USD") -> int | None:
    """'1.234,56', '1,234.56', '$ 1.234.567' or 'USD 2,350.00' -> minor units, None if unclear."""
    if text is None:
        return None
    digits = minor_digits(currency)
    s = text.strip()
    negative = s.startswith("-") or s.startswith("(") and s.endswith(")")
    s = s.strip("-()")
    s = _SYMBOLS.sub(" ", s).strip()
    s = re.sub(r"(?<=\d)[\s'’](?=\d{3}\b)", "", s)  # spaces or apostrophes between groups
    if not s or not re.fullmatch(r"\d[\d.,]*", s) or s[-1] in ".,":
        return None
    seps = [c for c in s if c in ".,"]
    if not seps:
        whole, frac = s, ""
    else:
        last = s.rfind(seps[-1])
        tail = s[last + 1 :]
        mixed = len(set(seps)) > 1
        if mixed or (seps.count(seps[-1]) == 1 and len(tail) != 3):
            whole, frac = s[:last], tail  # the last separator is the decimal point
            if mixed and seps[-1] in whole:
                return None
        else:
            whole, frac = s, ""  # one or more thousands separators only
        groups = re.split(r"[.,]", whole)
        if len(groups) > 1 and (
            not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:])
        ):
            return None
        whole = "".join(groups)
    if len(frac) > digits:
        return None
    value = int(whole) * 10**digits + int(frac.ljust(digits, "0") or 0)
    return -value if negative else value


def to_usd_minor(amount_minor: int, currency: str, rate: Decimal, quote: str) -> int:
    """Convert to USD minor units, always rounding up (ceiling)."""
    units = Decimal(amount_minor) / (Decimal(10) ** minor_digits(currency))
    usd = units / rate if quote == "per_usd" else units * rate
    return int((usd * 100).to_integral_value(rounding=ROUND_CEILING))


def format_minor(amount_minor: int, currency: str) -> str:
    """Spanish format for reasons: 1.200,00 USD."""
    digits = minor_digits(currency)
    sign = "-" if amount_minor < 0 else ""
    whole, frac = divmod(abs(amount_minor), 10**digits)
    grouped = f"{whole:,}".replace(",", ".")
    return (
        f"{sign}{grouped},{frac:0{digits}d} {currency}" if digits else f"{sign}{grouped} {currency}"
    )


def usd_whole_to_minor(usd: int) -> int:
    return usd * 100
