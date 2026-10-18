"""Shared fixtures: the real world files and a builder for routine, rule-passing facts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from alinka.decide.ledger import LedgerEntry, MemoryLedger, Status
from alinka.types import (
    Channel,
    Computed,
    Confidence,
    Field,
    Flags,
    InvoiceFacts,
    Printed,
    RulesConfig,
    Source,
    Verification,
)
from alinka.world import World, load_rules, load_world

ROUTINE_PRINTED = {  # BEN-10, Cobalt Ridge Hosting, inside its USD contract
    "doc_type": "Invoice",
    "buyer_name": "Ceiba Demo Labs, Inc.",
    "buyer_tax_id": "DEMO-88-4417302",
    "beneficiary_name": "Cobalt Ridge Hosting, Inc.",
    "beneficiary_tax_id": "DEMO-12-3456789",
    "invoice_number": "CR-2026-0930",
    "issue_date": "September 30, 2026",
    "due_date": "October 30, 2026",
    "currency": "USD",
    "total": "1,180.00",
    "amount_in_words": "One thousand one hundred eighty and 00/100 US Dollars",
    "bank_account": "Demo Federal Bank · ABA DEMO-0210 · Acct DEMO-4421-0010",
    "service_text": "Cloud hosting and storage, September 2026",
}
ROUTINE_COMPUTED = {
    "currency": "USD",
    "total_minor": 118000,
    "words_minor": 118000,
    "issue_date": date(2026, 9, 30),
    "due_date": date(2026, 10, 30),
    "invoice_number_norm": "CR20260930",
    "usd_minor": 118000,
}


def build_facts(
    invoice_id: str = "OCT-01",
    *,
    received: datetime = datetime(2026, 10, 1, 14, 0, tzinfo=UTC),
    doc_sha256: str | None = None,
    printed: dict[str, str | None] | None = None,
    stamps: tuple[str, ...] = (),
    computed: dict[str, Any] | None = None,
    flags: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> InvoiceFacts:
    """Routine facts for BEN-10; every override names what the test changes."""
    values = {**ROUTINE_PRINTED, **(printed or {})}
    fields = {
        k: Field(value=v, quote=v, confidence=Confidence.HIGH, grounded=True, agreed=True)
        for k, v in values.items()
    }
    return InvoiceFacts(
        source=Source(
            invoice_id=invoice_id,
            doc_sha256=doc_sha256 or invoice_id.encode().hex().ljust(64, "0"),
            channel=Channel.PDF,
            received_at=received,
        ),
        as_of=date(2026, 10, 17),
        printed=Printed(stamps=stamps, **fields),
        computed=Computed(**{**ROUTINE_COMPUTED, **(computed or {})}),
        flags=Flags(**(flags or {})),
        verification=Verification(**{"risk": 0.1, **(verification or {})}),
    )


def build_entry(invoice_id: str = "SEP-01", **kw: Any) -> LedgerEntry:
    """A ledger row for BEN-10, paid; override what the test needs."""
    base: dict[str, Any] = {
        "invoice_id": invoice_id,
        "beneficiary_id": "BEN-10",
        "invoice_number_norm": "CR20260831",
        "fiscal_id_norm": None,
        "doc_sha256": invoice_id.encode().hex().ljust(64, "f"),
        "amount_minor": 118000,
        "currency": "USD",
        "usd_minor": 118000,
        "period": "2026-08",
        "received": date(2026, 9, 1),
        "decided": date(2026, 10, 3),
        "cost_center": "software",
        "status": Status.PAID,
    }
    return LedgerEntry(**{**base, **kw})


@pytest.fixture(scope="session")
def world() -> World:
    return load_world()


@pytest.fixture(scope="session")
def cfg() -> RulesConfig:
    return load_rules()


@pytest.fixture
def ledger() -> MemoryLedger:
    return MemoryLedger()


@pytest.fixture(scope="session")
def make_facts():
    """Builder for routine BEN-10 facts; tests override what they change."""
    return build_facts


@pytest.fixture(scope="session")
def entry():
    """Builder for a paid BEN-10 ledger row."""
    return build_entry
