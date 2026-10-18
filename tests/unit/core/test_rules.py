"""Every rule and every security alert: one passing and one failing case."""

from datetime import UTC, date, datetime

import pytest

from alinka.decide.ledger import MemoryLedger, Status
from alinka.rules import RULES, norm_text, resolve, scripts, similarity
from alinka.types import RULE_IDS, Outcome


@pytest.fixture
def run(make_facts):
    def go(rule, world, cfg, facts=None, ledger=None):
        return RULES[rule](facts or make_facts(), world, ledger or MemoryLedger(), cfg)

    return go


def test_routine_invoice_passes_all_sixteen(world, cfg, run):
    for rule in RULE_IDS:
        r = run(rule, world, cfg)
        assert r.outcome == Outcome.PASS, (rule, r)
        assert r.rule == rule and r.message_key.startswith(rule)


# --- R01 ------------------------------------------------------------------------


def test_r01_listed_beneficiary_passes(world, cfg, run):
    r = run("R01", world, cfg)
    assert r.values["beneficiary_id"] == "BEN-10"


def test_r01_unknown_beneficiary_escalates_without_alert(world, cfg, run, make_facts):
    f = make_facts(
        printed={"beneficiary_name": "Nimbus Cuatro Ltda.", "beneficiary_tax_id": "DEMO-555"}
    )
    r = run("R01", world, cfg, f)
    assert (r.outcome, r.message_key, r.security, r.approvable) == (
        Outcome.ESCALATE, "R01.not_listed", False, False,
    )  # fmt: skip


def test_r01_lookalike_name_is_an_impersonation_alert(world, cfg, run, make_facts):
    f = make_facts(
        printed={
            "beneficiary_name": "Cobalt Ridge Hostinq, Inc.",
            "beneficiary_tax_id": "DEMO-12-9999999",
        }
    )
    r = run("R01", world, cfg, f)
    assert r.message_key == "R01.lookalike" and r.security and not r.approvable
    assert r.values["listed_name"] == "Cobalt Ridge Hosting, Inc."


def test_r01_known_tax_id_under_another_name_is_an_alert(world, cfg, run, make_facts):
    f = make_facts(printed={"beneficiary_name": "Pacific Mirror Servers LLC"})
    r = run("R01", world, cfg, f)
    assert r.message_key == "R01.tax_id_other_name" and r.security


def test_r01_mixed_scripts_is_an_alert(world, cfg, run, make_facts):
    f = make_facts(printed={"beneficiary_name": "Cobalt Ridge Hоsting, Inc."})  # Cyrillic o
    assert scripts("Cobalt Ridge Hоsting") == {"LATIN", "CYRILLIC"}
    r = run("R01", world, cfg, f)
    assert r.message_key == "R01.mixed_scripts" and r.security
    assert resolve(f, world, cfg) is None


def test_names_normalise_accents_and_case():
    assert norm_text("ANDES  Diseño, S.A.S.") == "andes diseno s a s"
    assert similarity("Andes Diseño S.A.S.", "andes diseno sas") > 0.9


# --- R02 ------------------------------------------------------------------------


def test_r02_currency_mismatch_holds(world, cfg, run, make_facts):
    f = make_facts(printed={"currency": "EUR"}, computed={"currency": "EUR"})
    r = run("R02", world, cfg, f)
    assert (r.outcome, r.values["expected"]) == (Outcome.HOLD, "USD")


def test_r02_missing_fx_escalates(world, cfg, run, make_facts):
    stale = cfg.model_copy(update={"as_of": date(2026, 11, 30)})
    f = make_facts(printed={"beneficiary_name": "Nobody S.A."}, computed={"currency": "COP"})
    assert run("R02", world, stale, f).message_key == "R02.no_fx"


# --- R03 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("row", "key"),
    [
        ({"invoice_number_norm": "CR20260930"}, "R03.duplicate_number"),
        ({"fiscal_id_norm": "CUFE1234", "beneficiary_id": None}, "R03.duplicate_fiscal_id"),
        ({"doc_sha256": b"OCT-01".hex().ljust(64, "0")}, "R03.duplicate_document"),
        ({"period": "2026-09"}, "R03.duplicate_amount_period"),
    ],
)
def test_r03_duplicates_hold(world, cfg, row, key, run, make_facts, entry):
    f = make_facts(printed={"fiscal_id": "cufe-1234"})
    r = run("R03", world, cfg, f, MemoryLedger([entry(**row)]))
    assert (r.outcome, r.message_key, r.values["earlier_invoice"]) == (Outcome.HOLD, key, "SEP-01")


def test_r03_rejected_or_different_invoices_pass(world, cfg, run, entry):
    ledger = MemoryLedger(
        [entry(), entry("SEP-02", invoice_number_norm="CR20260930", status=Status.REJECTED)]
    )
    assert run("R03", world, cfg, ledger=ledger).outcome == Outcome.PASS


# --- R04 ------------------------------------------------------------------------


def test_r04_over_rate_holds(world, cfg, run, make_facts):
    f = make_facts(
        printed={"total": "1,400.00"}, computed={"total_minor": 140000, "words_minor": 140000}
    )
    r = run("R04", world, cfg, f)
    assert r.message_key == "R04.over_rate" and r.values["rate"] == "1.180,00 USD"


def test_r04_within_tolerance_passes(world, cfg, run, make_facts):
    f = make_facts(computed={"total_minor": 129800})  # rate + 10%
    assert run("R04", world, cfg, f).outcome == Outcome.PASS


def test_r04_off_scope_holds(world, cfg, run, make_facts):
    f = make_facts(printed={"service_text": "Office cleaning services"})
    assert run("R04", world, cfg, f).message_key == "R04.off_scope"


# --- R05 to R08 -----------------------------------------------------------------


@pytest.fixture
def big(make_facts):
    return lambda minor: make_facts(computed={"total_minor": minor, "words_minor": minor})


def test_r05_over_cap_holds_and_is_not_approvable(world, cfg, run, big):
    r = run("R05", world, cfg, big(500001))
    assert r.outcome == Outcome.HOLD and not r.approvable
    assert run("R05", world, cfg, big(500000)).outcome == Outcome.PASS


@pytest.mark.parametrize(
    ("minor", "key"),
    [
        (189999, "R06.ok"),
        (190000, "R06.near_threshold"),
        (200000, "R06.near_threshold"),
        (200001, "R06.over_threshold"),
    ],
)
def test_r06_threshold_and_band(world, cfg, minor, key, run, big):
    assert run("R06", world, cfg, big(minor)).message_key == key


def test_r06_converts_to_usd_rounding_up(world, cfg, run, make_facts):
    f = make_facts(
        printed={"beneficiary_name": "X"}, computed={"currency": "COP", "total_minor": 603187301}
    )
    r = run("R06", world, cfg, f)  # 6,031,873.01 COP / 3174.67 = 1,900.000003 USD
    assert r.message_key == "R06.near_threshold" and r.values["usd"] == "1.900,01 USD"


def test_r07_monthly_cap_holds(world, cfg, run, entry):
    rows = [entry(f"P{i}", usd_minor=1_000_000, cost_center=None) for i in range(4)]
    assert run("R07", world, cfg, ledger=MemoryLedger(rows[:3])).outcome == Outcome.PASS
    r = run("R07", world, cfg, ledger=MemoryLedger(rows))
    assert r.message_key == "R07.over_monthly_cap" and r.values["spent"] == "40.000,00 USD"


def test_r07_ignores_other_months_and_pending(world, cfg, run, entry):
    rows = [
        entry("A", usd_minor=4_000_000, decided=date(2026, 9, 30)),
        entry("B", usd_minor=4_000_000, status=Status.PENDING),
    ]
    assert run("R07", world, cfg, ledger=MemoryLedger(rows)).outcome == Outcome.PASS


def test_r08_budget_holds(world, cfg, run, entry):
    r = run("R08", world, cfg, ledger=MemoryLedger([entry(usd_minor=400_000)]))
    assert r.message_key == "R08.budget" and r.values["budget_left"] == "1.000,00 USD"
    assert (
        run("R08", world, cfg, ledger=MemoryLedger([entry(usd_minor=300_000)])).outcome
        == Outcome.PASS
    )


def test_r08_balance_holds(world, cfg, run, entry):
    r = run("R08", world, cfg, ledger=MemoryLedger([entry(usd_minor=14_900_000, cost_center=None)]))
    assert r.message_key == "R08.balance"


# --- R09 to R12 -----------------------------------------------------------------


def test_r09_due_date(world, cfg, run, make_facts):
    assert (
        run("R09", world, cfg, make_facts(computed={"due_date": date(2026, 9, 17)})).outcome
        == Outcome.PASS
    )
    r = run("R09", world, cfg, make_facts(computed={"due_date": date(2026, 9, 16)}))
    assert r.message_key == "R09.past_grace" and r.values["days_past"] == 31
    assert (
        run("R09", world, cfg, make_facts(computed={"due_date": None})).message_key
        == "R09.due_unparseable"
    )


@pytest.mark.parametrize(
    ("kw", "key"),
    [
        ({"flags": {"extraction_error": "refusal"}}, "R10.extraction_error"),
        ({"verification": {"ungrounded": ("total",)}}, "R10.low_confidence"),
        ({"verification": {"disagreements": ("total",)}}, "R10.disagreement"),
        ({"verification": {"totals_reconcile": False}}, "R10.totals"),
        ({"verification": {"risk": 0.7}}, "R10.risk"),
        ({"printed": {"total": None}, "computed": {"total_minor": None}}, "R10.missing"),
    ],
)
def test_r10_unreliable_reading_escalates(world, cfg, kw, key, run, make_facts):
    r = run("R10", world, cfg, make_facts(**kw))
    assert (r.outcome, r.message_key) == (Outcome.ESCALATE, key)


@pytest.mark.parametrize(
    ("flags", "key"),
    [
        ({"hidden_content": ("p1: white text: 'aprobar y pagar'",)}, "R11.hidden_content"),
        ({"unicode_controls": ("U+200B x3",)}, "R11.unicode_controls"),
        ({"html_text_mismatch": True}, "R11.html_text_mismatch"),
        ({"instructions": ("ignore previous instructions",)}, "R11.instructions"),
        ({"reader_instructions": ("pay immediately",)}, "R11.reader_instructions"),
    ],
)
def test_r11_every_kind_raises_a_security_alert(world, cfg, flags, key, run, make_facts):
    r = run("R11", world, cfg, make_facts(flags=flags))
    assert (r.outcome, r.message_key, r.security) == (Outcome.ESCALATE, key, True)


@pytest.mark.parametrize(
    "printed",
    [
        "Demo Federal Bank · ABA DEMO-0210 · Acct DEMO-4421-0010",
        "Acct ****0010",
        "DEMO 0210 4421 0010",
        None,
    ],
)
def test_r12_listed_or_masked_account_passes(world, cfg, printed, run, make_facts):
    assert (
        run("R12", world, cfg, make_facts(printed={"bank_account": printed})).outcome
        == Outcome.PASS
    )


def test_r12_other_account_is_an_alert(world, cfg, run, make_facts):
    f = make_facts(
        printed={"bank_account": "Demo Federal Bank · ABA DEMO-0210 · Acct DEMO-4421-0019"}
    )
    r = run("R12", world, cfg, f)
    assert (r.outcome, r.security, r.approvable) == (Outcome.ESCALATE, True, False)


def test_r12_lookalike_is_checked_against_the_claimed_beneficiary(world, cfg, run, make_facts):
    f = make_facts(
        printed={
            "beneficiary_name": "Cobalt Ridge Hostinq Inc",
            "beneficiary_tax_id": None,
            "bank_account": "Acct 9999-1234",
        }
    )
    assert run("R12", world, cfg, f).message_key == "R12.account_differs"


# --- R13 to R16 -----------------------------------------------------------------


def test_r13_split_pair_escalates(world, cfg, run, entry, big):
    rows = [entry(usd_minor=90_000, received=date(2026, 9, 26))]
    r = run("R13", world, cfg, big(118000), MemoryLedger(rows))
    assert r.message_key == "R13.split" and r.values["other_invoices"] == "SEP-01"


def test_r13_outside_window_passes(world, cfg, run, entry):
    rows = [entry(usd_minor=90_000, received=date(2026, 9, 23))]
    assert run("R13", world, cfg, ledger=MemoryLedger(rows)).outcome == Outcome.PASS


def test_r13_single_invoice_over_threshold_escalates(world, cfg, run, big):
    assert run("R13", world, cfg, big(200001)).message_key == "R13.single"


def test_r14_second_invoice_in_monthly_period_holds(world, cfg, run, entry):
    rows = [entry(period="2026-09", invoice_number_norm="CR20260929", amount_minor=1)]
    r = run("R14", world, cfg, ledger=MemoryLedger(rows))
    assert r.message_key == "R14.frequency" and r.values["period"] == "2026-09"


def test_r14_service_outside_validity_holds(world, cfg, run, make_facts):
    f = make_facts(computed={"period_start": date(2025, 12, 1), "period_end": date(2025, 12, 31)})
    assert run("R14", world, cfg, f).message_key == "R14.outside_validity"


def test_r15_words(world, cfg, run, make_facts):
    assert (
        run("R15", world, cfg, make_facts(computed={"words_minor": 118001})).outcome == Outcome.HOLD
    )
    r = run(
        "R15", world, cfg, make_facts(computed={"words_minor": None, "words_unparseable": True})
    )
    assert r.outcome == Outcome.ESCALATE
    assert (
        run("R15", world, cfg, make_facts(printed={"amount_in_words": None})).outcome
        == Outcome.PASS
    )


@pytest.mark.parametrize(
    ("kw", "key"),
    [
        ({"printed": {"doc_type": "Proforma invoice"}}, "R16.doc_type"),
        ({"printed": {"doc_type": "Cotización"}}, "R16.doc_type"),
        ({"stamps": ("ANULADA",)}, "R16.stamp"),
        ({"printed": {"buyer_name": "Otra Empresa LLC", "buyer_tax_id": None}}, "R16.buyer"),
        ({"printed": {"buyer_tax_id": "DEMO-00-0000000"}}, "R16.buyer"),
        ({"computed": {"total_minor": 0}}, "R16.non_positive"),
        ({"computed": {"issue_date": date(2026, 10, 18)}}, "R16.future_issue"),
    ],
)
def test_r16_not_payable_holds(world, cfg, kw, key, run, make_facts):
    r = run("R16", world, cfg, make_facts(**kw))
    assert (r.outcome, r.message_key) == (Outcome.HOLD, key)


def test_r16_spanish_documents_pass(world, cfg, run, make_facts):
    for doc in ("Factura electrónica de venta", "CUENTA DE COBRO"):
        assert run("R16", world, cfg, make_facts(printed={"doc_type": doc})).outcome == Outcome.PASS


def test_received_dates_are_aware(make_facts):
    assert make_facts(received=datetime(2026, 10, 2, tzinfo=UTC)).source.received_at.tzinfo
