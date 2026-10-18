"""Amounts in words, Spanish and English, parsed in code into minor units."""

from __future__ import annotations

import re
import unicodedata

_EN = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_ES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
    "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90, "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400,
    "quinientos": 500, "quinientas": 500, "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}  # fmt: skip
_SMALL = _EN | _ES
_SCALES = {
    "thousand": 1_000, "mil": 1_000, "million": 1_000_000, "millions": 1_000_000,
    "millon": 1_000_000, "millones": 1_000_000, "billion": 1_000_000_000,
}  # fmt: skip
_FILLER = {
    "and", "y", "son", "the", "sum", "of", "la", "suma", "de", "us", "u", "s", "usd", "dollars",
    "dollar", "dolares", "dolar", "estadounidenses", "americanos", "pesos", "peso", "m", "cte",
    "mcte", "n", "mn", "moneda", "corriente", "legal", "colombianos", "mexicanos", "euros",
    "euro", "reais", "reales", "real", "brasilenos", "only", "exactly", "solamente", "exactos",
    "cop", "mxn", "eur", "brl", "brazilian", "mexican", "colombian", "american", "united",
    "states", "america", "colombia", "mexico", "brasil", "brazil", "nacional", "en", "letras",
    "amount", "words", "in", "total",
}  # fmt: skip
_FRACTION = re.compile(r"\b(\d{1,2})\s*/\s*100\b")
_CENTS = re.compile(r"\b(?:and|con|y)\s+([a-z\s-]+?)\s+(?:cents?|centavos?|centimos?)\b")


def parse_words(text: str | None, minor_digits: int = 2) -> int | None:
    """'TRES MILLONES CIEN MIL PESOS M/CTE' -> 310000000; None when it cannot be parsed."""
    if not text or not text.strip():
        return None
    s = unicodedata.normalize("NFKD", text.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    cents = 0
    if m := _FRACTION.search(s):
        cents = int(m.group(1))
        s = s[: m.start()] + " " + s[m.end() :]
    elif m := _CENTS.search(s):
        value = _number(m.group(1).replace("-", " ").split())
        if value is None or value > 99:
            return None
        cents = value
        s = s[: m.start()] + " " + s[m.end() :]
    tokens = re.sub(r"[^a-z]+", " ", s.replace("-", " ")).split()
    whole = _number(tokens)
    if whole is None:
        return None
    return whole * 10**minor_digits + cents * 10 ** max(minor_digits - 2, 0)


def _number(tokens: list[str]) -> int | None:
    total = current = 0
    seen = False
    for token in tokens:
        if token in _SMALL:
            current += _SMALL[token]
            seen = True
        elif token == "hundred":
            current = (current or 1) * 100
            seen = True
        elif token in _SCALES:
            total += (current or 1) * _SCALES[token]
            current = 0
            seen = True
        elif token in _FILLER:
            continue
        else:
            return None
    return total + current if seen else None
