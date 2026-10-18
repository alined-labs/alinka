"""D2: migrations, the hash chain over stored bytes, and the one-transaction decision."""

import threading
from datetime import UTC, date, datetime

import pytest

from alinka import db
from alinka.decide.ledger import LedgerEntry, Status
from alinka.types import (
    RULE_IDS,
    Channel,
    Computed,
    Decision,
    DecisionRecord,
    Field,
    InvoiceFacts,
    Outcome,
    Printed,
    RuleResult,
    Source,
)

pytestmark = pytest.mark.db


def record(invoice_id: str, number: str, sha: str) -> DecisionRecord:
    facts = InvoiceFacts(
        source=Source(
            invoice_id=invoice_id,
            doc_sha256=sha,
            channel=Channel.PDF,
            received_at=datetime(2026, 10, 1, tzinfo=UTC),
        ),
        as_of=date(2026, 10, 17),
        printed=Printed(invoice_number=Field(value=number)),
        computed=Computed(currency="USD", total_minor=50000, usd_minor=50000),
    )
    return DecisionRecord(
        record_id="draft",
        session="draft",
        seq=0,
        prev_hash="",
        hash="",
        invoice_id=invoice_id,
        decision=Decision.PAY,
        results=tuple(RuleResult(rule=r, outcome=Outcome.PASS, message_key="ok") for r in RULE_IDS),
        reason_es="Pagada: cumple las 16 reglas.",
        facts=facts,
        rules_version="t",
        rules_hash="0" * 64,
        as_of=date(2026, 10, 17),
        code_version="test",
        created_at=datetime(2026, 10, 17, tzinfo=UTC),
    )


def row(invoice_id: str, number: str, sha: str) -> LedgerEntry:
    return LedgerEntry(
        invoice_id=invoice_id,
        beneficiary_id="BEN-10",
        invoice_number_norm=number,
        fiscal_id_norm=None,
        doc_sha256=sha,
        amount_minor=50000,
        currency="USD",
        usd_minor=50000,
        period="2026-10",
        received=date(2026, 10, 1),
        decided=date(2026, 10, 17),
        cost_center="software",
        status=Status.PAID,
    )


def new_session(pool, sid: str) -> None:
    with pool.connection() as conn:
        conn.execute("INSERT INTO sessions (id, kind) VALUES (%s, 'sandbox')", (sid,))


def decide_pay(invoice_id: str, number: str, sha: str):
    return lambda ledger: (record(invoice_id, number, sha), [row(invoice_id, number, sha)])


def test_migrate_is_idempotent(db_url):
    assert db.migrate(db_url) == []


def test_chain_round_trips_through_stored_bytes(pool):
    new_session(pool, "s-chain")
    with pool.connection() as conn:
        a = db.record_decision("s-chain", decide_pay("OCT-01", "A1", "a" * 64), conn)
        b = db.record_decision("s-chain", decide_pay("OCT-02", "A2", "b" * 64), conn)
        assert (a.seq, b.seq, b.prev_hash) == (1, 2, a.hash)
        assert db.load_records(conn, "s-chain") == [a, b]
        rows = db.chain_rows(conn, "s-chain")
    prev = db.ZERO_HASH
    for _, prev_hash, digest, canonical in rows:
        assert prev_hash == prev and db.chain_hash(prev, canonical) == digest
        prev = digest


def test_unique_violation_becomes_r03(pool):
    new_session(pool, "s-dup")
    with pool.connection() as conn:
        db.record_decision("s-dup", decide_pay("OCT-01", "N1", "c" * 64), conn)
        dup = db.record_decision("s-dup", decide_pay("OCT-09", "N1", "d" * 64), conn)
        same_doc = db.record_decision("s-dup", decide_pay("OCT-10", "N2", "c" * 64), conn)
        ledger = db.read_ledger(conn, "s-dup")
    for r in (dup, same_doc):
        assert r.decision == Decision.HOLD and r.determining_rule == "R03" and r.payment is None
        assert "OCT-01" in r.reason_es
    assert [(x.invoice_id, x.status) for x in ledger] == [("OCT-01", Status.PAID)]


def test_concurrent_duplicates_pay_once(pool):
    new_session(pool, "s-race")
    out: list[DecisionRecord] = []

    def worker(i: int) -> None:
        with pool.connection() as conn:
            out.append(
                db.record_decision("s-race", decide_pay(f"X-{i}", "SAME", f"{i}" * 64), conn)
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.decision.value for r in out) == ["HOLD", "HOLD", "HOLD", "PAY"]
    assert sorted(r.seq for r in out) == [1, 2, 3, 4]


def test_sessions_cascade(pool):
    new_session(pool, "s-gone")
    with pool.connection() as conn:
        db.record_decision("s-gone", decide_pay("OCT-01", "Z", "e" * 64), conn)
        conn.execute("DELETE FROM sessions WHERE id = 's-gone'")
        assert db.head(conn, "s-gone") == (0, db.ZERO_HASH)
        assert db.read_ledger(conn, "s-gone") == []
