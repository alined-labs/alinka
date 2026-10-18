"""The seven steps of one invoice's run, as shown on Probar and in "Cómo se decidió".

TraceStep is the contract in the brain decision "Probar contract". Each builder turns a
finished stage into its final step; `running` is the step announced before the stage
starts. `build_trace` rebuilds all seven from a stored record, with no durations.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from alinka.audit.reasons import sentence
from alinka.types import (
    CRITICAL_FIELDS,
    DECISION_ES,
    RULE_NAMES_ES,
    DecisionRecord,
    Field,
    InvoiceFacts,
    ModelCall,
    Outcome,
    RuleResult,
)
from alinka.world import load_rules

StepName = Literal["received", "sanitize", "read", "verify", "rules", "decide", "record"]
Status = Literal["running", "done", "flagged", "error"]
Mode = Literal["replay", "live"]

STEPS: tuple[StepName, ...] = (
    "received", "sanitize", "read", "verify", "rules", "decide", "record",
)  # fmt: skip
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
    "received": "Recibiendo el documento",
    "sanitize": "Buscando contenido oculto antes de que la IA lo vea",
    "read": "La IA lee las páginas y cita cada dato",
    "verify": "El código comprueba cada cita, los montos y la segunda lectura",
    "rules": "Aplicando las 16 reglas",
    "decide": "Combinando los resultados de las reglas",
    "record": "Guardando la decisión en el registro encadenado",
}
CHANNEL_ES = {"pdf": "PDF", "image": "imagen", "email": "correo", "chat": "chat"}
FIELD_ES = {
    "beneficiary_name": "beneficiario",
    "beneficiary_tax_id": "identificación",
    "invoice_number": "número",
    "currency": "moneda",
    "total": "total",
    "due_date": "fecha de pago",
}
# The sanitizer's flag text (alinka/ingest) -> what a person would call it.
HIDDEN_ES: tuple[tuple[str, str], ...] = (
    ("opacity 0", "texto transparente"),
    ("render mode 3", "texto invisible"),
    ("optional-content layer", "texto en una capa oculta"),
    ("under 2 pt", "texto diminuto"),
    ("outside the CropBox", "texto fuera de la página"),
    ("coloured like the background", "texto blanco o del color del fondo"),
    ("covered by another object", "texto tapado"),
    ("annotation", "una anotación"),
    ("form field", "un campo de formulario"),
    ("embedded files", "archivos incrustados"),
    ("CropBox differs", "una página recortada"),
    ("hidden element", "un elemento oculto en el HTML del correo"),
    ("attachment not read", "un adjunto que no se leyó"),
)


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


def _step(step: StepName, status: Status, summary: str, data: dict[str, Any], ms: int | None):
    return TraceStep(
        step=step, status=status, title_es=TITLES_ES[step], summary_es=summary, ms=ms, data=data
    )


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} y {items[-1]}"


def _call(c: ModelCall) -> dict[str, Any]:
    return {
        "role": c.role, "model": c.model, "cached": c.cached,
        "cost_usd": c.cost_usd, "latency_ms": c.latency_ms,
    }  # fmt: skip


def _fields(facts: InvoiceFacts) -> dict[str, Field]:
    return {
        name: value
        for name in type(facts.printed).model_fields
        if isinstance(value := getattr(facts.printed, name), Field)
    }


def _decimal(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


# --- One builder per step ----------------------------------------------------------


def received(facts: InvoiceFacts, ms: int | None = None) -> TraceStep:
    s = facts.source
    data = {
        "invoice_id": s.invoice_id,
        "channel": s.channel.value,
        "pages": s.pages,
        "sha8": s.doc_sha256[:8],
        "filename": PurePosixPath(s.path).name if s.path else s.invoice_id,
        "language": s.language.value if s.language else None,
    }
    summary = (
        f"{s.invoice_id} llegó por {CHANNEL_ES[s.channel.value]}: "
        f"{_plural(s.pages, 'página', 'páginas')}, huella {data['sha8']}"
    )
    return _step("received", "done", summary, data, ms)


def _hidden_es(flag: str) -> str:
    return next((es for key, es in HIDDEN_ES if key in flag), "contenido oculto")


def sanitize(facts: InvoiceFacts, ms: int | None = None) -> TraceStep:
    fl = facts.flags
    data = {
        "hidden_content": list(fl.hidden_content),
        "unicode_controls": list(fl.unicode_controls),
        "html_text_mismatch": fl.html_text_mismatch,
        "instructions": list(fl.instructions),
    }
    found: list[str] = []
    if fl.hidden_content:
        kinds = list(dict.fromkeys(_hidden_es(f) for f in fl.hidden_content))
        pages = sorted(
            {int(m.group(1)) for f in fl.hidden_content if (m := re.match(r"p(\d+):", f))}
        )
        where = ""
        if pages:
            where = (
                f" en la página {pages[0]}"
                if len(pages) == 1
                else f" en las páginas {_join([str(p) for p in pages])}"
            )
        found.append(f"{_join(kinds)}{where}")
    if fl.unicode_controls:
        found.append(
            _plural(
                len(fl.unicode_controls),
                "carácter Unicode invisible",
                "caracteres Unicode invisibles",
            )
        )
    if fl.html_text_mismatch:
        found.append("el HTML del correo dice algo distinto a su texto plano")
    if fl.instructions:
        found.append(
            _plural(
                len(fl.instructions),
                "instrucción dirigida a un sistema",
                "instrucciones dirigidas a un sistema",
            )
        )
    if not found:
        summary = (
            "Sin contenido oculto: ni texto invisible, ni caracteres de control, ni instrucciones"
        )
        return _step("sanitize", "done", summary, data, ms)
    unread = "; no se leyó" if fl.hidden_content or fl.unicode_controls else "; la IA no lo sigue"
    return _step("sanitize", "flagged", f"Contenido oculto: {_join(found)}{unread}", data, ms)


def read(facts: InvoiceFacts, mode: Mode | None = None, ms: int | None = None) -> TraceStep:
    calls = [c for c in facts.calls if c.role == "reader"]
    if mode is None:
        mode = "replay" if all(c.cached for c in calls) else "live"
    fields = _fields(facts)
    fl = facts.flags
    data = {
        "mode": mode,
        "calls": [_call(c) for c in calls],
        "fields": {
            name: {"value": f.value, "quote": f.quote, "confidence": f.confidence.value}
            for name, f in fields.items()
        },
        "stamps": list(facts.printed.stamps),
        "instructions_seen": list(fl.reader_instructions),
        "error": fl.extraction_error,
    }
    if fl.extraction_error:
        summary = "La lectura falló y la factura pasa a una persona (R10)"
        return _step("read", "error", summary, data, ms)
    stated = [f for f in fields.values() if f.value is not None]
    quoted = sum(1 for f in stated if f.quote)
    summary = f"La IA leyó {_plural(len(stated), 'campo', 'campos')}, " + (
        "cada uno con su cita" if quoted == len(stated) else f"{quoted} con su cita"
    )
    if fl.reader_instructions:
        n = len(fl.reader_instructions)
        summary += f"; reportó {_plural(n, 'instrucción', 'instrucciones')} dirigida{'s' if n > 1 else ''} a un sistema y no la{'s' if n > 1 else ''} siguió"
        return _step("read", "flagged", summary, data, ms)
    return _step("read", "done", summary, data, ms)


def verify(facts: InvoiceFacts, risk_max: float, ms: int | None = None) -> TraceStep:
    v = facts.verification
    fields = _fields(facts)
    data = {
        "calls": [_call(c) for c in facts.calls if c.role in ("checker", "jev")],
        "fields": {
            name: {
                "grounded": f.grounded,
                "agreed": f.agreed,
                "boxes": [b.model_dump() for b in f.boxes],
            }
            for name, f in fields.items()
        },
        "ungrounded": list(v.ungrounded),
        "disagreements": list(v.disagreements),
        "amount_in_regex": v.amount_in_regex,
        "totals_reconcile": v.totals_reconcile,
        "jev": [
            {"question": j.question, "answer": j.answer, "probability": j.probability}
            for j in v.jev
        ],
        "risk": v.risk,
        "risk_max": risk_max,
    }
    grounded = len(CRITICAL_FIELDS) - len(set(v.ungrounded) & set(CRITICAL_FIELDS))
    parts = [f"{grounded} de {len(CRITICAL_FIELDS)} campos críticos con cita en la página"]
    if v.disagreements:
        names = [FIELD_ES.get(f, f) for f in v.disagreements]
        parts.append(f"la segunda lectura difiere en {_join(names)}")
    elif any(f.agreed is not None for f in fields.values()):
        parts.append("la segunda lectura coincide")
    if v.amount_in_regex is False:
        parts.append("el total no aparece entre los montos de la página")
    if v.totals_reconcile is False:
        parts.append("subtotal más impuestos no da el total")
    risky = v.risk >= risk_max  # as R10 compares it
    if risky:
        parts.append(f"riesgo {_decimal(v.risk)}, al menos el máximo de {_decimal(risk_max)}")
    flagged = bool(
        v.ungrounded or v.disagreements or risky
        or v.amount_in_regex is False or v.totals_reconcile is False
    )  # fmt: skip
    return _step(
        "verify", "flagged" if flagged else "done", f"Verificación: {'; '.join(parts)}", data, ms
    )


def rules(results: tuple[RuleResult, ...], ms: int | None = None) -> TraceStep:
    data = {
        "results": [
            {
                "rule": r.rule,
                "name_es": RULE_NAMES_ES[r.rule],
                "outcome": r.outcome.value,
                "security": r.security,
                "approvable": r.approvable,
                "sentence_es": sentence(r),
            }
            for r in results
        ]
    }
    passed = sum(1 for r in results if r.outcome == Outcome.PASS)
    parts = [f"{passed} se cumple{'n' if passed != 1 else ''}"]
    for outcome, one, many in (
        (Outcome.HOLD, "frena", "frenan"),
        (Outcome.ESCALATE, "escala", "escalan"),
    ):
        ids = [r.rule for r in results if r.outcome == outcome]
        if ids:
            parts.append(f"{len(ids)} {one if len(ids) == 1 else many} ({', '.join(ids)})")
    status: Status = "done" if passed == len(results) else "flagged"
    return _step("rules", status, f"Reglas: {', '.join(parts)}", data, ms)


def decide(record: DecisionRecord, ms: int | None = None) -> TraceStep:
    data = {
        "decision": record.decision.value,
        "label_es": DECISION_ES[record.decision],
        "determining_rule": record.determining_rule,
        "alerts": list(record.alerts),
        "reason_es": record.reason_es,
        "payment": record.payment.model_dump() if record.payment else None,
    }
    summary = DECISION_ES[record.decision]
    if record.determining_rule:
        summary += (
            f" por {RULE_NAMES_ES[record.determining_rule].lower()} ({record.determining_rule})"
        )
    elif record.payment:
        summary += f": las 16 reglas se cumplen; pago a {record.payment.beneficiary_name}"
    if record.alerts:
        summary += f", con {_plural(len(record.alerts), 'alerta', 'alertas')} de seguridad ({', '.join(record.alerts)})"
    return _step("decide", "done", summary, data, ms)


def record(rec: DecisionRecord, ms: int | None = None) -> TraceStep:
    data = {
        "record_id": rec.record_id,
        "seq": rec.seq,
        "hash8": rec.hash[:8],
        "prev_hash8": rec.prev_hash[:8],
    }
    summary = (
        f"Registro n.º {rec.seq}, hash {data['hash8']}, encadenado al anterior {data['prev_hash8']}"
    )
    return _step("record", "done", summary, data, ms)


def risk_max_of(rec: DecisionRecord) -> float:
    """The verifier_risk_max in force: R10 records it; otherwise data/rules.yaml."""
    r10 = next((r for r in rec.results if r.rule == "R10"), None)
    value = r10.values.get("risk_max") if r10 else None
    return float(value) if isinstance(value, int | float) else load_rules().verifier_risk_max


def build_trace(rec: DecisionRecord, mode: Mode | None = None) -> list[TraceStep]:
    """All seven steps of a stored record, with final statuses and no durations."""
    facts = rec.facts
    return [
        received(facts),
        sanitize(facts),
        read(facts, mode),
        verify(facts, risk_max_of(rec)),
        rules(rec.results),
        decide(rec),
        record(rec),
    ]
