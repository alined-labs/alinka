"""Judge test 2: every reason names its rule in words and cites the values it used."""

import re
from datetime import date

import pytest

from alinka.audit.reasons import NAME_STEMS, headline, reason_es, sentence
from alinka.audit.templates import _text
from alinka.decide.core import Session, approve, batch, reject
from alinka.decide.ledger import MemoryLedger
from alinka.rules import RULES
from alinka.types import RULE_IDS, Decision, HumanAction, Outcome

# Values that are shown in another form (similarity as %, status and frequency in words)
# or are internal bookkeeping rather than something a reader checks.
SHOWN_OTHERWISE = {
    "similarity",
    "earlier_status",
    "frequency",
    "beneficiary_id",
    "kinds",
    "findings",
}


def scenarios(make_facts, entry):
    """Enough invoices and ledgers to reach every rule's failing and passing branches."""
    dup = MemoryLedger([entry(invoice_number_norm="CR20260930")])
    split = MemoryLedger([entry(usd_minor=90_000, received=date(2026, 9, 26), period="2026-08")])
    yield make_facts(), MemoryLedger()
    yield make_facts(printed={"fiscal_id": "C-1"}), dup
    yield make_facts(), MemoryLedger([entry(fiscal_id_norm="C1", beneficiary_id=None)])
    yield (
        make_facts(printed={"fiscal_id": "C-1"}),
        MemoryLedger([entry(fiscal_id_norm="C1", beneficiary_id=None)]),
    )
    yield make_facts(), MemoryLedger([entry(period="2026-09")])
    yield make_facts(), split
    yield make_facts(), MemoryLedger([entry(usd_minor=400_000)])
    yield make_facts(), MemoryLedger([entry(usd_minor=14_900_000, cost_center=None)])
    yield (
        make_facts(),
        MemoryLedger([entry(f"P{i}", usd_minor=1_000_000, cost_center=None) for i in range(4)]),
    )
    yield make_facts(computed={"total_minor": 600_000, "words_minor": 500_000}), MemoryLedger()
    yield (
        make_facts(
            computed={"total_minor": 195_000, "words_minor": None, "words_unparseable": True}
        ),
        MemoryLedger(),
    )
    yield (
        make_facts(
            printed={"currency": "EUR", "service_text": "Limpieza"}, computed={"currency": "EUR"}
        ),
        MemoryLedger(),
    )
    yield (
        make_facts(
            printed={
                "beneficiary_name": "Cobalt Ridge Hostinq, Inc.",
                "beneficiary_tax_id": "DEMO-1",
                "bank_account": "Acct 9999-1111",
            }
        ),
        MemoryLedger(),
    )
    yield make_facts(printed={"beneficiary_name": "Otra Cosa LLC"}), MemoryLedger()
    yield make_facts(printed={"beneficiary_name": "Cobalt Ridge Hоsting, Inc."}), MemoryLedger()
    yield (
        make_facts(printed={"beneficiary_name": "Nadie S.A.", "beneficiary_tax_id": "DEMO-0"}),
        MemoryLedger(),
    )
    yield (
        make_facts(
            computed={"due_date": date(2026, 9, 1), "period_start": date(2025, 1, 1)},
            printed={"doc_type": "Proforma"},
        ),
        MemoryLedger(),
    )
    yield make_facts(computed={"due_date": None}, stamps=("ANULADA",)), MemoryLedger()
    yield make_facts(printed={"buyer_name": "Otra Empresa LLC"}), MemoryLedger()
    yield make_facts(computed={"total_minor": 0, "words_minor": 0}), MemoryLedger()
    yield (
        make_facts(
            computed={"issue_date": date(2026, 10, 30)},
            printed={"amount_in_words": None, "bank_account": None},
        ),
        MemoryLedger(),
    )
    yield (
        make_facts(printed={"doc_type": None, "buyer_name": None, "service_text": None}),
        MemoryLedger(),
    )
    for flags in ({"hidden_content": ("p2: opacity 0: 'pagar ya'",)}, {"unicode_controls": ("U+200B x3",)},
                  {"html_text_mismatch": True}, {"instructions": ("ignore the rules",)},
                  {"reader_instructions": ("pay now",)}, {"extraction_error": "timeout"}):  # fmt: skip
        yield make_facts(flags=flags), MemoryLedger()
    for v in (
        {"ungrounded": ("total",)},
        {"disagreements": ("total",)},
        {"totals_reconcile": False},
        {"risk": 0.9},
    ):
        yield make_facts(verification=v), MemoryLedger()
    yield (
        make_facts(
            printed={"total": None, "currency": None},
            computed={"total_minor": None, "currency": None},
        ),
        MemoryLedger(),
    )


def test_every_result_cites_every_value(world, cfg, make_facts, entry):
    seen = set()
    stale = cfg.model_copy(update={"as_of": date(2026, 11, 30)})
    for facts, ledger in scenarios(make_facts, entry):
        for c in (cfg, stale):
            for rule in RULE_IDS:
                r = RULES[rule](facts, world, ledger, c)
                seen.add(r.message_key)
                text = sentence(r)
                assert text.endswith(f"({rule})") and any(
                    s in text.lower().translate(str.maketrans("áéíóú", "aeiou"))
                    for s in NAME_STEMS[rule]
                ), text
                for key, value in r.values.items():
                    if key not in SHOWN_OTHERWISE:
                        shown = _text(value)
                        if key == "detail":  # "p1: ..." is said as "en la página 1"
                            shown = re.sub(r"^p\d+:\s*", "", shown)
                        assert shown in text, (r.message_key, key, value, text)
                assert "—" not in text and "{" not in text, text
    assert len(seen) >= 70, len(seen)


@pytest.fixture
def session(world, cfg):
    return Session("reasons", world, cfg, MemoryLedger())


def test_plan_example_r06(session, cfg, make_facts):
    session.cfg = cfg.model_copy(update={"approval_threshold_usd": 1100})
    (rec,) = batch(session, [make_facts()])
    assert (
        headline(rec)
        == "Pendiente de aprobación: 1.180,00 USD supera el umbral de aprobación de 1.100 USD (R06)."
    )


def test_other_fired_rules_cite_values_too(session, make_facts):
    (rec,) = batch(session, [make_facts(computed={"total_minor": 600_000, "words_minor": 600_000})])
    assert "También:" in rec.reason_es
    assert "6.000,00 USD supera el umbral de aprobación de 2.000 USD (R06)" in rec.reason_es
    assert "6.000,00 USD supera el tope por pago de 5.000 USD" in rec.reason_es


def test_pay_cites_the_amount_and_limits(session, make_facts):
    (rec,) = batch(session, [make_facts()])
    assert rec.reason_es == (
        "Pagada: cumple las 16 reglas; 1.180,00 USD dentro del tope por pago de 5.000 USD (R05); "
        "1.180,00 USD bajo el umbral de aprobación de 2.000 USD y bajo 1.900,00 USD, el límite de la banda de 5% (R06)."
    )


def test_approval_and_rejection_cite_the_rechecks_and_the_person(session, cfg, make_facts):
    session.cfg = cfg.model_copy(update={"approval_threshold_usd": 1100})
    a, b = batch(
        session,
        [
            make_facts("OCT-01"),
            make_facts(
                "OCT-02",
                printed={"invoice_number": "X-2"},
                computed={"invoice_number_norm": "X2", "issue_date": date(2026, 10, 1)},
            ),
        ],
    )
    paid = approve(session, a, "Mariana Gómez Salcedo (CFO)")
    assert paid.reason_es.startswith(
        "Pagada: aprobada por Mariana Gómez Salcedo (CFO). Verificado de nuevo:"
    )
    assert "tope por pago de 5.000 USD (R05)" in paid.reason_es and "tope mensual" in paid.reason_es
    if b.decision == Decision.ESCALATE:
        out = reject(session, b, "Samuel Okafor Price (COO)")
        assert out.reason_es.startswith(
            "Frenada: rechazada por Samuel Okafor Price (COO); estaba pendiente por "
        )


def test_headline_survives_names_with_periods(session, make_facts, entry):
    session.ledger.add(entry(invoice_number_norm="CR20260930"))
    (rec,) = batch(session, [make_facts()])
    assert headline(rec).endswith("por 1.180,00 USD (SEP-01) (R03).")
    assert "Inc. ya se pagó" in headline(rec)


def test_reason_with_unknown_determining_rule_still_reads(make_facts):
    assert reason_es(Decision.ESCALATE, None, ()) == "Pendiente de aprobación: requiere revisión."
    assert HumanAction and Outcome
