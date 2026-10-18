"""Pure functions that turn facts and decision records into the API's response models."""

from __future__ import annotations

import re
from collections.abc import Sequence

from alinka.api.models import Board, Card, Column, FieldView, LogEntry, RuleView, View
from alinka.decide.core import approval_blockers
from alinka.rules import claimed
from alinka.types import (
    CRITICAL_FIELDS,
    DECISION_ES,
    RULE_NAMES_ES,
    Beneficiary,
    Decision,
    DecisionRecord,
    InvoiceFacts,
    Outcome,
    Printed,
)
from alinka.world import World

INBOX_ES = "Bandeja de entrada"
TECHNICAL_ERROR_ES = "error técnico"

FIELD_LABELS_ES: dict[str, str] = {
    "doc_type": "Tipo de documento",
    "beneficiary_name": "Beneficiario",
    "beneficiary_tax_id": "Identificación tributaria",
    "invoice_number": "Número de factura",
    "fiscal_id": "Identificador fiscal",
    "issue_date": "Fecha de emisión",
    "due_date": "Fecha de vencimiento",
    "service_period": "Periodo del servicio",
    "currency": "Moneda",
    "subtotal": "Subtotal",
    "tax_total": "Impuestos",
    "total": "Total a pagar",
    "amount_in_words": "Monto en letras",
    "bank_account": "Cuenta impresa (no se usa para pagar)",
    "service_text": "Concepto",
    "buyer_name": "Comprador",
    "buyer_tax_id": "Identificación del comprador",
}


def norm_id(value: str | None) -> str:
    """Uppercase letters and digits only, so "DEMO-12-3456789" matches "demo 123456789"."""
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


def beneficiary_for(facts: InvoiceFacts, world: World) -> Beneficiary | None:
    """The listed beneficiary the document claims to be, for display only (R01 decides)."""
    return claimed(facts, world)


def _base(facts: InvoiceFacts, ben: Beneficiary | None) -> dict:
    return {
        "invoice_id": facts.source.invoice_id,
        "channel": facts.source.channel,
        "received_at": facts.source.received_at,
        "beneficiary_id": ben.id if ben else None,
        "beneficiary_name": ben.name if ben else facts.printed.beneficiary_name.value,
        "amount_minor": facts.computed.total_minor,
        "currency": facts.computed.currency,
        "usd_minor": facts.computed.usd_minor,
    }


def inbox_card(facts: InvoiceFacts, ben: Beneficiary | None) -> Card:
    return Card(**_base(facts, ben), state="inbox", state_es=INBOX_ES)


def short_reason(reason_es: str) -> str:
    """The first sentence of the reason, which already names the rule and its values."""
    head, dot, _ = reason_es.partition(". ")
    return head + "." if dot else reason_es


def can_approve(record: DecisionRecord, view: View) -> bool:
    """Whether to show the approve button; the core decides again when it is pressed."""
    return (
        view == "sandbox"
        and record.decision == Decision.ESCALATE
        and record.human is None
        and not approval_blockers(record)
    )


def record_card(record: DecisionRecord, ben: Beneficiary | None, view: View) -> Card:
    det = record.determining_rule
    return Card(
        **_base(record.facts, ben),
        state=record.decision.value,
        state_es=DECISION_ES[record.decision],
        determining_rule=det,
        determining_rule_es=RULE_NAMES_ES[det] if det else None,
        alerts=record.alerts,
        reason_es=short_reason(record.reason_es),
        approvable=can_approve(record, view),
        approver=record.human.approver if record.human else None,
        technical_error=record.facts.flags.extraction_error is not None
        or (record.decision == Decision.ESCALATE and det is None),
    )


def board(
    session_id: str,
    view: View,
    rules_version: str,
    cards: Sequence[Card],
    head_hash: str | None,
) -> Board:
    ordered = sorted(cards, key=lambda c: (c.received_at, c.invoice_id))
    columns = []
    for decision in (Decision.PAY, Decision.HOLD, Decision.ESCALATE):
        # Security alerts are listed first within a column.
        col = sorted(
            (c for c in ordered if c.state == decision.value),
            key=lambda c: (not c.alerts, c.received_at, c.invoice_id),
        )
        columns.append(
            Column(
                decision=decision, label_es=DECISION_ES[decision], count=len(col), cards=tuple(col)
            )
        )
    return Board(
        session_id=session_id,
        view=view,
        rules_version=rules_version,
        head_hash=head_hash,
        total=len(ordered),
        inbox=tuple(c for c in ordered if c.state == "inbox"),
        columns=tuple(columns),  # type: ignore[arg-type]
    )


def field_views(printed: Printed) -> tuple[FieldView, ...]:
    out = []
    for name, label in FIELD_LABELS_ES.items():
        f = getattr(printed, name)
        out.append(
            FieldView(
                name=name,
                label_es=label,
                value=f.value,
                quote=f.quote,
                confidence=f.confidence,
                grounded=f.grounded,
                agreed=f.agreed,
                critical=name in CRITICAL_FIELDS,
                boxes=f.boxes,
            )
        )
    return tuple(out)


def rule_views(record: DecisionRecord) -> tuple[RuleView, ...]:
    out = []
    for r in record.results:
        if r.rule == record.determining_rule:
            reason = record.reason_es
        elif r.outcome == Outcome.PASS:
            reason = f"{RULE_NAMES_ES[r.rule]}: cumple."
        else:
            reason = f"{RULE_NAMES_ES[r.rule]}: no cumple ({r.rule})."
        out.append(
            RuleView(
                rule=r.rule,
                name_es=RULE_NAMES_ES[r.rule],
                outcome=r.outcome,
                security=r.security,
                approvable=r.approvable,
                values=r.values,
                reason_es=reason,
            )
        )
    return tuple(out)


def log_entry(record: DecisionRecord) -> LogEntry:
    return LogEntry(
        seq=record.seq,
        record_id=record.record_id,
        invoice_id=record.invoice_id,
        decision=record.decision,
        decision_es=DECISION_ES[record.decision],
        determining_rule=record.determining_rule,
        reason_es=record.reason_es,
        approver=record.human.approver if record.human else None,
        prev_hash=record.prev_hash,
        hash=record.hash,
        created_at=record.created_at,
    )
