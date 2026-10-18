"""The decision core: the only code that returns PAY (AGENTS.md rule 16).

Every rule runs and every result is kept. HOLD beats ESCALATE beats PAY. Any exception,
in a rule or around it, becomes ESCALATE.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from alinka.audit.chain import GENESIS, seal
from alinka.audit.reasons import reason_es
from alinka.decide.ledger import Ledger, LedgerEntry, Status, excluding
from alinka.rules import (
    RULES,
    currency,
    invoice_number,
    norm_id,
    period_base,
    period_key,
    resolve,
    total_minor,
    usd_minor,
)
from alinka.types import (
    NEVER_APPROVABLE,
    RECHECK_ON_APPROVAL,
    RULE_IDS,
    Decision,
    DecisionRecord,
    HumanAction,
    InvoiceFacts,
    Outcome,
    PaymentPreview,
    RuleId,
    RuleResult,
    RulesConfig,
)
from alinka.world import World, rules_hash

CODE_VERSION = "0.1.0"


class ApprovalRefused(Exception):
    """The approval cannot happen; the message is Spanish and shown to the person."""


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    determining_rule: RuleId | None
    results: tuple[RuleResult, ...]
    alerts: tuple[RuleId, ...]
    payment: PaymentPreview | None = None


def run_rule(
    rule: RuleId, facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig
) -> RuleResult:
    try:
        r = RULES[rule](facts, world, ledger, cfg)
        if r.rule != rule:
            raise ValueError(f"{rule} returned a result for {r.rule}")
        return r
    except Exception as exc:  # noqa: BLE001 - any failure escalates
        return RuleResult(
            rule=rule, outcome=Outcome.ESCALATE, approvable=False,
            values={"error": f"{type(exc).__name__}: {exc}"[:200]}, message_key=f"{rule}.error",
        )  # fmt: skip


def combine(results: tuple[RuleResult, ...], facts: InvoiceFacts) -> tuple[Decision, RuleId | None]:
    """Precedence HOLD > ESCALATE > PAY; PAY only when all 16 passed and nothing failed to read."""
    by_rule = {r.rule: r for r in results}
    holds = [r for r in results if r.outcome == Outcome.HOLD]
    escalates = [r for r in results if r.outcome == Outcome.ESCALATE]
    if holds:
        return Decision.HOLD, holds[0].rule
    if escalates:
        security = [r for r in escalates if r.security]
        return Decision.ESCALATE, (security or escalates)[0].rule
    if (
        set(by_rule) != set(RULE_IDS)
        or len(results) != len(RULE_IDS)
        or any(r.outcome != Outcome.PASS for r in results)
        or facts.flags.extraction_error is not None
    ):
        return Decision.ESCALATE, "R10"
    return Decision.PAY, None


def mask_account(account: str) -> str:
    """Hide every digit but the last four."""
    total = sum(c.isdigit() for c in account)
    seen = 0
    out = []
    for c in account:
        if c.isdigit():
            seen += 1
            out.append(c if seen > total - 4 else "•")
        else:
            out.append(c)
    return "".join(out)


def preview(facts: InvoiceFacts, world: World, cfg: RulesConfig) -> PaymentPreview:
    """The payout always uses the account on the beneficiary list (AGENTS.md rule 17)."""
    ben = resolve(facts, world, cfg)
    total, cur, usd = total_minor(facts), currency(facts), usd_minor(facts, world, cfg)
    if ben is None or total is None or cur is None or usd is None:
        raise ValueError("no listed beneficiary or amount for the payment preview")
    return PaymentPreview(
        beneficiary_id=ben.id, beneficiary_name=ben.name, account_masked=mask_account(ben.account_on_file),
        amount_minor=total, currency=cur, usd_minor=usd,
    )  # fmt: skip


def decide(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> Verdict:
    try:
        results = tuple(run_rule(rule, facts, world, ledger, cfg) for rule in RULE_IDS)
        decision, determining = combine(results, facts)
        alerts = tuple(r.rule for r in results if r.security and r.outcome != Outcome.PASS)
        payment = preview(facts, world, cfg) if decision == Decision.PAY else None
        return Verdict(decision, determining, results, alerts, payment)
    except Exception as exc:  # noqa: BLE001
        error = RuleResult(
            rule="R10", outcome=Outcome.ESCALATE, approvable=False,
            values={"error": f"{type(exc).__name__}: {exc}"[:200]}, message_key="R10.error",
        )  # fmt: skip
        return Verdict(Decision.ESCALATE, "R10", (error,), ())


def ledger_entry(
    facts: InvoiceFacts, world: World, cfg: RulesConfig, status: Status
) -> LedgerEntry:
    ben = resolve(facts, world, cfg)
    cur = currency(facts) or "USD"
    return LedgerEntry(
        invoice_id=facts.source.invoice_id,
        beneficiary_id=ben.id if ben else None,
        invoice_number_norm=invoice_number(facts),
        fiscal_id_norm=norm_id(facts.printed.fiscal_id.value),
        doc_sha256=facts.source.doc_sha256,
        amount_minor=total_minor(facts) or 0,
        currency=cur,
        usd_minor=usd_minor(facts, world, cfg) or 0,
        period=period_key(period_base(facts), ben.contract.frequency) if ben else None,
        received=facts.source.received_at.date(),
        decided=cfg.as_of,
        cost_center=ben.contract.cost_center if ben else None,
        status=status,
    )


# --- Sessions: a chain of records plus the ledger ------------------------------------


@dataclass
class Session:
    """One canonical run or sandbox, in memory. Lane D persists the same steps in Postgres."""

    id: str
    world: World
    cfg: RulesConfig
    ledger: Ledger
    records: list[DecisionRecord] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.records[-1].hash if self.records else GENESIS

    def append(self, **fields: object) -> DecisionRecord:
        seq = len(self.records) + 1
        record = seal(
            {
                "record_id": f"{self.id}-{seq:04d}", "session": self.id, "seq": seq,
                "prev_hash": self.head, "rules_version": self.cfg.version,
                "rules_hash": rules_hash(self.cfg), "as_of": self.cfg.as_of,
                "code_version": CODE_VERSION, **fields,
            }
        )  # fmt: skip
        self.records.append(record)
        return record

    def latest(self, invoice_id: str) -> DecisionRecord | None:
        return next((r for r in reversed(self.records) if r.invoice_id == invoice_id), None)


def record_decision(
    session: Session, facts: InvoiceFacts, at: datetime | None = None
) -> DecisionRecord:
    """Decide one invoice and write the record; PAY and ESCALATE write the ledger.

    Invoice IDs are unique within a session: the ledger, approvals and re-checks key on them.
    """
    if session.latest(facts.source.invoice_id) is not None or any(
        e.invoice_id == facts.source.invoice_id for e in session.ledger.entries()
    ):
        raise ValueError(f"{facts.source.invoice_id} was already decided in session {session.id}")
    v = decide(facts, session.world, session.ledger, session.cfg)
    if v.decision == Decision.PAY:
        session.ledger.add(ledger_entry(facts, session.world, session.cfg, Status.PAID))
    elif v.decision == Decision.ESCALATE:
        session.ledger.add(ledger_entry(facts, session.world, session.cfg, Status.PENDING))
    return session.append(
        invoice_id=facts.source.invoice_id, decision=v.decision, determining_rule=v.determining_rule,
        results=v.results, alerts=v.alerts, reason_es=reason_es(v.decision, v.determining_rule, v.results),
        facts=facts, created_at=at or datetime.now(UTC), payment=v.payment,
    )  # fmt: skip


def batch(session: Session, items: Iterable[InvoiceFacts]) -> list[DecisionRecord]:
    """Decide in received order (ties by invoice ID), so the ledger grows as it would live."""
    ordered = sorted(items, key=lambda f: (f.source.received_at, f.source.invoice_id))
    return [record_decision(session, f) for f in ordered]


def _pending(session: Session, record: DecisionRecord) -> DecisionRecord:
    latest = session.latest(record.invoice_id)
    if latest is None or latest.hash != record.hash:
        raise ApprovalRefused("Ya hay una decisión más reciente para esta factura.")
    if record.decision != Decision.ESCALATE or record.human is not None:
        raise ApprovalRefused(
            "Solo se puede aprobar o rechazar una factura pendiente de aprobación."
        )
    return record


def approval_blockers(record: DecisionRecord) -> list[RuleId]:
    """Rules that forbid approval: R01 or R12 fired, or a result marked not approvable."""
    return [
        r.rule
        for r in record.results
        if r.outcome != Outcome.PASS and (r.rule in NEVER_APPROVABLE or not r.approvable)
    ]


def _approver(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name:
        raise ApprovalRefused("La aprobación necesita el nombre de quien aprueba.")
    return name[:120]


def approve(
    session: Session, record: DecisionRecord, approver: str, note: str | None = None,
    at: datetime | None = None,
) -> DecisionRecord:  # fmt: skip
    """Approve an escalation: refused for R01/R12; R03, R05, R07 and R08 are re-checked now."""
    record = _pending(session, record)
    name = _approver(approver)
    if blockers := approval_blockers(record):
        raise ApprovalRefused(f"No se puede aprobar: {', '.join(blockers)} no admite aprobación.")
    at = at or datetime.now(UTC)
    facts, world, cfg = record.facts, session.world, session.cfg
    others = excluding(session.ledger, record.invoice_id)
    rechecked = {rule: run_rule(rule, facts, world, others, cfg) for rule in RECHECK_ON_APPROVAL}
    results = tuple(rechecked.get(r.rule, r) for r in record.results)
    human = HumanAction(action="approve", approver=name, note=note, at=at)
    failed = [r for r in rechecked.values() if r.outcome != Outcome.PASS]
    if failed:  # a late approval never breaks a cap: it becomes a HOLD
        session.ledger.set_status(record.invoice_id, Status.REJECTED)
        return session.append(
            invoice_id=record.invoice_id, decision=Decision.HOLD, determining_rule=failed[0].rule,
            results=results, alerts=record.alerts, facts=facts, created_at=at, human=human,
            reason_es=reason_es(Decision.HOLD, failed[0].rule, tuple(failed)),
        )  # fmt: skip
    payment = preview(facts, world, cfg)
    session.ledger.set_status(record.invoice_id, Status.APPROVED)
    return session.append(
        invoice_id=record.invoice_id, decision=Decision.PAY, determining_rule=None, results=results,
        alerts=record.alerts, facts=facts, created_at=at, human=human, payment=payment,
        reason_es=reason_es(Decision.PAY, None, results, approver=name),
    )  # fmt: skip


def reject(
    session: Session, record: DecisionRecord, approver: str, note: str | None = None,
    at: datetime | None = None,
) -> DecisionRecord:  # fmt: skip
    """Reject an escalation: recorded as a HOLD with the person's name; the ledger drops it."""
    record = _pending(session, record)
    name = _approver(approver)
    at = at or datetime.now(UTC)
    session.ledger.set_status(record.invoice_id, Status.REJECTED)
    return session.append(
        invoice_id=record.invoice_id, decision=Decision.HOLD, determining_rule=record.determining_rule,
        results=record.results, alerts=record.alerts, facts=record.facts, created_at=at,
        human=HumanAction(action="reject", approver=name, note=note, at=at),
        reason_es=f"Frenada: rechazada por {name}.",
    )  # fmt: skip
