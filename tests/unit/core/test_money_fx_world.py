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
