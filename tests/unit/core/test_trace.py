"""alinka/trace.py against the Probar contract, on stored readings: OCT-01 (routine),
OCT-16 (near the approval threshold) and ATK-01-1 (hidden white text)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from alinka import trace
from alinka.decide import core
from alinka.decide.ledger import MemoryLedger
from alinka.trace import STEPS, TraceStep, build_trace
from alinka.types import RULE_IDS, Flags, Printed, Verification
from alinka.world import load_run_dir

RUNS = Path(__file__).parents[3] / "data" / "runs"
KEYS = {
    "received": {"invoice_id", "channel", "pages", "sha8", "filename", "language"},
    "sanitize": {"hidden_content", "unicode_controls", "html_text_mismatch", "instructions"},
    "read": {"mode", "calls", "fields", "stamps", "instructions_seen", "error"},
    "verify": {
        "calls",
        "fields",
        "ungrounded",
        "disagreements",
        "amount_in_regex",
        "totals_reconcile",
        "jev",
        "risk",
        "risk_max",
    },  # fmt: skip
    "rules": {"results"},
    "decide": {"decision", "label_es", "determining_rule", "alerts", "reason_es", "payment"},
    "record": {"record_id", "seq", "hash8", "prev_hash8"},
}
PRINTED_FIELDS = {n for n in Printed.model_fields if n != "stamps"}


@pytest.fixture(scope="module")
def records(world, cfg):
    def run(split: str, only: set[str] | None = None):
        facts = [
            f for f in load_run_dir(RUNS / split) if only is None or f.source.invoice_id in only
        ]
        session = core.Session(id=split, world=world, cfg=cfg, ledger=MemoryLedger(), records=[])
        return {r.invoice_id: r for r in core.batch(session, facts)}

    return run("showcase") | run("attack", {"ATK-01-1"})


def summaries(steps: list[TraceStep]) -> dict[str, tuple[str, str]]:
    return {s.step: (s.status, s.summary_es) for s in steps}


@pytest.mark.parametrize("invoice_id", ["OCT-01", "OCT-16", "ATK-01-1"])
def test_trace_follows_the_contract(records, invoice_id):
    rec = records[invoice_id]
    steps = build_trace(rec)
    assert tuple(s.step for s in steps) == STEPS
    assert [s.title_es for s in steps] == [
        "Recepción", "Contenido oculto", "La IA lee", "Verificación", "16 reglas", "Decisión", "Registro",
    ]  # fmt: skip
    for s in steps:
        assert set(s.data) == KEYS[s.step]
        assert s.ms is None and s.summary_es
    by = {s.step: s.data for s in steps}
    assert set(by["read"]["fields"]) == set(by["verify"]["fields"]) == PRINTED_FIELDS
    assert [r["rule"] for r in by["rules"]["results"]] == list(RULE_IDS)
    assert by["record"]["hash8"] == rec.hash[:8] and by["record"]["prev_hash8"] == rec.prev_hash[:8]
    assert by["decide"]["reason_es"] == rec.reason_es
    # The API sends these as JSON, and the page reads them back.
    again = [TraceStep.model_validate_json(s.model_dump_json()) for s in steps]
    assert [a.model_dump(mode="json") for a in again] == [s.model_dump(mode="json") for s in steps]


def test_routine_invoice_is_clean_and_paid(records):
    steps = build_trace(records["OCT-01"])
    got = summaries(steps)
    assert got == {
        "received": ("done", "OCT-01 llegó por PDF: 1 página, huella 28937aa2"),
        "sanitize": ("done", "Sin contenido oculto: ni texto invisible, ni caracteres de control, ni instrucciones"),
        "read": ("done", "La IA leyó 16 campos, cada uno con su cita"),
        "verify": ("done", "Verificación: 6 de 6 campos críticos con cita en la página; la segunda lectura coincide"),
        "rules": ("done", "Reglas: 16 se cumplen"),
        "decide": ("done", "Pagada: las 16 reglas se cumplen; pago a Cobalt Ridge Hosting, Inc."),
    } | {"record": got["record"]}  # fmt: skip
    rec = records["OCT-01"]
    assert got["record"] == (
        "done",
        f"Registro n.º 1, hash {rec.hash[:8]}, encadenado al anterior 00000000",
    )
    decide = steps[5].data
    assert decide["label_es"] == "Pagada" and decide["payment"]["account_masked"]
    assert steps[2].data["mode"] in ("replay", "live")


def test_trap_escalates_on_the_threshold(records):
    steps = build_trace(records["OCT-16"])
    got = summaries(steps)
    assert got["rules"] == ("flagged", "Reglas: 15 se cumplen, 1 escala (R06)")
    assert got["decide"] == ("done", "Pendiente de aprobación por umbral de aprobación (R06)")
    r06 = steps[4].data["results"][5]
    assert r06["outcome"] == "escalate" and "umbral de aprobación" in r06["sentence_es"]
    assert r06["sentence_es"].endswith("(R06)") and "USD" in r06["sentence_es"]
    assert steps[5].data["payment"] is None


def test_attack_flags_hidden_text_before_the_reading(records):
    steps = build_trace(records["ATK-01-1"])
    got = summaries(steps)
    assert got["sanitize"] == (
        "flagged", "Contenido oculto: texto blanco o del color del fondo en la página 1; no se leyó",
    )  # fmt: skip
    assert steps[1].data["hidden_content"]
    assert got["rules"] == ("flagged", "Reglas: 15 se cumplen, 1 escala (R11)")
    assert steps[5].data["alerts"] == ["R11"]
    assert steps[4].data["results"][10]["security"] is True


def test_read_error_and_risk_change_the_status(records):
    facts = records["OCT-01"].facts
    broken = facts.model_copy(update={"flags": Flags(extraction_error="timeout")})
    assert trace.read(broken).status == "error"
    risky = facts.model_copy(update={"verification": Verification(risk=0.7)})
    step = trace.verify(risky, risk_max=0.7)
    assert step.status == "flagged" and "riesgo 0,70" in step.summary_es
    assert trace.verify(risky, risk_max=0.71).status == "done"


def test_running_step_and_strict_model():
    step = trace.running("read")
    assert (step.status, step.title_es, step.ms, step.data) == ("running", "La IA lee", None, {})
    with pytest.raises(ValidationError):
        TraceStep(step="read", status="done", title_es="x", summary_es="y", extra=1)
    with pytest.raises(ValidationError):
        step.status = "done"  # frozen
