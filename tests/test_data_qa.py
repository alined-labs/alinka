"""The dataset's quality gate: the fictional world loads and stays fictional (Lane B)."""

import json
from collections import Counter
from pathlib import Path

import yaml

from alinka.types import RULE_IDS, SECURITY_RULES, Beneficiary, Company, Decision, Label, Split

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# How each rule fails, from PLAN section 7. R15 holds when the words differ and escalates
# when they cannot be parsed, so a trap on R15 alone decides it.
FAILS_AS = {r: Decision.ESCALATE for r in ("R01", "R06", "R09", "R10", "R11", "R12", "R13")}
FAILS_AS |= {r: Decision.HOLD for r in ("R02", "R03", "R04", "R05", "R07", "R08", "R14", "R16")}


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


def traps() -> dict:
    return yaml.safe_load((DATA / "generator/traps.yaml").read_text())


def test_traps_follow_the_rule_table():
    doc = traps()
    assert doc["routine"]["decision"] == "PAY" and doc["routine"]["rules"] == []
    splits = {s.value for s in Split}
    for key, t in doc["traps"].items():
        rules = t["rules"]
        assert rules and set(rules) <= set(RULE_IDS), key
        assert set(t["splits"]) <= splits and t["how"], key
        impersonation = "R01" in rules and "attack" in t["splits"]  # new vendors are no alert
        assert t["security"] == (bool(set(rules) & SECURITY_RULES - {"R01"}) or impersonation), key
        expected = {FAILS_AS[r] for r in rules if r in FAILS_AS}
        if expected:
            want = Decision.HOLD if Decision.HOLD in expected else Decision.ESCALATE
            assert Decision(t["decision"]) == want, key
        else:
            assert rules == ["R15"] and t["decision"] in {"HOLD", "ESCALATE"}, key


def labels() -> list[Label]:
    rows = []
    for f in sorted((DATA / "labels").glob("*.jsonl")):
        rows += [Label.model_validate(json.loads(line)) for line in f.read_text().splitlines()]
    return rows


def test_labels_validate_and_point_at_documents():
    rows = labels()
    assert rows, "no labels yet"
    assert len({r.invoice_id for r in rows}) == len(rows)
    doc = traps()
    for r in rows:
        assert (ROOT / r.path).is_file(), r.path
        t = doc["traps"][r.trap] if r.trap else doc["routine"]
        assert r.gold_decision == Decision(t["decision"]), r.invoice_id
        assert list(r.gold_rules) == t["rules"] and r.gold_security == t["security"], r.invoice_id


def test_the_month_follows_the_plan_table():
    rows = [r for r in labels() if r.split == Split.SHOWCASE]
    assert [r.invoice_id for r in rows] == [f"OCT-{i:02d}" for i in range(1, 31)]
    assert [r.received_at for r in rows] == sorted(r.received_at for r in rows)
    assert Counter(r.trap for r in rows) == {
        None: 16,
        "duplicate_number": 1,
        "duplicate_fiscal_id": 1,
        "new_beneficiary": 2,
        "off_contract_amount": 1,
        "off_contract_scope": 1,
        "over_threshold": 2,
        "insufficient_budget": 2,
        "near_threshold": 1,
        "due_past_grace": 1,
        "words_unparseable": 1,
        "currency_mismatch": 1,
    }
    assert {r.channel.value for r in rows} == {"pdf", "image", "email", "chat"}
    for r in rows:
        if r.path.endswith((".eml", ".txt")):
            text = (ROOT / r.path).read_text(encoding="utf-8")
            assert "(empresa ficticia)" in text or "(fictitious company)" in text, r.path


def test_the_generated_set_follows_the_plan_mix():
    rows = [r for r in labels() if r.split == Split.GENERATED]
    assert len(rows) == 120 and sum(r.trap is None for r in rows) == 72
    assert Counter(r.language.value for r in rows) == {"es": 72, "en": 48}
    assert Counter(r.channel.value for r in rows) == {
        "pdf": 72,
        "image": 12,
        "email": 18,
        "chat": 18,
    }
    generated = {k for k, t in traps()["traps"].items() if "generated" in t["splits"]}
    assert {r.trap for r in rows if r.trap} == generated
    # Episodes (GEN-<episode>-<n>) run as their own batch: numbered from 1, in received order.
    episodes: dict[str, list[Label]] = {}
    for r in rows:
        episodes.setdefault(r.invoice_id.rsplit("-", 1)[0], []).append(r)
    for key, ep in episodes.items():
        assert [r.invoice_id for r in ep] == [f"{key}-{n}" for n in range(1, len(ep) + 1)]
        assert [r.received_at for r in ep] == sorted(r.received_at for r in ep), key
        assert all(r.trap is None for r in ep[:-1]), key  # priors are routine


def test_the_attacks_cover_every_attack_type():
    rows = [r for r in labels() if r.split == Split.ATTACK]
    assert len(rows) == 25
    attacks = {k for k, t in traps()["traps"].items() if "attack" in t["splits"]}
    assert Counter(r.trap for r in rows) == {None: 2} | dict.fromkeys(attacks, 1)
    # The two routine rows open the split-pair and second-in-period episodes.
    assert {r.invoice_id for r in rows if r.trap is None} == {"ATK-15-1", "ATK-16-1"}
    for r in rows:
        if r.trap in {"split_pair", "second_in_period"}:
            assert r.invoice_id.endswith("-2"), r.invoice_id


def test_judge_fixtures_agree_with_the_labels():
    gold = {r.invoice_id: r for r in labels()}
    files = sorted((ROOT / "tests/judge/fixtures").glob("*.yaml"))
    tests = [yaml.safe_load(f.read_text()) for f in files]
    assert [t["test"] for t in tests] == list(range(1, 22))

    def entries(node):
        if isinstance(node, dict):
            if "invoice_id" in node and "decision" in node and "path" in node:
                yield node
            for v in node.values():
                yield from entries(v)
        elif isinstance(node, list):
            for v in node:
                yield from entries(v)

    for t in tests:
        for e in entries(t["expected"]):
            r = gold[e["invoice_id"]]
            assert e["path"] == r.path and Decision(e["decision"]) == r.gold_decision, e
            assert e.get("rules", []) == list(r.gold_rules), e
