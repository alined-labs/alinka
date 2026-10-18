"""Response and request models for every route in PLAN section 6, built on alinka.types.

These are the contract Lane E builds against through openapi.json: add optional fields
freely, but renaming or removing one breaks the front end.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime
from pydantic import Field as F

from alinka.types import (
    Box,
    Channel,
    Confidence,
    Decision,
    DecisionRecord,
    DocType,
    Model,
    Outcome,
    PaymentPreview,
    RuleId,
    RulesConfig,
)

View = Literal["sandbox", "canonical"]
CardState = Literal["inbox", "PAY", "HOLD", "ESCALATE"]


class ErrorOut(Model):
    detail: str


class Health(Model):
    status: Literal["ok", "degraded"]
    version: str
    canonical_head: str | None = None  # hash of the canonical run's last record
    database: bool = False


# --- Board --------------------------------------------------------------------


class Card(Model):
    invoice_id: str
    channel: Channel
    received_at: AwareDatetime
    beneficiary_id: str | None = None  # None when the document matches no listed beneficiary
    beneficiary_name: str | None = None  # as printed when not on the list
    amount_minor: int | None = None
    currency: str | None = None
    usd_minor: int | None = None
    state: CardState
    state_es: str  # "Bandeja de entrada", "Pagada", "Frenada", "Pendiente de aprobación"
    determining_rule: RuleId | None = None
    determining_rule_es: str | None = None
    alerts: tuple[RuleId, ...] = ()  # security alerts, shown first
    reason_es: str = ""  # one line
    approvable: bool = False  # ESCALATE in a sandbox, and neither R01 nor R12 fired
    approver: str | None = None  # set once a person approved or rejected it
    technical_error: bool = False  # "error técnico": the pipeline failed and escalated


class Column(Model):
    decision: Decision
    label_es: str
    count: int
    cards: tuple[Card, ...]


class Board(Model):
    session_id: str
    view: View
    rules_version: str
    head_hash: str | None = None
    total: int
    inbox: tuple[Card, ...]
    columns: tuple[Column, Column, Column]  # PAY, HOLD, ESCALATE in that order


class RunStep(Model):
    invoice_id: str
    decision: Decision
    determining_rule: RuleId | None = None
    elapsed_ms: int


class RunResult(Model):
    decided: int
    steps: tuple[RunStep, ...]  # in received order, for the progress animation
    board: Board


# --- Invoice detail -----------------------------------------------------------


class PageImage(Model):
    n: int  # 1-based
    url: str  # GET /api/invoices/{id}/pages/{n}
    width: int  # pixels
    height: int


class FieldView(Model):
    name: str  # a Printed attribute: total, due_date...
    label_es: str
    value: str | None = None
    quote: str | None = None
    confidence: Confidence = Confidence.LOW
    grounded: bool = False
    agreed: bool | None = None
    critical: bool = False
    boxes: tuple[Box, ...] = ()


class RuleView(Model):
    rule: RuleId
    name_es: str
    outcome: Outcome
    security: bool = False
    approvable: bool = True
    values: dict[str, str | int | float | bool | None] = F(default_factory=dict)
    reason_es: str = ""


class InvoiceDetail(Model):
    card: Card
    record: DecisionRecord | None = None  # None while the invoice is still in the inbox
    pages: tuple[PageImage, ...] = ()
    fields: tuple[FieldView, ...] = ()
    rules: tuple[RuleView, ...] = ()  # all 16 once decided, in rule order
    payment: PaymentPreview | None = None  # what would be paid, to the account on file


class ApprovalIn(Model):
    approver: str = F(min_length=1, max_length=120)
    note: str | None = F(default=None, max_length=500)


# --- Rules and beneficiaries --------------------------------------------------


class Bound(Model):
    min: float
    max: float


class BeneficiaryView(Model):
    id: str
    name: str
    tax_id: str
    country: str
    currency: str
    account_masked: str
    doc_types: tuple[DocType, ...]
    contract_id: str
    rate_minor: int
    frequency: str
    cost_center: str
    added_in_sandbox: bool = False


class RulesOut(Model):
    session_id: str
    view: View
    rules: RulesConfig
    rules_hash: str
    bounds: dict[str, Bound]  # editable keys and their allowed range
    beneficiaries: tuple[BeneficiaryView, ...]


class RulesIn(Model):
    """Editable parameters; omitted keys keep their current value."""

    per_payment_cap_usd: int | None = None
    approval_threshold_usd: int | None = None
    approval_band_pct: float | None = None
    monthly_cap_usd: int | None = None
    due_grace_days: int | None = None
    verifier_risk_max: float | None = None
    split_window_days: int | None = None
    split_threshold_usd: int | None = None


class RulesSaved(Model):
    rules: RulesOut
    board: Board


class ContractIn(Model):
    scope_es: tuple[str, ...] = F(min_length=1)
    scope_en: tuple[str, ...] = ()
    rate_minor: int = F(gt=0)
    tolerance_pct: float = F(default=5, ge=0, le=50)
    frequency: Literal["monthly", "biweekly", "weekly", "per_delivery"] = "monthly"
    valid_from: date
    valid_to: date
    cost_center: str


class BeneficiaryIn(Model):
    name: str = F(min_length=2, max_length=160)
    tax_id: str = F(pattern=r"^DEMO-[A-Za-z0-9.\-]{1,40}$")
    country: str = F(pattern=r"^[A-Z]{2}$")
    currency: str = F(pattern=r"^[A-Z]{3}$")
    account_on_file: str = F(min_length=4, max_length=120)
    doc_types: tuple[DocType, ...] = (DocType.FACTURA, DocType.CUENTA_DE_COBRO)
    contract: ContractIn


class BeneficiaryAdded(Model):
    beneficiary: BeneficiaryView
    board: Board


# --- Log and evaluation -------------------------------------------------------


class LogEntry(Model):
    seq: int
    record_id: str
    invoice_id: str
    decision: Decision
    decision_es: str
    determining_rule: RuleId | None = None
    reason_es: str
    approver: str | None = None
    prev_hash: str
    hash: str
    created_at: AwareDatetime


class Log(Model):
    session_id: str
    view: View
    head_hash: str | None = None
    entries: tuple[LogEntry, ...]


class ChainCheck(Model):
    ok: bool
    checked: int
    head_hash: str | None = None
    first_bad_seq: int | None = None
    message_es: str


class EvalOut(Model):
    available: bool
    report: dict[str, Any] | None = None  # evals/report.json as Lane A writes it
