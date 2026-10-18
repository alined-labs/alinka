"""Official exchange rates from data/fx.yaml: the latest on or before as_of, never stale."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml

from alinka.money import to_usd_minor
from alinka.types import FxUsed

FX_PATH = Path(__file__).resolve().parents[1] / "data" / "fx.yaml"


def load_fx(path: Path = FX_PATH) -> tuple[FxUsed, ...]:
    raw = yaml.safe_load(path.read_text())
    return tuple(FxUsed.model_validate(r) for r in raw["rates"])


def rate_for(
    currency: str, as_of: date, max_age_days: int, table: tuple[FxUsed, ...]
) -> FxUsed | None:
    """Latest rate on or before as_of and at most max_age_days old; None makes R02/R10 escalate."""
    oldest = as_of - timedelta(days=max_age_days)
    candidates = [r for r in table if r.currency == currency and oldest <= r.date <= as_of]
    return max(candidates, key=lambda r: r.date, default=None)


def usd_of(
    amount_minor: int, currency: str, as_of: date, max_age_days: int, table: tuple[FxUsed, ...]
) -> tuple[int, FxUsed | None] | None:
    """USD minor units (rounded up) and the rate used; None when no fresh rate exists."""
    if currency == "USD":
        return amount_minor, None
    fx = rate_for(currency, as_of, max_age_days, table)
    if fx is None:
        return None
    return to_usd_minor(amount_minor, currency, Decimal(fx.rate), fx.quote), fx
