"""Facts built from a label's gold fields: the rules' view when the reading is perfect.

Labels carry the critical fields only. Fields they lack (document type, buyer, service
text, service period, reading confidence) get routine values, except for the traps that
live in them: there a perfect reading of the trap's declared feature is simulated
(SIMULATED), and the report says so.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from alinka.money import parse_amount, words_to_minor
from alinka.rules import norm_id
from alinka.types import (
    Computed,
    Confidence,
    DocType,
    Field,
    InvoiceFacts,
    Label,
    Printed,
    Source,
    Verification,
)
from alinka.world import World

ROOT = Path(__file__).resolve().parents[1]
SIMULATED = {
    "off_contract_scope": "service text",
    "proforma": "document type",
    "other_buyer": "buyer",
    "stamp_anulada": "stamps",
    "service_outside_validity": "service period",
    "low_quality_scan": "reading confidence",
    "second_in_period": "service period",
    "hidden_white_text": "hidden-content flag",
    "hidden_render_mode_3": "hidden-content flag",
    "hidden_opacity_0": "hidden-content flag",
    "hidden_covered": "hidden-content flag",
    "hidden_layer": "hidden-content flag",
    "metadata_injection": "instructions flag",
    "urgent_cfo_chat": "instructions flag",
    "unicode_controls_chat": "Unicode-controls flag",
    "html_text_mismatch": "HTML/text mismatch flag",
}
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
    )  # fmt: skip
}
DOC_TEXT = {DocType.FACTURA: "Factura", DocType.CUENTA_DE_COBRO: "Cuenta de cobro"}


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    s = text.strip()
    for fmt in ("%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            pass
    if m := re.fullmatch(r"(\d{1,2}) de (\w+) de (\d{4})", s.casefold()):
        if (month := MONTHS.get(m.group(2))) is not None:
            return date(int(m.group(3)), month, int(m.group(1)))
    return None


def doc_sha256(path: str) -> str:
    p = ROOT / path
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "0" * 64


def gold_facts(label: Label, world: World, as_of: date) -> InvoiceFacts:
    g = label.gold_facts
    ben = world.beneficiary(label.beneficiary_id) if label.beneficiary_id else None
    cur = (g.get("currency") or "").strip().upper() or None
    es = label.language.value == "es"
    printed = {k: v for k, v in g.items() if k in Printed.model_fields}
    if ben is not None:
        printed.setdefault("doc_type", DOC_TEXT.get(ben.doc_types[0], "Invoice"))
        printed.setdefault(
            "service_text", (ben.contract.scope_es if es else ben.contract.scope_en)[0]
        )
    else:
        printed.setdefault("doc_type", "Factura" if es else "Invoice")
        printed.setdefault(
            "service_text", "servicios profesionales" if es else "professional services"
        )
    printed.setdefault("buyer_name", world.company.name)
    printed.setdefault("buyer_tax_id", world.company.tax_id)
    fields = {
        k: Field(value=v, quote=v, confidence=Confidence.HIGH, grounded=True, agreed=True)
        for k, v in printed.items()
    }
    total = parse_amount(g.get("total"), cur) if cur else None
    words = g.get("amount_in_words")
    words_minor = words_to_minor(words, cur or "USD")
    facts = InvoiceFacts(
        source=Source(
            invoice_id=label.invoice_id,
            doc_sha256=doc_sha256(label.path),
            path=label.path,
            channel=label.channel,
            language=label.language,
            received_at=label.received_at,
        ),  # fmt: skip
        as_of=as_of,
        printed=Printed(**fields),
        computed=Computed(
            currency=cur,
            total_minor=total,
            subtotal_minor=parse_amount(g.get("subtotal"), cur) if cur else None,
            tax_minor=parse_amount(g.get("tax_total"), cur) if cur else None,
            words_minor=words_minor,
            words_unparseable=bool(words) and words_minor is None,
            issue_date=parse_date(g.get("issue_date")),
            due_date=parse_date(g.get("due_date")),
            invoice_number_norm=norm_id(g.get("invoice_number")),
            beneficiary_tax_id_norm=norm_id(g.get("beneficiary_tax_id")),
        ),
        verification=Verification(risk=0.0),
    )
    return simulate(label, facts, world)


def simulate(label: Label, facts: InvoiceFacts, world: World) -> InvoiceFacts:
    """Give the trap its declared feature where the label has no field for it."""
    p, c, fl = facts.printed, facts.computed, facts.flags
    es = label.language.value == "es"
    ben = world.beneficiary(label.beneficiary_id) if label.beneficiary_id else None
    text = lambda f, v: f.model_copy(update={"value": v, "quote": v})  # noqa: E731
    match label.trap:
        case "off_contract_scope":
            v = "Mantenimiento de oficinas" if es else "Office maintenance"
            p = p.model_copy(update={"service_text": text(p.service_text, v)})
        case "proforma":
            p = p.model_copy(
                update={
                    "doc_type": text(p.doc_type, "Factura proforma" if es else "Proforma invoice")
                }
            )
        case "other_buyer":
            p = p.model_copy(
                update={
                    "buyer_name": text(p.buyer_name, "Otra Empresa LLC"),
                    "buyer_tax_id": Field(),
                }
            )
        case "stamp_anulada":
            p = p.model_copy(update={"stamps": ("ANULADA",)})
        case "service_outside_validity" if ben is not None:
            start = ben.contract.valid_from - timedelta(days=31)
            c = c.model_copy(
                update={"period_start": start, "period_end": start + timedelta(days=30)}
            )
        case "low_quality_scan":
            weak = {k: getattr(p, k).model_copy(update={"confidence": Confidence.LOW, "grounded": False})
                    for k in ("total", "invoice_number", "due_date")}  # fmt: skip
            p = p.model_copy(update=weak)
        case "second_in_period" if c.issue_date is not None:
            end = c.issue_date.replace(day=1) - timedelta(days=1)  # the month already billed
            c = c.model_copy(update={"period_start": end.replace(day=1), "period_end": end})
        case trap if trap and trap.startswith("hidden_"):
            fl = fl.model_copy(update={"hidden_content": (f"p1: {trap} (simulado)",)})
        case "metadata_injection" | "urgent_cfo_chat":
            fl = fl.model_copy(update={"instructions": (f"{label.trap} (simulado)",)})
        case "unicode_controls_chat":
            fl = fl.model_copy(update={"unicode_controls": ("U+200B (simulado)",)})
        case "html_text_mismatch":
            fl = fl.model_copy(update={"html_text_mismatch": True})
        case _:
            return facts
    return facts.model_copy(update={"printed": p, "computed": c, "flags": fl})
