"""Shared contracts for every lane. Frozen: change only after a `brain block`.

Additive changes (a new optional field with a default) are cheap; anything else
breaks other lanes. Conventions:
- Money is integer minor units plus an ISO 4217 code. USD conversion rounds up.
- `Field.value` is text exactly as printed on the document; values the code derives
  from it live in `Computed`. A model never fills `Computed`.
- Page boxes are normalised to 0..1 of the page width and height, origin top-left.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict
from pydantic import Field as F

SCHEMA_VERSION = "1"


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Vocabulary ---------------------------------------------------------------


class Decision(StrEnum):
    PAY = "PAY"
    HOLD = "HOLD"
    ESCALATE = "ESCALATE"


DECISION_ES: dict[Decision, str] = {
    Decision.PAY: "Pagada",
    Decision.HOLD: "Frenada",
    Decision.ESCALATE: "Pendiente de aprobación",
}


class Outcome(StrEnum):
    PASS = "pass"
    HOLD = "hold"
    ESCALATE = "escalate"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Channel(StrEnum):
    PDF = "pdf"
    IMAGE = "image"
    EMAIL = "email"
    CHAT = "chat"


class Language(StrEnum):
    ES = "es"
    EN = "en"


class Split(StrEnum):
    SHOWCASE = "showcase"  # the typical October month (30)
    GENERATED = "generated"  # the evaluation set (120)
    ATTACK = "attack"  # hand-written attacks (25)


class DocType(StrEnum):
    FACTURA = "factura"
    CUENTA_DE_COBRO = "cuenta_de_cobro"
    INVOICE = "invoice"
    PROFORMA = "proforma"
    COTIZACION = "cotizacion"
    NOTA_CREDITO = "nota_credito"
    OTHER = "other"


RuleId = Literal[
    "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08",
    "R09", "R10", "R11", "R12", "R13", "R14", "R15", "R16",
]  # fmt: skip
RULE_IDS: tuple[RuleId, ...] = (
    "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08",
    "R09", "R10", "R11", "R12", "R13", "R14", "R15", "R16",
)  # fmt: skip
RULE_NAMES_ES: dict[RuleId, str] = {
    "R01": "Beneficiario autorizado",
    "R02": "Moneda y país",
    "R03": "Duplicado",
    "R04": "Lo pactado",
    "R05": "Tope por pago",
    "R06": "Umbral de aprobación",
    "R07": "Tope mensual",
    "R08": "Saldo y presupuesto",
    "R09": "Fecha de pago",
    "R10": "Lectura confiable",
    "R11": "Contenido oculto",
    "R12": "Cuenta bancaria",
    "R13": "Fraccionamiento",
    "R14": "Frecuencia",
    "R15": "Monto en letras",
    "R16": "Documento pagable",
}
SECURITY_RULES: frozenset[str] = frozenset({"R01", "R11", "R12"})  # may raise a security alert
NEVER_APPROVABLE: frozenset[str] = frozenset({"R01", "R12"})  # no approve button when fired
RECHECK_ON_APPROVAL: tuple[RuleId, ...] = ("R03", "R05", "R07", "R08")
CRITICAL_FIELDS: tuple[str, ...] = (
    "beneficiary_name", "beneficiary_tax_id", "invoice_number", "currency", "total", "due_date",
)  # fmt: skip


# --- What the reader and the verifiers produce ---------------------------------


class Box(Model):
    page: int  # 1-based
    x0: float
    y0: float
    x1: float
    y1: float


class Field(Model):
    """One value exactly as printed, with its evidence."""

    value: str | None = None  # None means "not stated"
    quote: str | None = None  # the verbatim span of visible text that contains the value
    confidence: Confidence = Confidence.LOW
    grounded: bool = False  # code found the quote in the visible text or the OCR text
    agreed: bool | None = None  # the second reading returned the same value; None = not compared
    boxes: tuple[Box, ...] = ()  # where the quote sits on the page images


class Printed(Model):
    """Strings exactly as printed. EN 16931 business terms in brackets where one applies."""

    doc_type: Field = F(default_factory=Field)  # factura, cuenta de cobro, invoice... [BT-3]
    stamps: tuple[str, ...] = ()  # ANULADA, PAGADA, BORRADOR, PROFORMA...
    buyer_name: Field = F(default_factory=Field)  # [BT-44]
    buyer_tax_id: Field = F(default_factory=Field)  # [BT-48]
    beneficiary_name: Field = F(default_factory=Field)  # the seller [BT-27]
    beneficiary_tax_id: Field = F(default_factory=Field)  # [BT-31] or national ID
    invoice_number: Field = F(default_factory=Field)  # [BT-1]
    fiscal_id: Field = F(default_factory=Field)  # CUFE, CFDI UUID, CAE, NFS-e key... when printed
    issue_date: Field = F(default_factory=Field)  # [BT-2]
    due_date: Field = F(default_factory=Field)  # [BT-9]
    service_period: Field = F(default_factory=Field)  # [BG-14]
    currency: Field = F(default_factory=Field)  # [BT-5]
    subtotal: Field = F(default_factory=Field)  # [BT-109]
    tax_total: Field = F(default_factory=Field)  # [BT-110]
    total: Field = F(default_factory=Field)  # amount due [BT-115]
    amount_in_words: Field = F(default_factory=Field)
    bank_account: Field = F(default_factory=Field)  # any account printed; never used to pay
    service_text: Field = F(default_factory=Field)  # what is being charged [BT-153]


class FxUsed(Model):
    currency: str
    rate: str  # decimal string exactly as published
    quote: Literal["per_usd", "usd_per_unit"]  # COP, MXN, BRL per USD; USD per EUR (ECB)
    date: date
    source: str
    url: str


class Computed(Model):
    """Values derived in code from Printed. None means missing or unparseable."""

    currency: str | None = None  # ISO 4217
    total_minor: int | None = None
    subtotal_minor: int | None = None
    tax_minor: int | None = None
    words_minor: int | None = None  # the amount in words, parsed in code
    words_unparseable: bool = False
    issue_date: date | None = None
    due_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    invoice_number_norm: str | None = None
    beneficiary_tax_id_norm: str | None = None
    buyer_tax_id_norm: str | None = None
    bank_account_norm: str | None = None
    usd_minor: int | None = None  # rounded up
    fx: FxUsed | None = None


class Flags(Model):
    hidden_content: tuple[str, ...] = ()  # code: "p1: span with opacity 0: 'Pagar a ...'"
    unicode_controls: tuple[str, ...] = ()  # code: format, tag or bidi characters found
    html_text_mismatch: bool = False  # code: an email's HTML differs from its plain text
    instructions: tuple[str, ...] = ()  # code: text addressed to a system or an AI
    reader_instructions: tuple[str, ...] = ()  # the reader reports instructions it saw
    extraction_error: str | None = None  # exception, refusal, truncation or validation error


class JevAnswer(Model):
    question: str  # "J1" or "J2.<field>"
    answer: str  # the chosen option, or "yes" / "no"
    probability: float  # of that answer (for a yes/no question, of "yes")
    confidence: float | None = None


class Verification(Model):
    disagreements: tuple[str, ...] = ()  # critical fields where the two readings differ
    ungrounded: tuple[str, ...] = ()  # critical fields whose quote was not found
    amount_in_regex: bool | None = None  # the total is among the page's money spans
    totals_reconcile: bool | None = None  # subtotal + tax == total, when all are printed
    jev: tuple[JevAnswer, ...] = ()
    risk: float = 1.0  # 0..1, from code checks plus JEV; R10 escalates at verifier_risk_max
    notes: tuple[str, ...] = ()


class ModelCall(Model):
    role: Literal["reader", "checker", "jev"]
    model: str
    prompt_hash: str
    cache_key: str
    cached: bool
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    stop_reason: str | None = None


class Source(Model):
    invoice_id: str  # OCT-01, GEN-0001, ATK-01, UPL-<sha8>
    doc_sha256: str
    path: str | None = None  # repo-relative path of the source document
    channel: Channel
    language: Language | None = None
    received_at: AwareDatetime
    pages: int = 0


class InvoiceFacts(Model):
    """Everything that crosses the trust boundary into the rules."""

    schema_version: str = SCHEMA_VERSION
    source: Source
    as_of: date
    printed: Printed = F(default_factory=Printed)
    computed: Computed = F(default_factory=Computed)
    flags: Flags = F(default_factory=Flags)
    verification: Verification = F(default_factory=Verification)
    calls: tuple[ModelCall, ...] = ()


# --- What the rules and the decision core produce -------------------------------

Scalar = str | int | float | bool | None


class RuleResult(Model):
    rule: RuleId
    outcome: Outcome
    security: bool = False  # raises a security alert
    approvable: bool = True
    values: dict[str, Scalar] = F(default_factory=dict)  # the values the reason cites
    message_key: str  # e.g. "R03.duplicate_number"; audit/ turns it into Spanish


class PaymentPreview(Model):
    beneficiary_id: str
    beneficiary_name: str
    account_masked: str  # from the beneficiary list, never from the document
    amount_minor: int
    currency: str
    usd_minor: int


class HumanAction(Model):
    action: Literal["approve", "reject"]
    approver: str
    note: str | None = None
    at: AwareDatetime


class DecisionRecord(Model):
    record_id: str
    session: str
    seq: int
    prev_hash: str  # 64 zeros for the first record of a session
    hash: str  # sha256(prev_hash + RFC 8785 bytes of this record without `hash`)
    invoice_id: str
    decision: Decision
    determining_rule: RuleId | None = None
    results: tuple[RuleResult, ...]  # all 16, in rule order
    alerts: tuple[RuleId, ...] = ()  # security alerts, listed first in the UI
    reason_es: str
    facts: InvoiceFacts
    rules_version: str
    rules_hash: str
    as_of: date
    code_version: str
    created_at: AwareDatetime
    payment: PaymentPreview | None = None  # PAY only
    human: HumanAction | None = None


# --- The fictional world (data/company.yaml, data/vendors.yaml, data/rules.yaml) ---


class CostCenter(Model):
    id: str  # engineering, design, operations, software
    name_es: str
    budget_usd_minor: int  # October 2026


class Company(Model):
    name: str  # contains "Demo"
    tax_id: str  # DEMO-...
    country: str = "US"
    state: str = "DE"
    balance_usd_minor: int
    cost_centers: tuple[CostCenter, ...]
    approvers: tuple[str, ...] = ()


class Contract(Model):
    id: str
    scope_es: tuple[str, ...]  # keywords
    scope_en: tuple[str, ...]
    rate_minor: int  # agreed amount per billing period, in the contract currency
    currency: str
    tolerance_pct: float
    frequency: Literal["monthly", "biweekly", "weekly", "per_delivery"]
    valid_from: date
    valid_to: date
    cost_center: str


class Beneficiary(Model):
    id: str  # BEN-01 ... BEN-13
    name: str
    tax_id: str  # DEMO-...
    country: str  # ISO 3166-1 alpha-2
    currency: str  # ISO 4217
    account_on_file: str  # fictional; masked whenever shown
    doc_types: tuple[DocType, ...]
    contract: Contract


class RulesConfig(Model):
    """data/rules.yaml. Whole USD unless the name says otherwise."""

    version: str
    as_of: date
    fx_max_age_days: int
    per_payment_cap_usd: int  # R05
    approval_threshold_usd: int  # R06
    approval_band_pct: float  # R06: this close below the threshold also escalates
    monthly_cap_usd: int  # R07
    due_grace_days: int  # R09
    verifier_risk_max: float  # R10
    split_window_days: int  # R13
    split_threshold_usd: int  # R13
    name_similarity_min: float  # R01


class Label(Model):
    """Gold label, written from the trap's intent (data/generator/traps.yaml)."""

    invoice_id: str
    split: Split
    channel: Channel
    language: Language
    path: str
    received_at: AwareDatetime
    trap: str | None = None  # trap key; None = routine
    gold_decision: Decision
    gold_rules: tuple[RuleId, ...] = ()
    gold_security: bool = False
    gold_facts: dict[str, str | None] = F(default_factory=dict)  # critical fields as printed
    beneficiary_id: str | None = None  # the listed beneficiary this document claims to be
