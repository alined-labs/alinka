"""Verification in code: words, amounts, dates, currency, grounding, checks and risk."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pymupdf
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from num2words import num2words

from alinka.cache import ResponseCache
from alinka.ingest.image import ingest_image
from alinka.ingest.pdf import ingest_pdf
from alinka.types import CRITICAL_FIELDS, Computed, Confidence, Field, Printed
from alinka.verify import checks
from alinka.verify.facts import facts_for_path
from alinka.verify.ground import ground
from alinka.verify.ground import norm as ground_norm
from alinka.verify.normalize import detect_currency, find_dates, parse_date
from alinka.verify.words import parse_words

ROOT = Path(__file__).resolve().parents[3]


@settings(max_examples=300, deadline=None)
@given(st.integers(min_value=0, max_value=999_999_999), st.sampled_from(["es", "en"]))
def test_words_round_trip_num2words(n, lang):
    assert parse_words(num2words(n, lang=lang)) == n * 100


@pytest.mark.parametrize(
    ("text", "minor"),
    [
        ("SON: TRES MILLONES CIEN MIL PESOS M/CTE", 310_000_000),
        ("(VEINTISÉIS MIL PESOS 00/100 M.N.)", 2_600_000),
        ("SON: SETECIENTOS VEINTE DÓLARES ESTADOUNIDENSES", 72_000),
        ("One thousand one hundred eighty and 00/100 US Dollars", 118_000),
        ("Two thousand four hundred and 50/100 US Dollars", 240_050),
        ("mil doscientos euros con cincuenta centavos", 120_050),
        ("Twenty-one dollars and five cents", 2_105),
        ("UN MILLÓN DOSCIENTOS MIL PESOS", 120_000_000),
    ],
)
def test_words_as_printed(text, minor):
    assert parse_words(text) == minor


@pytest.mark.parametrize("text", ["TRES MILLNES CIEN MIL PES", "SON: ####", "", "PESOS M/CTE"])
def test_garbled_words_are_unparseable(text):
    assert parse_words(text) is None


@pytest.mark.parametrize(
    ("text", "month_first", "expected"),
    [
        ("October 30, 2026", True, date(2026, 10, 30)),
        ("30/09/2026", False, date(2026, 9, 30)),
        ("10/05/2026", True, date(2026, 10, 5)),
        ("10/05/2026", False, date(2026, 5, 10)),
        ("2026-10-02T16:30:12", False, date(2026, 10, 2)),
        ("31 de julio de 2026", False, date(2026, 7, 31)),
        ("15 oct. 2026", False, date(2026, 10, 15)),
        ("Net 30", False, None),
    ],
)
def test_dates(text, month_first, expected):
    assert parse_date(text, month_first) == expected


def test_service_period_has_two_dates():
    assert find_dates("September 1, 2026 – September 30, 2026") == [
        date(2026, 9, 1),
        date(2026, 9, 30),
    ]
    assert find_dates("01/09/2026 al 30/09/2026") == [date(2026, 9, 1), date(2026, 9, 30)]


@pytest.mark.parametrize(
    ("texts", "code"),
    [
        (("USD",), "USD"),
        (("Pesos colombianos",), "COP"),
        (("$", "$ 3.100.000,00 COP"), "COP"),
        (("$", None, "VEINTISÉIS MIL PESOS 00/100 M.N."), "MXN"),
        (("€",), "EUR"),
        (("$",), None),
    ],
)
def test_currency(texts, code):
    assert detect_currency(*texts) == code


def _pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Factura DEMO-7 (empresa ficticia)", fontsize=12)
    page.insert_text((72, 130), "Subtotal 1.000,00   IVA 250,00", fontsize=12)
    page.insert_text((72, 160), "Total a pagar: 1.250,00 USD", fontsize=12)
    return doc.tobytes()


def test_grounding_needs_the_quote_on_the_page_and_the_value_in_the_quote():
    doc = ingest_pdf(_pdf())
    good = ground(Field(value="1.250,00", quote="Total a pagar: 1.250,00 USD"), doc, {})
    assert good.grounded and len(good.boxes) == 1
    box = good.boxes[0]
    assert box.page == 1 and 0.1 < box.x0 < box.x1 < 0.6 and 0.15 < box.y0 < box.y1 < 0.22
    assert not ground(
        Field(value="9.250,00", quote="Total a pagar: 1.250,00 USD"), doc, {}
    ).grounded
    assert not ground(Field(value="1.250,00", quote="Total: 1.250,00"), doc, {}).grounded
    assert not ground(Field(value="1.250,00", quote=None), doc, {}).grounded


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="no Tesseract")
def test_grounding_on_ocr_words_gives_boxes():
    from tests.unit.reader.test_reader_text import _image

    doc = ingest_image(_image(["CUENTA DE COBRO", "TOTAL 3.100.000,00 COP"]))
    field = ground(Field(value="3.100.000,00", quote="TOTAL 3.100.000,00 COP"), doc, {})
    assert field.grounded and field.boxes and field.boxes[0].y0 > 0.4


def test_money_spans_and_reconcile():
    doc = ingest_pdf(_pdf())
    assert checks.money_spans(doc, "USD") >= {100_000, 25_000, 125_000}
    ok = Computed(currency="USD", total_minor=125_000, subtotal_minor=100_000, tax_minor=25_000)
    assert checks.amount_in_regex(doc, ok) and checks.totals_reconcile(ok)
    bad = ok.model_copy(update={"total_minor": 135_000})
    assert checks.amount_in_regex(doc, bad) is False and checks.totals_reconcile(bad) is False


def test_compare_ignores_form_but_not_content():
    a = Printed(total=Field(value="1,250.00"), due_date=Field(value="October 30, 2026"))
    b = Printed(total=Field(value="1250.00"), due_date=Field(value="10/30/2026"))
    c = Printed(total=Field(value="1,520.00"), due_date=Field(value="October 30, 2026"))
    assert (
        checks.compare(a, b, "USD", True)["total"] and checks.compare(a, b, "USD", True)["due_date"]
    )
    assert not checks.compare(a, c, "USD", True)["total"]


def test_risk_only_rises_with_doubts():
    p = Printed(total=Field(value="1", confidence=Confidence.HIGH))
    base, _ = checks.risk(p, ungrounded=[], disagreements=[], in_regex=True, reconcile=None,
                          checker_failed=False, ocr_confidence=None)  # fmt: skip
    worse, notes = checks.risk(p, ungrounded=["total"], disagreements=["total"], in_regex=False,
                               reconcile=False, checker_failed=False, ocr_confidence=40)  # fmt: skip
    failed, _ = checks.risk(p, ungrounded=[], disagreements=[], in_regex=True, reconcile=None,
                            checker_failed=True, ocr_confidence=None)  # fmt: skip
    assert base == 0 and 0.9 < worse < 1 and failed == 1.0 and len(notes) == 5


MONTH = [
    json.loads(line)
    for line in (ROOT / "data/labels/showcase.jsonl").read_text().splitlines()
    if line.strip()
]


def _facts(label):
    path = ROOT / label["path"]
    received = datetime.fromisoformat(label["received_at"])
    facts, _ = facts_for_path(
        path, invoice_id=label["invoice_id"], received_at=received, cache=ResponseCache("replay")
    )
    return facts


def test_pipeline_replays_oct_01_with_grounded_boxes_and_agreement():
    facts = _facts(MONTH[0])
    assert facts.flags.extraction_error is None
    assert [c.role for c in facts.calls][:2] == ["reader", "checker"]
    for name in CRITICAL_FIELDS:
        field = getattr(facts.printed, name)
        assert field.grounded and field.agreed and field.boxes, name
    assert facts.computed.total_minor == 118_000 and facts.computed.currency == "USD"
    assert facts.computed.due_date == date(2026, 10, 30) and facts.computed.words_minor == 118_000
    assert facts.verification.amount_in_regex and facts.verification.risk < 0.2


def test_month_field_accuracy_is_at_least_90_percent():
    fields = ("total", "currency", "beneficiary_name", "due_date")
    right = total = 0
    for label in MONTH:
        facts = _facts(label)
        for name in fields:
            gold = label["gold_facts"].get(name)
            if gold is None:
                continue
            total += 1
            got = getattr(facts.printed, name).value
            right += got is not None and (got == gold or ground_norm(got) == ground_norm(gold))
    assert total >= 100 and right / total >= 0.9
