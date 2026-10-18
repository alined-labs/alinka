"""The decision core: precedence, batch order, approvals and rejections."""

from datetime import UTC, datetime

import pytest

from alinka.decide import core
from alinka.decide.core import ApprovalRefused, Session, approve, batch, decide, reject
from alinka.decide.ledger import MemoryLedger, Status
from alinka.types import RULE_IDS, Decision, Outcome


@pytest.fixture
def session(world, cfg):
    return Session("test", world, cfg, MemoryLedger())


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def test_routine_pays_to_the_listed_account(world, cfg, ledger, make_facts):
    v = decide(make_facts(printed={"bank_account": None}), world, ledger, cfg)
    assert v.decision == Decision.PAY and v.determining_rule is None
    assert [r.rule for r in v.results] == list(RULE_IDS)
    assert v.payment.account_masked == "Demo Federal Bank · ABA DEMO-•••• · Acct DEMO-••••-0010"


def test_hold_beats_escalate_and_alerts_are_kept(world, cfg, ledger, make_facts):
    f = make_facts(
        computed={"total_minor": 600000, "words_minor": 600000},
        flags={"hidden_content": ("p1: opacity 0",)},
    )
    v = decide(f, world, ledger, cfg)
    assert v.decision == Decision.HOLD and v.determining_rule == "R04"
    assert v.alerts == ("R11",)
    fired = {r.rule for r in v.results if r.outcome != Outcome.PASS}
    assert {"R04", "R05", "R06", "R11", "R13"} <= fired


def test_security_alert_determines_an_escalation(world, cfg, ledger, make_facts):
    tight = cfg.model_copy(update={"approval_threshold_usd": 1100})
    v = decide(make_facts(flags={"html_text_mismatch": True}), world, ledger, tight)
    assert (v.decision, v.determining_rule, v.alerts) == (Decision.ESCALATE, "R11", ("R11",))
    assert v.results[5].outcome == Outcome.ESCALATE  # R06 fired too


def test_a_crashing_rule_escalates(world, cfg, ledger, monkeypatch, make_facts):
    def boom(*_):
        raise RuntimeError("bad")

    monkeypatch.setitem(core.RULES, "R07", boom)
    v = decide(make_facts(), world, ledger, cfg)
    assert (v.decision, v.determining_rule) == (Decision.ESCALATE, "R07")
    assert v.results[6].message_key == "R07.error" and not v.results[6].approvable


def test_a_crash_outside_the_rules_escalates(world, cfg, ledger, monkeypatch, make_facts):
    monkeypatch.setattr(core, "combine", lambda *_: 1 / 0)
    assert decide(make_facts(), world, ledger, cfg).decision == Decision.ESCALATE


def test_extraction_error_never_pays(world, cfg, ledger, make_facts):
    v = decide(make_facts(flags={"extraction_error": "truncated"}), world, ledger, cfg)
    assert v.decision == Decision.ESCALATE


def test_batch_runs_in_received_order_and_catches_the_duplicate(session, make_facts):
    first = make_facts("OCT-01", received=at(1))
    again = make_facts("OCT-09", received=at(9), printed={"bank_account": None})
    records = batch(session, [again, first])
    assert [r.invoice_id for r in records] == ["OCT-01", "OCT-09"]
    assert [r.decision for r in records] == [Decision.PAY, Decision.HOLD]
    assert records[1].determining_rule == "R03"
    assert records[1].prev_hash == records[0].hash and records[0].seq == 1
    assert [e.status for e in session.ledger.entries()] == [Status.PAID]


@pytest.fixture
def over_threshold(make_facts):
    return lambda invoice_id="OCT-03": make_facts(
        invoice_id,
        printed={"service_text": "Cloud hosting"},
        computed={"total_minor": 129000, "words_minor": 129000},
    )


def test_escalation_is_pending_until_approved(session, cfg, over_threshold):
    tight = cfg.model_copy(update={"approval_threshold_usd": 1200})
    session.cfg = tight
    (rec,) = batch(session, [over_threshold()])
    assert rec.decision == Decision.ESCALATE and rec.determining_rule == "R06"
    assert session.ledger.entries()[0].status == Status.PENDING
    with pytest.raises(ApprovalRefused):
        approve(session, rec, "   ")
    paid = approve(session, rec, "Mariana Gómez Salcedo (CFO)", at=at(17))
    assert paid.decision == Decision.PAY and paid.human.approver.startswith("Mariana")
    assert paid.payment.beneficiary_id == "BEN-10" and paid.prev_hash == rec.hash
    assert session.ledger.entries()[0].status == Status.APPROVED
    with pytest.raises(ApprovalRefused):
        approve(session, paid, "Otra persona")
    with pytest.raises(ApprovalRefused):
        approve(session, rec, "Otra persona")  # superseded


def test_late_approval_cannot_break_the_monthly_cap(session, cfg, entry, over_threshold):
    session.cfg = cfg.model_copy(update={"approval_threshold_usd": 1200})
    (rec,) = batch(session, [over_threshold()])
    for i in range(4):
        session.ledger.add(entry(f"P{i}", usd_minor=990_000, cost_center=None, beneficiary_id=None))
    held = approve(session, rec, "Samuel Okafor Price (COO)")
    assert (held.decision, held.determining_rule) == (Decision.HOLD, "R07")
    assert session.ledger.entries()[0].status == Status.REJECTED


@pytest.mark.parametrize(
    "printed",
    [
        {"beneficiary_name": "Cobalt Ridge Hostinq, Inc.", "beneficiary_tax_id": "DEMO-1"},
        {"bank_account": "Acct DEMO-9999-0000"},
    ],
)
def test_r01_and_r12_can_never_be_approved(session, printed, make_facts):
    (rec,) = batch(session, [make_facts(printed=printed)])
    assert rec.decision == Decision.ESCALATE
    with pytest.raises(ApprovalRefused):
        approve(session, rec, "Mariana Gómez Salcedo (CFO)")


def test_only_escalations_can_be_approved(session, make_facts):
    (rec,) = batch(session, [make_facts()])
    assert rec.decision == Decision.PAY
    with pytest.raises(ApprovalRefused):
        approve(session, rec, "Mariana")


def test_reject_records_the_person_and_frees_the_ledger(session, make_facts):
    (rec,) = batch(
        session,
        [make_facts(printed={"beneficiary_name": "Nadie S.A.", "beneficiary_tax_id": "DEMO-0"})],
    )
    out = reject(session, rec, "Samuel Okafor Price (COO)", note="No lo conocemos")
    assert out.decision == Decision.HOLD and out.human.action == "reject"
    assert session.ledger.entries()[0].status == Status.REJECTED
