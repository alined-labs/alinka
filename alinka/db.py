"""Postgres access: a psycopg 3 pool, plain SQL migrations, and one transaction per decision.

    uv run python -m alinka.db migrate

Each decision takes a transaction-level advisory lock on its session, reads the ledger,
decides, then inserts the ledger rows and the hash-chained record. A unique violation on
the ledger (same beneficiary and number, or same document) becomes an R03 HOLD.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psycopg
import rfc8785
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from alinka.audit.reasons import reason_es
from alinka.decide.ledger import LedgerEntry, Status
from alinka.money import format_minor
from alinka.settings import get_settings
from alinka.types import Decision, DecisionRecord, Outcome, RuleResult

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
ZERO_HASH = "0" * 64

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=8,
            timeout=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection(pool: ConnectionPool | None = None) -> Iterator[psycopg.Connection]:
    with (pool or get_pool()).connection() as conn:
        yield conn


# --- Migrations -----------------------------------------------------------------


def migrate(conninfo: str | None = None) -> list[str]:
    """Apply every migrations/*.sql not yet applied, in name order. Returns the new ones."""
    applied: list[str] = []
    with psycopg.connect(conninfo or get_settings().database_url) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('alinka.migrate', 0))")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.name in done:
                    continue
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
                applied.append(path.name)
    return applied


# --- The chain --------------------------------------------------------------------


def record_bytes(record: DecisionRecord) -> bytes:
    """RFC 8785 bytes of the record without its hash: what the chain signs and stores."""
    body = record.model_dump(mode="json")
    body.pop("hash")
    return rfc8785.dumps(body)


def chain_hash(prev_hash: str, canonical: bytes) -> str:
    return hashlib.sha256(prev_hash.encode() + canonical).hexdigest()


def seal(record: DecisionRecord, session_id: str, seq: int, prev_hash: str) -> DecisionRecord:
    """Place the record in the session's chain and compute its hash."""
    draft = record.model_copy(
        update={
            "session": session_id,
            "seq": seq,
            "prev_hash": prev_hash,
            "record_id": f"{session_id}-{seq:04d}",
            "hash": "",
        }
    )
    return draft.model_copy(update={"hash": chain_hash(prev_hash, record_bytes(draft))})


# --- The ledger -------------------------------------------------------------------


LEDGER_COLUMNS = tuple(LedgerEntry.__dataclass_fields__)


def read_ledger(conn: psycopg.Connection, session_id: str) -> list[LedgerEntry]:
    rows = conn.execute(
        f"SELECT {', '.join(LEDGER_COLUMNS)} FROM ledger WHERE session_id = %s ORDER BY id",
        (session_id,),
    ).fetchall()
    return [LedgerEntry(**(r | {"status": Status(r["status"])})) for r in rows]


def insert_ledger(conn: psycopg.Connection, session_id: str, row: LedgerEntry) -> None:
    values = {k: str(v) if k == "status" else v for k, v in asdict(row).items()}
    conn.execute(
        f"INSERT INTO ledger (session_id, {', '.join(values)})"
        f" VALUES (%s, {', '.join(['%s'] * len(values))})",
        (session_id, *values.values()),
    )


def set_ledger_status(conn: psycopg.Connection, session_id: str, invoice_id: str, status: str):
    conn.execute(
        "UPDATE ledger SET status = %s WHERE session_id = %s AND invoice_id = %s",
        (str(status), session_id, invoice_id),
    )


def head(conn: psycopg.Connection, session_id: str) -> tuple[int, str]:
    """The last sequence number and hash of a session's chain (0 and zeros when empty)."""
    row = conn.execute(
        "SELECT seq, hash FROM decisions WHERE session_id = %s ORDER BY seq DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return (row["seq"], row["hash"]) if row else (0, ZERO_HASH)


def insert_record(conn: psycopg.Connection, record: DecisionRecord) -> None:
    conn.execute(
        "INSERT INTO decisions (session_id, seq, record_id, prev_hash, hash, canonical,"
        " decision, invoice_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            record.session,
            record.seq,
            record.record_id,
            record.prev_hash,
            record.hash,
            record_bytes(record),
            record.decision.value,
            record.invoice_id,
            record.created_at,
        ),
    )


def lock_session(conn: psycopg.Connection, session_id: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (session_id,))


def as_duplicate(record: DecisionRecord, earlier: dict | None, by: str) -> DecisionRecord:
    """The record a ledger unique violation turns into: Frenada by R03, nothing to pay.

    `by` is the constraint that fired: the same number from the same beneficiary, or the
    same document. The values feed Lane A's R03 templates, so the reason cites them.
    """
    printed = record.facts.printed
    values: dict[str, str | None] = {
        "invoice_number": printed.invoice_number.value or record.invoice_id,
        "beneficiary": record.payment.beneficiary_name
        if record.payment
        else printed.beneficiary_name.value,
        "earlier_invoice": earlier["invoice_id"] if earlier else None,
        "earlier_status": earlier["status"] if earlier else None,
        "earlier_date": earlier["decided"].isoformat() if earlier else None,
        "earlier_amount": format_minor(earlier["amount_minor"], earlier["currency"])
        if earlier
        else None,
    }
    key = "R03.duplicate_document" if by == "ledger_document_unique" else "R03.duplicate_number"
    results = tuple(
        RuleResult(rule="R03", outcome=Outcome.HOLD, values=values, message_key=key)
        if r.rule == "R03"
        else r
        for r in record.results
    )
    return record.model_copy(
        update={
            "decision": Decision.HOLD,
            "determining_rule": "R03",
            "results": results,
            "reason_es": reason_es(Decision.HOLD, "R03", results, record.human),
            "payment": None,
        }
    )


DecideFn = Callable[[list[LedgerEntry]], tuple[DecisionRecord, list[LedgerEntry]]]


def record_decision(
    session_id: str,
    decide: DecideFn,
    conn: psycopg.Connection,
    marks: list[float] | None = None,
) -> DecisionRecord:
    """Decide one invoice in one transaction on `conn` and return the sealed record.

    `decide` gets the session's ledger and returns the record (chain fields are filled
    here) and the ledger rows to write with it. `marks`, when given, gets the
    perf_counter times after deciding, after the ledger write and after the commit.
    """
    mark = marks.append if marks is not None else (lambda _: None)
    with conn.transaction():
        lock_session(conn, session_id)
        record, rows = decide(read_ledger(conn, session_id))
        mark(time.perf_counter())
        try:
            with conn.transaction():  # a savepoint, so a conflict leaves the outer one usable
                for row in rows:
                    insert_ledger(conn, session_id, row)
        except errors.UniqueViolation as exc:
            earlier = earliest_conflict(conn, session_id, rows)
            record = as_duplicate(record, earlier, exc.diag.constraint_name or "")
        mark(time.perf_counter())
        seq, prev = head(conn, session_id)
        sealed = seal(record, session_id, seq + 1, prev)
        insert_record(conn, sealed)
    mark(time.perf_counter())
    return sealed


def earliest_conflict(conn: psycopg.Connection, session_id: str, rows: list[LedgerEntry]):
    for row in rows:
        hit = conn.execute(
            "SELECT invoice_id, status, decided, amount_minor, currency FROM ledger"
            " WHERE session_id = %s AND (doc_sha256 = %s"
            " OR (beneficiary_id = %s AND invoice_number_norm = %s)) ORDER BY id LIMIT 1",
            (session_id, row.doc_sha256, row.beneficiary_id, row.invoice_number_norm),
        ).fetchone()
        if hit:
            return hit
    return None


def load_records(conn: psycopg.Connection, session_id: str) -> list[DecisionRecord]:
    """Every record of a session in chain order, rebuilt from the stored canonical bytes."""
    rows = conn.execute(
        "SELECT hash, canonical FROM decisions WHERE session_id = %s ORDER BY seq", (session_id,)
    ).fetchall()
    return [
        DecisionRecord.model_validate({**json.loads(r["canonical"]), "hash": r["hash"]})
        for r in rows
    ]


def chain_rows(conn: psycopg.Connection, session_id: str) -> list[tuple[int, str, str, bytes]]:
    rows = conn.execute(
        "SELECT seq, prev_hash, hash, canonical FROM decisions WHERE session_id = %s ORDER BY seq",
        (session_id,),
    ).fetchall()
    return [(r["seq"], r["prev_hash"], r["hash"], bytes(r["canonical"])) for r in rows]


def setting(conn: psycopg.Connection, key: str, default: Any = None) -> Any:
    """A value from the settings table, read on every request so a switch needs no redeploy."""
    row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: psycopg.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())"
        " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (key, Jsonb(value)),
    )


def main(argv: list[str]) -> int:
    if argv[:1] == ["migrate"]:
        applied = migrate()
        print("applied: " + (", ".join(applied) if applied else "nothing new"))
        return 0
    print("usage: python -m alinka.db migrate", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
