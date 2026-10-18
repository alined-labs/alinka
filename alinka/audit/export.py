"""The reconciliation spreadsheet: one row per decision record, in log order."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from alinka.money import minor_digits
from alinka.rules import currency, total_minor
from alinka.types import DECISION_ES, DecisionRecord, Outcome

COLUMNS = (
    "factura", "beneficiario", "monto", "moneda", "usd", "decision", "reglas", "motivo",
    "aprobador", "fecha",
)  # fmt: skip


def safe(cell: str) -> str:
    """Names come from untrusted documents: never let a cell start a spreadsheet formula."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@", "\t", "\r") else cell


def decimal(minor: int | None, cur: str | None) -> str:
    if minor is None or cur is None:
        return ""
    digits = minor_digits(cur) if cur in ("COP", "MXN", "BRL", "EUR", "USD") else 2
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 10**digits)
    return f"{sign}{whole}.{frac:0{digits}d}"


def row(r: DecisionRecord) -> list[str]:
    f, pay = r.facts, r.payment
    cur = pay.currency if pay else currency(f)
    amount = pay.amount_minor if pay else total_minor(f)
    usd = pay.usd_minor if pay else f.computed.usd_minor
    fired = " ".join(x.rule for x in r.results if x.outcome != Outcome.PASS)
    cells = [
        r.invoice_id,
        pay.beneficiary_name if pay else (f.printed.beneficiary_name.value or ""),
        decimal(amount, cur),
        cur or "",
        decimal(usd, "USD"),
        DECISION_ES[r.decision],
        fired,
        r.reason_es,
        r.human.approver if r.human else "",
        r.created_at.isoformat(),
    ]
    return [safe(c) for c in cells]


def export_csv(records: Iterable[DecisionRecord]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    writer.writerows(row(r) for r in records)
    return out.getvalue()
