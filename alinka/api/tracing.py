"""The seven Probar steps (decision "Probar contract"), built from what each stage left.

A stand-in with the contract's TraceStep shape until Lane A's alinka/trace.py (A12)
merges; then this module re-exports theirs. The builders take the stage's partial
InvoiceFacts (received to verify) or the sealed DecisionRecord (rules to record), and
build_trace rebuilds all seven from a stored record.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from alinka.audit.reasons import sentence
from alinka.types import (
    DECISION_ES,
    RULE_NAMES_ES,
    Channel,
    DecisionRecord,
    InvoiceFacts,
    Outcome,
    Printed,
)
from alinka.world import load_rules

StepName = Literal["received", "sanitize", "read", "verify", "rules", "decide", "record"]
Status = Literal["running", "done", "flagged", "error"]
STEPS: tuple[StepName, ...] = (
    "received",
    "sanitize",
    "read",
    "verify",
    "rules",
    "decide",
    "record",
)
TITLES_ES: dict[StepName, str] = {
    "received": "Recepción",
    "sanitize": "Contenido oculto",
    "read": "La IA lee",
    "verify": "Verificación",
    "rules": "16 reglas",
    "decide": "Decisión",
    "record": "Registro",
}
RUNNING_ES: dict[StepName, str] = {
    "received": "Recibiendo el documento…",
    "sanitize": "Buscando contenido oculto…",
    "read": "La IA está leyendo la factura…",
    "verify": "Verificando cada dato en código…",
    "rules": "Aplicando las 16 reglas…",
    "decide": "Decidiendo…",
    "record": "Escribiendo en el registro…",
}
CHANNEL_ES = {
    Channel.PDF: "PDF",
    Channel.IMAGE: "foto",
    Channel.EMAIL: "correo",
    Channel.CHAT: "chat",
}
OUTCOME = {Outcome.PASS: "pass", Outcome.HOLD: "hold", Outcome.ESCALATE: "escalate"}


class TraceStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step: StepName
    status: Status
    title_es: str
    summary_es: str
    ms: int | None = None
    data: dict[str, Any] = {}


def running(step: StepName) -> TraceStep:
    return TraceStep(
        step=step, status="running", title_es=TITLES_ES[step], summary_es=RUNNING_ES[step]
    )


def _step(step: StepName, status: Status, summary: str, data: dict, ms: int | None) -> TraceStep:
    return TraceStep(
        step=step, status=status, title_es=TITLES_ES[step], summary_es=summary, ms=ms, data=data
    )


def _num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _calls(facts: InvoiceFacts, roles: set[str]) -> list[dict]:
    return [
        {
            "role": c.role,
            "model": c.model,
            "cached": c.cached,
            "cost_usd": c.cost_usd,
            "latency_ms": c.latency_ms,
        }
        for c in facts.calls
        if c.role in roles
    ]


def _fields(printed: Printed) -> dict[str, Any]:
    return {name: getattr(printed, name) for name in Printed.model_fields if name != "stamps"}


# --- One builder per step -----------------------------------------------------------


def received(facts: InvoiceFacts, filename: str | None = None, ms: int | None = None) -> TraceStep:
    s = facts.source
    name = filename or (PurePosixPath(s.path).name if s.path else s.invoice_id)
    error = facts.flags.extraction_error
    failed = s.pages == 0 and bool(error)
    pages = f"{s.pages} página" + ("" if s.pages == 1 else "s")
    summary = (
        f"No se pudo abrir el documento ({CHANNEL_ES[s.channel]}); pasará a una persona."
        if failed
        else f"Llegó por {CHANNEL_ES[s.channel]}: {pages}, huella {s.doc_sha256[:8]}."
    )
    data = {
        "invoice_id": s.invoice_id,
        "channel": s.channel.value,
        "pages": s.pages,
        "sha8": s.doc_sha256[:8],
        "filename": name,
        "language": s.language.value if s.language else None,
    }
    return _step("received", "error" if failed else "done", summary, data, ms)


def sanitize(facts: InvoiceFacts, ms: int | None = None) -> TraceStep:
    fl = facts.flags
    data = {
        "hidden_content": list(fl.hidden_content),
        "unicode_controls": list(fl.unicode_controls),
        "html_text_mismatch": fl.html_text_mismatch,
        "instructions": list(fl.instructions),
    }
    found = [
        label
        for label, hit in (
            ("texto oculto", fl.hidden_content),
            ("caracteres invisibles", fl.unicode_controls),
            ("el HTML del correo dice otra cosa que su texto", fl.html_text_mismatch),
            ("instrucciones dirigidas a una IA", fl.instructions),
        )
        if hit
    ]
    if found:
        return _step("sanitize", "flagged", "Encontró " + ", ".join(found) + ".", data, ms)
    return _step("sanitize", "done", "Sin contenido oculto ni instrucciones escondidas.", data, ms)


def read(facts: InvoiceFacts, ms: int | None = None) -> TraceStep:
    calls = _calls(facts, {"reader"})
    fields = {
        name: {"value": f.value, "quote": f.quote, "confidence": f.confidence.value}
        for name, f in _fields(facts.printed).items()
    }
    error = facts.flags.extraction_error
    seen = list(facts.flags.reader_instructions)
    data = {
        "mode": "live" if any(not c["cached"] for c in calls) else "replay",
        "calls": calls,
        "fields": fields,
        "stamps": list(facts.printed.stamps),
        "instructions_seen": seen,
        "error": error,
    }
    if error:
        return _step(
            "read", "error", "La lectura falló; la factura pasará a una persona.", data, ms
        )
    n = sum(1 for f in fields.values() if f["value"] is not None)
    summary = f"La IA leyó {n} campos, cada uno con su cita"
    if seen:
        return _step("read", "flagged", summary + ", y vio instrucciones que no siguió.", data, ms)
    return _step("read", "done", summary + ".", data, ms)


def verify(facts: InvoiceFacts, risk_max: float, ms: int | None = None) -> TraceStep:
    v = facts.verification
    fields = {
        name: {
            "grounded": f.grounded,
            "agreed": f.agreed,
            "boxes": [b.model_dump(mode="json") for b in f.boxes],
        }
        for name, f in _fields(facts.printed).items()
    }
    data = {
        "calls": _calls(facts, {"checker", "jev"}),
        "fields": fields,
        "ungrounded": list(v.ungrounded),
        "disagreements": list(v.disagreements),
        "amount_in_regex": v.amount_in_regex,
        "totals_reconcile": v.totals_reconcile,
        "jev": [
            {"question": a.question, "answer": a.answer, "probability": a.probability}
            for a in v.jev
        ],
        "risk": v.risk,
        "risk_max": risk_max,
    }
    problems = [
        text
        for text, hit in (
            (f"citas no encontradas: {', '.join(v.ungrounded)}", v.ungrounded),
            (f"las dos lecturas difieren en {', '.join(v.disagreements)}", v.disagreements),
            ("el total no aparece entre los montos de la página", v.amount_in_regex is False),
            ("subtotal más impuestos no da el total", v.totals_reconcile is False),
            (f"riesgo {_num(v.risk)} desde el límite {_num(risk_max)}", v.risk >= risk_max),
        )
        if hit
    ]
    if problems:
        return _step("verify", "flagged", "Dudas: " + "; ".join(problems) + ".", data, ms)
    grounded = sum(1 for f in fields.values() if f["grounded"])
    summary = (
        f"{grounded} citas encontradas en la página y las dos lecturas coinciden;"
        f" riesgo {_num(v.risk)} (límite {_num(risk_max)})."
    )
    return _step("verify", "done", summary, data, ms)


def rules(record: DecisionRecord, ms: int | None = None) -> TraceStep:
    results = [
        {
            "rule": r.rule,
            "name_es": RULE_NAMES_ES[r.rule],
            "outcome": OUTCOME[r.outcome],
            "security": r.security,
            "approvable": r.approvable,
            "sentence_es": sentence(r),
        }
        for r in record.results
    ]
    stopped = [r["rule"] for r in results if r["outcome"] != "pass"]
    if stopped:
        summary = f"{16 - len(stopped)} de 16 reglas pasan; no pasan: {', '.join(stopped)}."
        return _step("rules", "flagged", summary, {"results": results}, ms)
    return _step("rules", "done", "Las 16 reglas pasan.", {"results": results}, ms)


def decide(record: DecisionRecord, ms: int | None = None) -> TraceStep:
    label = DECISION_ES[record.decision]
    rule = record.determining_rule
    data = {
        "decision": record.decision.value,
        "label_es": label,
        "determining_rule": rule,
        "alerts": list(record.alerts),
        "reason_es": record.reason_es,
        "payment": record.payment.model_dump(mode="json") if record.payment else None,
    }
    summary = (
        f"{label}, por la regla {RULE_NAMES_ES[rule].lower()} ({rule})." if rule else f"{label}."
    )
    return _step("decide", "done", summary, data, ms)


def record_step(record: DecisionRecord, ms: int | None = None) -> TraceStep:
    data = {
        "record_id": record.record_id,
        "seq": record.seq,
        "hash8": record.hash[:8],
        "prev_hash8": record.prev_hash[:8],
    }
    summary = (
        f"Registro n.º {record.seq}, encadenado al anterior"
        f" ({record.prev_hash[:8]} → {record.hash[:8]})."
    )
    return _step("record", "done", summary, data, ms)


def build_trace(record: DecisionRecord, risk_max: float | None = None) -> list[TraceStep]:
    """The seven steps of a stored record with their final statuses and no timings."""
    facts = record.facts
    limit = load_rules().verifier_risk_max if risk_max is None else risk_max
    return [
        received(facts),
        sanitize(facts),
        read(facts),
        verify(facts, limit),
        rules(record),
        decide(record),
        record_step(record),
    ]
