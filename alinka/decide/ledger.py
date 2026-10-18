"""The payment ledger the rules read: an interface, kept in memory here; Lane D backs it with Postgres."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Protocol


class Status(StrEnum):
    PAID = "paid"
    APPROVED = "approved"
    PENDING = "pending"  # escalated, waiting for a person
    REJECTED = "rejected"


ACTIVE = frozenset({Status.PAID, Status.APPROVED, Status.PENDING})  # R03, R13, R14
SPENT = frozenset({Status.PAID, Status.APPROVED})  # R07, R08


@dataclass(frozen=True)
class LedgerEntry:
    invoice_id: str
    beneficiary_id: str | None
    invoice_number_norm: str | None
    fiscal_id_norm: str | None
    doc_sha256: str
    amount_minor: int
    currency: str
    usd_minor: int
    period: str | None  # billing period key, see rules.period_key
    received: date
    decided: date
    cost_center: str | None
    status: Status


class Ledger(Protocol):
    def entries(self) -> Iterable[LedgerEntry]: ...

    def add(self, entry: LedgerEntry) -> None: ...

    def set_status(self, invoice_id: str, status: Status) -> None: ...


class MemoryLedger:
    def __init__(self, entries: Iterable[LedgerEntry] = ()) -> None:
        self._entries: list[LedgerEntry] = list(entries)

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def add(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def set_status(self, invoice_id: str, status: Status) -> None:
        self._entries = [
            replace(e, status=status) if e.invoice_id == invoice_id else e for e in self._entries
        ]


def excluding(ledger: Ledger, invoice_id: str) -> MemoryLedger:
    """The ledger as a re-check of this invoice sees it: its own entry left out."""
    return MemoryLedger(e for e in ledger.entries() if e.invoice_id != invoice_id)
