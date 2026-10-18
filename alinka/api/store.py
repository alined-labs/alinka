"""Helpers behind the routes: rule bounds, the chain check, the CSV and the eval report."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from alinka.api.models import Bound, ChainCheck
from alinka.db import ZERO_HASH, chain_hash
from alinka.types import DECISION_ES, DecisionRecord, Outcome
from alinka.world import rules_hash  # noqa: F401 - re-exported for the routes

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Editable rule parameters and their allowed ranges (PUT /api/rules refuses the rest).
RULE_BOUNDS: dict[str, Bound] = {
    "per_payment_cap_usd": Bound(min=100, max=100_000),
    "approval_threshold_usd": Bound(min=100, max=100_000),
    "approval_band_pct": Bound(min=0, max=50),
    "monthly_cap_usd": Bound(min=1_000, max=1_000_000),
    "due_grace_days": Bound(min=0, max=365),
    "verifier_risk_max": Bound(min=0.05, max=1.0),
    "split_window_days": Bound(min=1, max=31),
    "split_threshold_usd": Bound(min=100, max=100_000),
}


def verify_chain(items: list[tuple[int, str, str, bytes]]) -> ChainCheck:
    """Check (seq, prev_hash, hash, canonical bytes) rows in order."""
    prev = ZERO_HASH
    for i, (seq, prev_hash, digest, canonical) in enumerate(items, 1):
        if seq != i or prev_hash != prev or chain_hash(prev, canonical) != digest:
            return ChainCheck(
                ok=False,
                checked=i - 1,
                head_hash=prev if i > 1 else None,
                first_bad_seq=seq,
                message_es=f"Cadena rota en el registro {seq}: el hash no coincide.",
            )
        prev = digest
    n = len(items)
    return ChainCheck(
        ok=True,
        checked=n,
        head_hash=prev if n else None,
        message_es=f"Cadena verificada: {n} registros íntegros." if n else "Registro vacío.",
    )


def amount(minor: int | None) -> str:
    return "" if minor is None else f"{minor // 100}.{minor % 100:02d}"


CSV_COLUMNS = (
    "factura", "beneficiario", "monto", "moneda", "usd", "decision", "reglas", "motivo",
    "aprobador", "fecha",
)  # fmt: skip


def export_csv(records: list[DecisionRecord], names: dict[str, str | None]) -> str:
    """One row per decision record, in log order. `names` maps invoice to beneficiary."""
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(CSV_COLUMNS)
    for r in records:
        fired = [x.rule for x in r.results if x.outcome != Outcome.PASS]
        out.writerow(
            [
                r.invoice_id,
                names.get(r.invoice_id) or r.facts.printed.beneficiary_name.value or "",
                amount(r.facts.computed.total_minor),
                r.facts.computed.currency or "",
                amount(r.facts.computed.usd_minor),
                DECISION_ES[r.decision],
                " ".join(fired),
                r.reason_es,
                r.human.approver if r.human else "",
                r.created_at.isoformat(),
            ]
        )
    return buf.getvalue()


def eval_report() -> dict | None:
    path = ROOT / "evals/report.json"
    if path.is_file():
        return json.loads(path.read_text())
    return json.loads((FIXTURES / "eval.json").read_text())
