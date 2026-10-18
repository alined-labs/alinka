"""The dataset's quality gate: the fictional world loads and stays fictional (Lane B)."""

from collections import Counter
from pathlib import Path

import yaml

from alinka.types import Beneficiary, Company

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def company() -> Company:
    return Company.model_validate(yaml.safe_load((DATA / "company.yaml").read_text()))


def beneficiaries() -> list[Beneficiary]:
    raw = yaml.safe_load((DATA / "vendors.yaml").read_text())["beneficiaries"]
    return [Beneficiary.model_validate(b) for b in raw]


def test_company_is_the_fictional_delaware_payer():
    c = company()
    assert "Demo" in c.name and c.tax_id.startswith("DEMO")
    assert (c.country, c.state) == ("US", "DE")
    assert {cc.id for cc in c.cost_centers} == {"engineering", "design", "operations", "software"}
    assert len(c.approvers) == 2 and c.balance_usd_minor > 0


def test_thirteen_beneficiaries_in_the_planned_mix():
    bens = beneficiaries()
    assert [b.id for b in bens] == [f"BEN-{i:02d}" for i in range(1, 14)]
    assert Counter(b.country for b in bens) == {
        "CO": 5,
        "MX": 2,
        "BR": 1,
        "AR": 1,
        "US": 3,
        "ES": 1,
    }
    assert {b.currency for b in bens if b.country == "CO"} <= {"COP", "USD"}
    assert {b.country: b.currency for b in bens if b.country in {"MX", "BR", "AR", "ES"}} == {
        "MX": "MXN",
        "BR": "BRL",
        "AR": "USD",
        "ES": "EUR",
    }


def test_beneficiaries_are_fictional_and_consistent():
    cost_centers = {cc.id for cc in company().cost_centers}
    bens = beneficiaries()
    for b in bens:
        assert b.tax_id.startswith("DEMO"), b.id
        assert "DEMO" in b.account_on_file, b.id
        assert b.contract.currency == b.currency, b.id
        assert b.contract.cost_center in cost_centers, b.id
        assert b.contract.scope_es and b.contract.scope_en, b.id
        assert b.contract.valid_from <= b.contract.valid_to, b.id
        assert b.contract.rate_minor > 0 and 0 <= b.contract.tolerance_pct <= 10, b.id
    for key in ("tax_id", "name", "account_on_file"):
        assert len({getattr(b, key) for b in bens}) == len(bens), key
