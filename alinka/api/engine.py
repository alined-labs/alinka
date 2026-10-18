"""The API's door to Lane A's decision core (alinka.decide.core). Nothing here returns PAY.

The core works on an in-memory session; here each call gets a one-off session holding a
snapshot of the Postgres ledger, and the ledger writes it makes are handed back to be
stored in the same transaction. db.seal then places the record in the stored chain.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from alinka.decide import core
from alinka.decide.ledger import LedgerEntry, Status
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

ERROR_ES = "Pendiente de aprobación: error técnico al decidir."


class Refused(Exception):
    """The core refused an approval; the message is Spanish and shown to the person."""


class SnapshotLedger:
    """core.decide.ledger.Ledger over a snapshot, recording what the core writes."""

    def __init__(self, entries: list[LedgerEntry]) -> None:
        self._entries = list(entries)
        self.added: list[LedgerEntry] = []
        self.statuses: dict[str, Status] = {}

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def add(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)
        self.added.append(entry)

    def set_status(self, invoice_id: str, status: Status) -> None:
        self._entries = [
            replace(e, status=status) if e.invoice_id == invoice_id else e for e in self._entries
        ]
        self.statuses[invoice_id] = status


def _session(world: World, rules: RulesConfig, ledger: SnapshotLedger, records=()):
    return core.Session(id="draft", world=world, cfg=rules, ledger=ledger, records=list(records))


def _escalated(facts: InvoiceFacts, rules: RulesConfig) -> DecisionRecord:
    results = tuple(
        RuleResult(rule=r, outcome=Outcome.ESCALATE, approvable=False, message_key="engine.error")
        for r in RULE_IDS
    )
    return DecisionRecord(
        record_id="draft", session="draft", seq=1, prev_hash=core.GENESIS, hash="",
        invoice_id=facts.source.invoice_id, decision=Decision.ESCALATE, results=results,
        reason_es=ERROR_ES, facts=facts, rules_version=rules.version,
        rules_hash=rules_hash(rules), as_of=rules.as_of, code_version=core.CODE_VERSION,
        created_at=datetime.now(UTC),
    )  # fmt: skip


def decide(
    facts: InvoiceFacts, world: World, rules: RulesConfig, entries: list[LedgerEntry]
) -> tuple[DecisionRecord, list[LedgerEntry]]:
    """One invoice: the core's record (sealed again by db) and the ledger rows it wrote."""
    ledger = SnapshotLedger(entries)
    try:
        record = core.record_decision(_session(world, rules, ledger), facts)
    except Exception:  # noqa: BLE001 - any failure escalates, with nothing to pay
        return _escalated(facts, rules), []
    return record, ledger.added


def act(
    record: DecisionRecord,
    human: HumanAction,
    world: World,
    rules: RulesConfig,
    entries: list[LedgerEntry],
) -> tuple[DecisionRecord, dict[str, Status]]:
    """Approve or reject an escalation through the core, which re-checks R03, R05, R07, R08."""
    ledger = SnapshotLedger(entries)
    session = _session(world, rules, ledger, [record])
    step = core.approve if human.action == "approve" else core.reject
    try:
        new = step(session, record, human.approver, human.note, human.at)
    except core.ApprovalRefused as exc:
        raise Refused(str(exc)) from exc
    return new, ledger.statuses


def approval_blockers(record: DecisionRecord) -> list[str]:
    return list(core.approval_blockers(record))
