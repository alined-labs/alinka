"""The data behind the routes. D1 serves hand-written fixtures; D3 swaps in Postgres."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import rfc8785
import yaml

from alinka.api.models import Bound, ChainCheck, View
from alinka.types import (
    DECISION_ES,
    Beneficiary,
    Company,
    DecisionRecord,
    InvoiceFacts,
    Outcome,
    RulesConfig,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
ZERO_HASH = "0" * 64

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


@lru_cache
def load_rules() -> RulesConfig:
    return RulesConfig.model_validate(yaml.safe_load((ROOT / "data/rules.yaml").read_text()))


@lru_cache
def load_company() -> Company:
    return Company.model_validate(yaml.safe_load((ROOT / "data/company.yaml").read_text()))


@lru_cache
def load_beneficiaries() -> tuple[Beneficiary, ...]:
    raw = yaml.safe_load((ROOT / "data/vendors.yaml").read_text())
    return tuple(Beneficiary.model_validate(b) for b in raw["beneficiaries"])


def rules_hash(rules: RulesConfig) -> str:
    return hashlib.sha256(rfc8785.dumps(rules.model_dump(mode="json"))).hexdigest()


def record_bytes(record: DecisionRecord) -> bytes:
    """RFC 8785 bytes of the record without its hash: what the chain signs."""
    body = record.model_dump(mode="json")
    body.pop("hash")
    return rfc8785.dumps(body)


def chain_hash(prev_hash: str, canonical: bytes) -> str:
    return hashlib.sha256(prev_hash.encode() + canonical).hexdigest()


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


@dataclass
class FixtureSession:
    session_id: str
    view: View
    records: list[DecisionRecord] = field(default_factory=list)
    facts: list[InvoiceFacts] = field(default_factory=list)  # every invoice, received order
    decided: bool = True


@lru_cache
def fixture_records() -> tuple[DecisionRecord, ...]:
    lines = (FIXTURES / "records.jsonl").read_text().splitlines()
    return tuple(DecisionRecord.model_validate(json.loads(x)) for x in lines if x.strip())


def fixture_session(session_id: str, view: View, decided: bool) -> FixtureSession:
    records = list(fixture_records())
    return FixtureSession(
        session_id=session_id,
        view=view,
        records=records if decided else [],
        facts=[r.facts for r in records],
        decided=decided,
    )


@lru_cache
def eval_report() -> dict | None:
    path = ROOT / "evals/report.json"
    if path.is_file():
        return json.loads(path.read_text())
    return json.loads((FIXTURES / "eval.json").read_text())
