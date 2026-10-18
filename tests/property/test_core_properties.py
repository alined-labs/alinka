"""Safety properties of the decision core, over generated invoices and ledgers."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from hypothesis import event, given
from hypothesis import strategies as st

from alinka.decide.core import ApprovalRefused, Session, approve, batch, decide, mask_account
from alinka.decide.ledger import ACTIVE, SPENT, MemoryLedger, Status
from alinka.rules import resolve
from alinka.types import NEVER_APPROVABLE, Decision, Outcome
from alinka.world import load_rules, load_world

WORLD, CFG = load_world(), load_rules()
BENS = WORLD.beneficiaries
CAUTION = {Decision.PAY: 0, Decision.ESCALATE: 1, Decision.HOLD: 2}
START = datetime(2026, 10, 1, 9, tzinfo=UTC)


def homoglyph(name: str) -> str:
    return name.replace("o", "о", 1).replace("a", "а", 1)  # Cyrillic look-alikes


def mostly(good, *bad):
    """The clean value most of the time, so PAY and approvals are reached often."""
    return st.sampled_from([good] * (3 * len(bad) + 1) + list(bad))


@st.composite
def invoice(draw, ben=None) -> dict[str, Any]:
    """Overrides for make_facts: mostly plausible invoices, with every kind of fault mixed in."""
    ben = ben or draw(st.sampled_from(BENS))
    ctr = ben.contract
    name = draw(mostly(ben.name, homoglyph(ben.name), ben.name[:-1] + "q", "Nadie S.A."))
    tax = draw(mostly(ben.tax_id, "DEMO-0000", None))
    cur = draw(mostly(ben.currency, "USD", "EUR", "COP", "ARS"))
    clean = draw(mostly(True, False))
    total = draw(st.integers(1, ctr.rate_minor) if clean else st.integers(-10, 3 * ctr.rate_minor))
    words = draw(mostly("same", "differ", "none", "garbled"))
    account = draw(mostly(ben.account_on_file, None, "Acct DEMO-9999-0001"))
    received = START + timedelta(hours=draw(st.integers(0, 16 * 24)))
    due = date(2026, 10, 17) + timedelta(days=draw(st.integers(-29 if clean else -60, 30)))
    computed = {
        "currency": cur, "total_minor": total, "due_date": due, "invoice_number_norm": None,
        "issue_date": received.date() - timedelta(days=draw(st.integers(0, 3))),
        "words_minor": {"same": total, "differ": total + 100, "none": None, "garbled": None}[words],
        "words_unparseable": words == "garbled",
    }  # fmt: skip
    printed = {
        "beneficiary_name": name, "beneficiary_tax_id": tax, "currency": cur, "total": str(total),
        "bank_account": account, "service_text": draw(mostly(ctr.scope_en[0], ctr.scope_es[0], "Limpieza")),
        "invoice_number": f"N-{draw(st.integers(1, 10**6))}",
        "doc_type": draw(mostly("Factura", "Cuenta de cobro", "Proforma")),
        "amount_in_words": None if words == "none" else "palabras",
    }  # fmt: skip
    flags = draw(
        mostly({}, {"hidden_content": ("p1: opacity 0",)}, {"extraction_error": "timeout"})
    )
    verification = {
        "risk": draw(st.floats(0, 0.5) if clean else st.floats(0, 1)),
        "disagreements": draw(mostly((), ("total",))),
    }
    return {
        "invoice_id": f"GEN-{draw(st.integers(1, 10**6)):07d}", "received": received,
        "printed": printed, "computed": computed, "flags": flags, "verification": verification,
    }  # fmt: skip


@st.composite
def prior_ledger(draw):
    rows = []
    for i in range(draw(st.integers(0, 6))):
        ben = draw(st.sampled_from(BENS))
        usd = draw(st.integers(1, 400_000))
        rows.append(
            dict(
                invoice_id=f"PRIOR-{i}", beneficiary_id=ben.id, invoice_number_norm=f"P{i}",
                amount_minor=usd, currency="USD", usd_minor=usd, period="2026-10",
                received=date(2026, 10, draw(st.integers(1, 16))), cost_center=ben.contract.cost_center,
                status=draw(st.sampled_from(list(Status))),
            )
        )  # fmt: skip
    return rows


# 1. PAY implies every rule passed ------------------------------------------------


@given(inv=invoice(), rows=prior_ledger())
def test_pay_implies_every_rule_passed(make_facts, entry, inv, rows):
    facts = make_facts(**inv)
    v = decide(facts, WORLD, MemoryLedger(entry(**r) for r in rows), CFG)
    event(v.decision.value)
    if v.decision == Decision.PAY:
        assert len(v.results) == 16 and all(r.outcome == Outcome.PASS for r in v.results)
        assert facts.flags.extraction_error is None and v.alerts == ()


# 2. The verifier can only make a decision more cautious --------------------------


@given(inv=invoice(), risk=st.floats(0, 1), bad=st.booleans(), grounded=st.booleans())
def test_verifier_only_adds_caution(make_facts, inv, risk, bad, grounded):
    clean = make_facts(**{**inv, "verification": {"risk": 0.0}})
    worse = make_facts(
        **{**inv, "verification": {
            "risk": risk, "disagreements": ("total",) if bad else (),
            "ungrounded": () if grounded else ("due_date",), "totals_reconcile": not bad,
        }}
    )  # fmt: skip
    before = decide(clean, WORLD, MemoryLedger(), CFG).decision
    after = decide(worse, WORLD, MemoryLedger(), CFG).decision
    assert CAUTION[after] >= CAUTION[before]


# 3. The payout account always equals the one on the list ------------------------


@given(inv=invoice())
def test_payout_account_comes_from_the_list(make_facts, inv):
    facts = make_facts(**inv)
    v = decide(facts, WORLD, MemoryLedger(), CFG)
    if v.decision == Decision.PAY:
        ben = WORLD.beneficiary(v.payment.beneficiary_id)
        assert ben is not None and ben == resolve(facts, WORLD, CFG)
        assert v.payment.account_masked == mask_account(ben.account_on_file)


# 4. Approvals never pass R01 or R12 and never break a cap ------------------------


@given(invs=st.lists(invoice(), min_size=1, max_size=6), rows=prior_ledger())
def test_approvals_respect_r01_r12_and_caps(make_facts, entry, invs, rows):
    session = Session("prop", WORLD, CFG, MemoryLedger(entry(**r) for r in rows))
    for rec in batch(session, [make_facts(**i) for i in invs]):
        if rec.decision != Decision.ESCALATE:
            continue
        try:
            out = approve(session, rec, "Mariana Gómez Salcedo (CFO)")
        except ApprovalRefused:
            event("approval refused")
            continue
        event(f"approval -> {out.decision.value}")
        fired = {r.rule for r in rec.results if r.outcome != Outcome.PASS}
        assert out.decision != Decision.PAY or not fired & NEVER_APPROVABLE
        if out.decision == Decision.PAY:
            spent = [e for e in session.ledger.entries() if e.status in SPENT]
            assert out.payment.usd_minor <= CFG.per_payment_cap_usd * 100
            assert (
                sum(e.usd_minor for e in spent if e.decided.month == 10)
                <= CFG.monthly_cap_usd * 100
            )
            assert sum(e.usd_minor for e in spent) <= WORLD.company.balance_usd_minor
            for cc in WORLD.company.cost_centers:
                used = sum(e.usd_minor for e in spent if e.cost_center == cc.id)
                assert used <= cc.budget_usd_minor or not any(
                    e.invoice_id == rec.invoice_id and e.cost_center == cc.id for e in spent
                )


# 5. A split pair over 2,000 USD within 7 days escalates -------------------------

PER_DELIVERY = [b for b in BENS if b.contract.frequency == "per_delivery" and b.currency == "USD"]


@given(
    ben=st.sampled_from(PER_DELIVERY),
    a=st.integers(1, 199_999),
    b=st.integers(1, 189_999),
    days=st.integers(0, 7),
    status=st.sampled_from(sorted(ACTIVE)),
)
def test_split_pair_escalates(make_facts, entry, ben, a, b, days, status):
    if a + b <= 200_000:
        b = 200_001 - a
    if b >= 190_000:  # keep the second under the R06 band so only R13 speaks
        return
    first = entry(
        beneficiary_id=ben.id,
        usd_minor=a,
        amount_minor=a,
        received=date(2026, 10, 1),
        status=status,
    )
    second = make_facts(
        "SPLIT-2", received=datetime(2026, 10, 1 + days, 12, tzinfo=UTC),
        printed={"beneficiary_name": ben.name, "beneficiary_tax_id": ben.tax_id, "bank_account": None, "service_text": ben.contract.scope_en[0]},
        computed={"total_minor": b, "words_minor": b, "invoice_number_norm": "SPLIT2"},
    )  # fmt: skip
    v = decide(second, WORLD, MemoryLedger([first]), CFG)
    r13 = v.results[12]
    assert r13.outcome == Outcome.ESCALATE and v.decision != Decision.PAY


# 6. A second invoice in a monthly period holds ----------------------------------

MONTHLY = [b for b in BENS if b.contract.frequency == "monthly"]


@given(ben=st.sampled_from(MONTHLY), day=st.integers(1, 28), status=st.sampled_from(sorted(ACTIVE)))
def test_second_invoice_in_a_monthly_period_holds(make_facts, entry, ben, day, status):
    first = entry(
        beneficiary_id=ben.id, period="2026-09", invoice_number_norm="FIRST", status=status
    )
    second = make_facts(
        "MONTHLY-2",
        printed={"beneficiary_name": ben.name, "beneficiary_tax_id": ben.tax_id},
        computed={
            "issue_date": date(2026, 9, day),
            "invoice_number_norm": "SECOND",
            "period_start": None,
        },
    )
    v = decide(second, WORLD, MemoryLedger([first]), CFG)
    assert v.decision == Decision.HOLD and v.results[13].outcome == Outcome.HOLD


# 7. Words that differ from the digits hold ---------------------------------------


@given(inv=invoice(), delta=st.integers(1, 10**8))
def test_words_that_differ_hold(make_facts, inv, delta):
    total = inv["computed"]["total_minor"]
    inv["computed"] = {**inv["computed"], "words_minor": total + delta, "words_unparseable": False}
    inv["printed"] = {**inv["printed"], "amount_in_words": "otra cifra"}
    v = decide(make_facts(**inv), WORLD, MemoryLedger(), CFG)
    assert v.decision == Decision.HOLD and v.results[14].outcome == Outcome.HOLD
