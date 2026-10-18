from datetime import date
from decimal import Decimal

import pytest

from alinka.fx import load_fx, rate_for, usd_of
from alinka.money import format_minor, parse_amount, to_usd_minor
from alinka.world import load_rules, load_world


@pytest.mark.parametrize(
    ("text", "minor"),
    [
        ("1.234,56", 123456),
        ("1,234.56", 123456),
        ("$ 1.234.567", 123456700),
        ("USD 2,350.00", 235000),
        ("720,00", 72000),
        ("3.100.000,00", 310000000),
        ("COP $5.200.000", 520000000),
        ("0.00", 0),
        ("1 234,50 €", 123450),
        ("R$ 12.500,00", 1250000),
        ("1180", 118000),
        ("-15,00", -1500),
    ],
)
def test_parse_amount(text, minor):
    assert parse_amount(text, "USD") == minor


@pytest.mark.parametrize("text", [None, "", "abc", "1,2345", "12.34.5", "1.234,56.7", "1,"])
def test_parse_amount_refuses_unclear_text(text):
    assert parse_amount(text) is None


def test_usd_conversion_rounds_up():
    assert to_usd_minor(520000000, "COP", Decimal("3174.67"), "per_usd") == 163797  # 1637.9673 up
    assert to_usd_minor(100, "EUR", Decimal("1.1253"), "usd_per_unit") == 113
    assert to_usd_minor(300000, "COP", Decimal("3000"), "per_usd") == 100  # exact stays exact


def test_format_minor_is_spanish():
    assert format_minor(120000, "USD") == "1.200,00 USD"
    assert format_minor(520000000, "COP") == "5.200.000,00 COP"


def test_fx_latest_on_or_before_and_not_stale():
    table = load_fx()
    assert rate_for("COP", date(2026, 10, 17), 4, table).rate == "3174.67"
    assert rate_for("COP", date(2026, 10, 16), 4, table).rate == "3170.46"
    assert rate_for("EUR", date(2026, 10, 17), 4, table).date == date(2026, 10, 16)
    assert rate_for("MXN", date(2026, 10, 25), 4, table) is None  # too old
    assert rate_for("MXN", date(2026, 10, 1), 4, table) is None  # nothing before
    assert rate_for("ARS", date(2026, 10, 17), 4, table) is None
    assert usd_of(5000, "USD", date(2026, 10, 17), 4, table) == (5000, None)
    usd, fx = usd_of(100000, "BRL", date(2026, 10, 17), 4, table)
    assert fx.rate == "5.08260" and usd == 19675


def test_every_world_currency_has_a_rate():
    world, cfg = load_world(), load_rules()
    for ben in world.beneficiaries:
        assert usd_of(100, ben.currency, cfg.as_of, cfg.fx_max_age_days, world.fx) is not None
    assert world.beneficiary("BEN-01").currency == "COP"


@pytest.mark.parametrize(
    ("text", "cur", "minor"),
    [
        ("SON: TRES MILLONES CIEN MIL PESOS M/CTE", "COP", 310000000),
        ("SON: VEINTISÉIS MILLONES PESOS M/CTE", "COP", 2600000000),
        ("One thousand one hundred eighty and 00/100 US Dollars", "USD", 118000),
        ("Four hundred twenty-eight and 50/100 US Dollars", "USD", 42850),
        ("(DIEZ MIL CIENTO OCHENTA PESOS 00/100 M.N.)", "MXN", 1018000),
        ("SON: SETECIENTOS VEINTE DÓLARES ESTADOUNIDENSES", "USD", 72000),
        ("Thirteen thousand five hundred and 00/100 Brazilian Reais", "BRL", 1350000),
        ("SON: MIL DOSCIENTOS QUINCE EUROS", "EUR", 121500),
        ("treinta y cinco mil", "USD", 3500000),
    ],
)
def test_words_to_minor(text, cur, minor):
    from alinka.money import words_to_minor

    assert words_to_minor(text, cur) == minor


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "F?ur h?ndr?d tw?nty and ??/100 US D?llars",
        "(V?INTISÉIS M?L P?SOS)",
        "Pay now",
        "SON: PESOS",
    ],
)
def test_words_to_minor_refuses(text):
    from alinka.money import words_to_minor

    assert words_to_minor(text) is None
