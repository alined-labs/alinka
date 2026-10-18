"""Money as integer minor units with an ISO 4217 code. A model never does this arithmetic."""

from __future__ import annotations

import re
import unicodedata
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


# --- Amounts in words (R15) --------------------------------------------------------

_UNITS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    # Spanish, accents removed
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
    "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
    "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500,
    "quinientas": 500, "seiscientos": 600, "seiscientas": 600, "setecientos": 700,
    "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900,
    "novecientas": 900,
}  # fmt: skip
_SCALES = {"thousand": 1000, "mil": 1000, "million": 10**6, "millon": 10**6, "millones": 10**6}
_FILLER = {
    "son", "and", "y", "con", "de", "only", "pesos", "peso", "m", "cte", "mcte", "n", "mn",
    "dolares", "dolar", "estadounidenses", "americanos", "us", "usd", "dollars", "dollar",
    "euros", "euro", "eur", "reales", "real", "reais", "brazilian", "brl", "mexicanos",
    "colombianos", "cop", "mxn", "moneda", "corriente", "nacional", "cents", "centavos",
}  # fmt: skip


def words_to_minor(text: str | None, currency: str = "USD") -> int | None:
    """'SON: TRES MILLONES CIEN MIL PESOS M/CTE' or 'One thousand ... and 00/100 US Dollars'.

    None when anything is not understood: R15 then escalates instead of guessing.
    """
    if not text or "?" in text or "�" in text:
        return None
    s = unicodedata.normalize("NFKD", text.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    cents = 0
    if m := re.search(r"(\d{1,2})\s*/\s*100", s):
        cents = int(m.group(1).ljust(2, "0"))
        s = s[: m.start()] + " " + s[m.end() :]
    total = current = 0
    seen = False
    for tok in re.findall(r"[a-z]+|\d+", s.replace("-", " ")):
        if tok in _UNITS:
            current += _UNITS[tok]
            seen = True
        elif tok == "hundred":
            current = (current or 1) * 100
        elif tok in _SCALES:
            total += (current or 1) * _SCALES[tok]
            current = 0
            seen = True
        elif tok not in _FILLER:
            return None
    if not seen:
        return None
    return (total + current) * 10 ** minor_digits(currency) + cents
