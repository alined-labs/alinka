"""Numeric date order: day-first for Spanish and non-US issuers, month-first only en-US."""

from __future__ import annotations

from datetime import date

import pytest

from alinka.types import Confidence, Field, Language, Printed
from alinka.verify import checks
from alinka.verify.dateorder import ambiguous_fields, date_order, issuer_country
from alinka.verify.normalize import find_dates, parse_date


def _printed(tax_quote=None, issue="01/09/2026", due="10/09/2026", period=None, **fields):
    return Printed(
        beneficiary_tax_id=Field(value=(tax_quote or "").split(": ")[-1] or None, quote=tax_quote),
        issue_date=Field(value=issue),
        due_date=Field(value=due),
        service_period=Field(value=period),
        **fields,
    )


# --- The same printed date, both orders -------------------------------------------


@pytest.mark.parametrize(
    ("order", "expected"),
    [("dmy", date(2026, 9, 1)), ("mdy", date(2026, 1, 9)), (None, None)],
)
def test_01_09_2026_reads_by_order_and_stays_unparsed_when_unknown(order, expected):
    assert parse_date("01/09/2026", order) == expected


@pytest.mark.parametrize("order", ["dmy", "mdy", None])
def test_unambiguous_dates_read_the_same_whatever_the_order(order):
    assert parse_date("13/09/2026", order) == date(2026, 9, 13)
    assert parse_date("09/13/2026", order) == date(2026, 9, 13)
    assert parse_date("05/05/2026", order) == date(2026, 5, 5)  # day equals month
    assert parse_date("September 1, 2026", order) == date(2026, 9, 1)
    assert parse_date("2026-09-01", order) == date(2026, 9, 1)


def test_unknown_order_drops_only_the_ambiguous_date_of_a_period():
    assert find_dates("01/09/2026 al 30/09/2026", None) == [date(2026, 9, 30)]
    assert find_dates("01/09/2026 al 30/09/2026", "dmy") == [date(2026, 9, 1), date(2026, 9, 30)]
    assert find_dates("09/01/2026 - 09/30/2026", "mdy") == [date(2026, 9, 1), date(2026, 9, 30)]


# --- Deciding the order from the document -------------------------------------------


def test_spanish_documents_are_day_first_even_from_a_us_issuer():
    d = date_order(_printed("EIN: DEMO-12-3456789"), Language.ES, "USD")
    assert d.order == "dmy" and d.reason == "Spanish document"


@pytest.mark.parametrize(
    ("tax_quote", "country"),
    [
        ("NIT: DEMO-901234567-7", "CO"),
        ("C.C.: DEMO-CC-1020345678", "CO"),
        ("RFC: DEMO010101AB1", "MX"),
        ("CUIT: DEMO-30-71234567-8", "AR"),
        ("NIF: DEMO-ESB12345678", "ES"),
        ("CNPJ: DEMO.123.456/0001-08", "BR"),
    ],
)
def test_english_documents_from_non_us_issuers_are_day_first(tax_quote, country):
    printed = _printed(tax_quote)
    assert issuer_country(printed, "USD")[0] == country
    d = date_order(printed, Language.EN, "USD")
    assert d.order == "dmy" and country in d.reason
    assert parse_date(printed.issue_date.value, d.order) == date(2026, 9, 1)


def test_english_documents_from_us_issuers_are_month_first():
    printed = _printed("EIN: DEMO-12-3456789")
    d = date_order(printed, Language.EN, "USD")
    assert d.order == "mdy"
    assert parse_date(printed.issue_date.value, d.order) == date(2026, 1, 9)


@pytest.mark.parametrize(
    ("fields", "currency", "country"),
    [
        (
            {
                "doc_type": Field(
                    value="NFS-E · NOTA FISCAL DE SERVIÇO ELETRÔNICA · SERVICE INVOICE"
                )
            },
            "USD",
            "BR",
        ),
        (
            {"fiscal_id": Field(value="070C5F15-6244", quote="Folio fiscal (UUID) 070C5F15-6244")},
            "USD",
            "MX",
        ),
        ({"bank_account": Field(value="IBAN ES00 DEMO 0000 0013")}, "USD", "ES"),
        ({"bank_account": Field(value="Demo Federal Bank · ABA DEMO-0210")}, "USD", "US"),
        ({}, "COP", "CO"),
        ({}, "EUR", "ES"),
    ],
)
def test_other_issuer_signals(fields, currency, country):
    assert issuer_country(_printed(None, **fields), currency)[0] == country


def test_english_without_a_country_uses_the_documents_own_dates():
    day_first = _printed(None, issue="01/10/2026", due="31/10/2026")
    assert date_order(day_first, Language.EN, "USD").order == "dmy"
    month_first = _printed(None, issue="10/01/2026", due="10/31/2026")
    assert date_order(month_first, Language.EN, "USD").order == "mdy"


def test_english_without_any_signal_is_ambiguous_and_raises_risk():
    printed = _printed(None, period="02/09/2026 to 03/09/2026")
    d = date_order(printed, Language.EN, "USD")
    assert d.order is None and "ambiguous" in d.reason
    assert ambiguous_fields(printed, d.order) == ["issue_date", "due_date", "service_period"]
    assert parse_date(printed.due_date.value, d.order) is None
    p = Printed(total=Field(value="1", confidence=Confidence.HIGH))
    risk, notes = checks.risk(p, ungrounded=[], disagreements=[], in_regex=True, reconcile=None,
                              checker_failed=False, ocr_confidence=None,
                              ambiguous_dates=ambiguous_fields(printed, d.order))  # fmt: skip
    assert risk >= 0.7 and "ambiguous numeric dates" in notes[0]


def test_a_us_issuer_whose_dates_prove_day_first_is_ambiguous():
    printed = _printed("EIN: DEMO-12-3456789", issue="01/10/2026", due="31/10/2026")
    d = date_order(printed, Language.EN, "USD")
    assert d.order is None and "contradict" in d.reason
    assert ambiguous_fields(printed, d.order) == ["issue_date"]


def test_known_order_leaves_nothing_ambiguous():
    assert ambiguous_fields(_printed("RFC: DEMO010101AB1"), "dmy") == []
