"""The API judge tests of PLAN section 9, read from Lane B's tests/judge/fixtures/.

Each fixture names its input (a split, or episodes of a split) and the expected outcome,
written from the trap's intent. The facts are Lane C's recorded readings in data/runs/
<split>/; each episode is decided as its own batch, the month as one batch of 30.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
import yaml

from alinka.api import load_run, runs
from alinka.types import RULE_NAMES_ES

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "judge" / "fixtures"
CSV_COLUMNS = {
    "invoice": "factura", "beneficiary": "beneficiario", "amount": "monto", "currency": "moneda",
    "usd": "usd", "decision": "decision", "rules": "reglas", "reason": "motivo",
    "approver": "aprobador", "time": "fecha",
}  # fmt: skip

# Known disagreements between a recorded reading and the trap's intent, each more cautious
# than gold. strict=True: once the reading is fixed the case passes and the entry must go.
KNOWN: dict[str, str] = {}


def fixture(n: int) -> dict:
    (path,) = FIXTURES.glob(f"{n:02d}-*.yaml")
    return yaml.safe_load(path.read_text())


def batches(spec: dict) -> list[tuple[str, list]]:
    """(name, facts) per batch: one per episode, else the whole split in received order."""
    inp = spec["input"]
    facts = runs.load_facts(inp["split"])
    if "episodes" not in inp:
        return [(inp["split"], list(facts))]
    out = []
    for ep in inp["episodes"]:
        chosen = [f for f in facts if f.source.invoice_id.startswith(f"{ep}-")]
        assert chosen, f"{ep} is not in data/runs/{inp['split']}"
        out.append((ep.lower(), chosen))
    return out


@pytest.fixture
def load(client, tmp_path, monkeypatch):
    """Load one batch as the canonical run; return the details of its invoices."""
    real = runs.RUNS

    def go(name: str, facts: list) -> dict[str, dict]:
        monkeypatch.setattr(runs, "RUNS", tmp_path)
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / "facts.jsonl").write_text("\n".join(f.model_dump_json() for f in facts))
        runs.load_facts.cache_clear()
        assert load_run.main([name, "--no-migrate"]) == 0
        details = {
            f.source.invoice_id: client.get(
                f"/api/invoices/{f.source.invoice_id}", params={"view": "canonical"}
            ).json()
            for f in facts
        }
        monkeypatch.setattr(runs, "RUNS", real)
        return details

    runs.load_facts.cache_clear()
    yield go
    runs.load_facts.cache_clear()


def decided(load, spec: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, facts in batches(spec):
        out |= load(name, facts)
    return out


def fired(detail: dict) -> set[str]:
    return {r["rule"] for r in detail["rules"] if r["outcome"] != "pass"}


def check(detail: dict, exp: dict) -> None:
    """One expected entry: decision, Spanish state, rules, citations, alerts, excluded facts."""
    card, inv = detail["card"], exp["invoice_id"]
    reason = detail["record"]["reason_es"]
    assert card["state"] == exp["decision"], f"{inv}: {reason}"
    if "state_es" in exp:
        assert card["state_es"] == exp["state_es"]
    if rules := exp.get("rules"):
        assert card["determining_rule"] in rules, f"{inv}: {reason}"
        assert set(rules) <= fired(detail), f"{inv}: fired {sorted(fired(detail))}"
    if "fired_includes" in exp:
        assert exp["fired_includes"] in fired(detail), f"{inv}: {reason}"
    for key in ("cites", "cites_number"):
        if key in exp:
            assert exp[key] in reason, f"{inv} should cite {exp[key]}: {reason}"
    if "reason_contains" in exp:
        assert exp["reason_contains"] in reason, f"{inv}: {reason}"
    if "approvable" in exp:
        assert card["approvable"] is exp["approvable"]
    if exp.get("security_alert"):
        assert set(card["alerts"]) & set(exp.get("rules", card["alerts"])), f"{inv}: {reason}"
        assert reason.startswith("Alerta de seguridad"), f"{inv}: {reason}"
    for text in exp.get("facts_exclude", ()):
        values = " ".join(f["value"] or "" for f in detail["fields"]).lower()
        assert text.lower() not in values, f"{inv}: {text!r} became a fact"


def cases() -> list:
    """One pytest case per expected invoice, so a single disagreement doesn't hide the rest."""
    out = []
    for n in (3, 6, 8, 9, 10, 12, 13, 14, 15, 16):
        for exp in fixture(n)["expected"]:
            inv = exp["invoice_id"]
            marks = [pytest.mark.xfail(reason=KNOWN[inv], strict=True)] if inv in KNOWN else []
            out.append(pytest.param(n, exp, id=f"{n:02d}-{inv}", marks=marks))
    return out


@pytest.mark.parametrize(("n", "exp"), cases())
def test_judge_invoice(load, n, exp):
    check(decided(load, fixture(n))[exp["invoice_id"]], exp)


def test_02_every_card_names_its_rule_and_a_value(client, load):
    spec = fixture(2)
    decided(load, spec)
    board = client.get("/api/board", params={"view": "canonical"}).json()
    cards = {c["invoice_id"]: c for col in board["columns"] for c in col["cards"]}
    assert len(cards) == spec["input"]["invoices"]
    for c in cards.values():
        assert any(ch.isdigit() for ch in c["reason_es"]), c["reason_es"]
        if c["determining_rule"]:
            assert f"({c['determining_rule']})" in c["reason_es"], c["reason_es"]
    for exp in spec["expected"]["non_pay"]:
        c = cards[exp["invoice_id"]]
        if exp["invoice_id"] in KNOWN:  # more cautious than gold, never paid
            assert c["state"] in {"HOLD", "ESCALATE"}, c["reason_es"]
            continue
        assert (c["state"], c["determining_rule"]) == (exp["decision"], exp["rule"]), c["reason_es"]
        assert c["determining_rule_es"] == exp["rule_name_es"] == RULE_NAMES_ES[exp["rule"]]


def test_07_monthly_cap_holds_the_first_invoice_over_it(client, load):
    spec = fixture(7)
    decided(load, spec)
    client.post("/api/run")
    board = client.put("/api/rules", json=spec["setup"]["PUT /api/rules"]).json()["board"]
    cards = {c["invoice_id"]: c for col in board["columns"] for c in col["cards"]}
    for inv in spec["expected"]["pays"]:
        assert cards[inv]["state"] == "PAY", cards[inv]["reason_es"]
    held = spec["expected"]["first_held"]
    c = cards[held["invoice_id"]]
    assert (c["state"], c["state_es"]) == (held["decision"], held["state_es"]), c["reason_es"]
    detail = client.get(f"/api/invoices/{held['invoice_id']}").json()
    assert held["fired_includes"] in fired(detail)


def test_19_csv_lists_every_decision_with_its_reason(client, load):
    spec = fixture(19)
    decided(load, spec)
    text = client.get("/api/log/export.csv", params={"view": "canonical"}).text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == spec["expected"]["rows"]
    assert list(rows[0]) == [CSV_COLUMNS[c] for c in spec["expected"]["columns"]]
    assert all(r["motivo"] and r["decision"] for r in rows)


def test_sandbox_work_never_touches_the_canonical_run(client, load):
    decided(load, fixture(19))  # the month
    canon = client.get("/api/log", params={"view": "canonical"}).json()
    client.post("/api/run")
    client.put("/api/rules", json={"approval_threshold_usd": 1000})
    pending = client.get("/api/board").json()["columns"][2]["cards"]
    for c in [c for c in pending if c["approvable"]][:3]:
        client.post(f"/api/invoices/{c['invoice_id']}/approve", json={"approver": "Ana Demo"})
    client.post("/api/sandbox/reset")
    assert client.get("/api/log", params={"view": "canonical"}).json() == canon
    assert client.get("/api/log/verify", params={"view": "canonical"}).json()["ok"]
