"""The API's door to Lane A's decision core. Nothing here returns PAY by itself.

Until `alinka.decide.core` is merged, every invoice escalates as "error técnico" and
approvals are refused: a missing engine costs a review, never a payment (AGENTS.md 16).
"""

from __future__ import annotations

from datetime import UTC, datetime

from alinka import db
from alinka.api.views import beneficiary_for
from alinka.types import (
    RULE_IDS,
    Decision,
    DecisionRecord,
    HumanAction,
    InvoiceFacts,
    Outcome,
    RuleResult,
    RulesConfig,
)
from alinka.world import World, rules_hash

CODE_VERSION = "api-0.1.0"
ENGINE_MISSING_ES = "Pendiente de aprobación: error técnico. El motor de reglas no está disponible."


class EngineUnavailable(RuntimeError):
    pass


def _core():
    try:
        from alinka.decide import core  # Lane A (A3)
    except ImportError:
        return None
    return core


def engine_ready() -> bool:
    return _core() is not None


def _escalated(facts: InvoiceFacts, rules: RulesConfig, reason: str) -> DecisionRecord:
    results = tuple(
        RuleResult(rule=r, outcome=Outcome.ESCALATE, approvable=False, message_key="engine.error")
        for r in RULE_IDS
    )
    return DecisionRecord(
        record_id="draft", session="draft", seq=0, prev_hash="", hash="",
        invoice_id=facts.source.invoice_id, decision=Decision.ESCALATE, results=results,
        reason_es=reason, facts=facts, rules_version=rules.version,
        rules_hash=rules_hash(rules), as_of=rules.as_of, code_version=CODE_VERSION,
        created_at=datetime.now(UTC),
    )  # fmt: skip


def ledger_row(record: DecisionRecord, world: World, status: str) -> db.LedgerRow:
    f = record.facts
    ben = beneficiary_for(f, world.beneficiaries)
    return db.LedgerRow(
        invoice_id=f.source.invoice_id,
        beneficiary_id=ben.id if ben else None,
        invoice_number_norm=f.computed.invoice_number_norm,
        doc_sha256=f.source.doc_sha256,
        amount_minor=f.computed.total_minor or 0,
        currency=f.computed.currency or (ben.currency if ben else "USD"),
        usd_minor=f.computed.usd_minor or 0,
        status=status,
        fiscal_id=f.printed.fiscal_id.value,
        cost_center=ben.contract.cost_center if ben else None,
        period_start=f.computed.period_start,
        period_end=f.computed.period_end,
    )


LEDGER_STATUS = {Decision.PAY: "paid", Decision.ESCALATE: "pending"}


def decide(
    facts: InvoiceFacts, world: World, rules: RulesConfig, ledger: list[db.LedgerRow]
) -> tuple[DecisionRecord, list[db.LedgerRow]]:
    """One invoice: the record (unsealed) and the ledger rows to write with it."""
    core = _core()
    if core is None:
        record = _escalated(facts, rules, ENGINE_MISSING_ES)
    else:
        try:
            record = core.decide(facts, world, ledger, rules)
        except Exception:  # noqa: BLE001 - any failure escalates
            record = _escalated(facts, rules, "Pendiente de aprobación: error técnico al decidir.")
    status = LEDGER_STATUS.get(record.decision)
    return record, [ledger_row(record, world, status)] if status else []


def approve(
    record: DecisionRecord,
    human: HumanAction,
    world: World,
    rules: RulesConfig,
    ledger: list[db.LedgerRow],
) -> DecisionRecord:
    """The record an approval or rejection appends; the core re-checks R03, R05, R07, R08."""
    core = _core()
    if core is not None:
        return core.approve(record, human, world, ledger, rules)
    if human.action == "approve":
        raise EngineUnavailable("El motor de reglas no está disponible.")
    # A rejection only makes the decision more cautious, so it needs no engine.
    return record.model_copy(
        update={
            "decision": Decision.HOLD,
            "human": human,
            "payment": None,
            "reason_es": f"Frenada: rechazada por {human.approver}. {record.reason_es}",
            "created_at": human.at,
        }
    )
