"""Sessions in Postgres: the read-only canonical run and one private sandbox per visitor."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import psycopg
import yaml
from psycopg.types.json import Jsonb

from alinka import db
from alinka.api import engine, runs
from alinka.api.models import RunStep, View
from alinka.types import Beneficiary, DecisionRecord, HumanAction, InvoiceFacts, RulesConfig
from alinka.world import World, load_rules, load_world, rules_hash

CANONICAL = "canonical"
SANDBOX_TTL = timedelta(hours=24)


class Refused(Exception):
    """A request the rules don't allow (shown to the user as a 409)."""


class NotFound(Exception):
    pass


@lru_cache
def base_world() -> World:
    return load_world()


@dataclass(frozen=True)
class Ctx:
    session_id: str
    view: View
    run_name: str
    rules: RulesConfig
    world: World
    added: tuple[str, ...] = ()  # beneficiary IDs added in this sandbox
    tried: tuple[InvoiceFacts, ...] = ()  # invoices run from Probar in this sandbox

    @property
    def facts(self) -> tuple[InvoiceFacts, ...]:
        base = runs.load_facts(self.run_name)
        if not self.tried:
            return base
        return tuple(
            sorted((*base, *self.tried), key=lambda f: (f.source.received_at, f.source.invoice_id))
        )


# --- Creating sessions ------------------------------------------------------------


def _insert_session(conn, sid: str, kind: str, run_name: str, rules: RulesConfig) -> None:
    expires = datetime.now(UTC) + SANDBOX_TTL if kind == "sandbox" else None
    conn.execute(
        "INSERT INTO sessions (id, kind, run_name, expires_at) VALUES (%s, %s, %s, %s)",
        (sid, kind, run_name, expires),
    )
    save_rules(conn, sid, rules)


def load_canonical(conn: psycopg.Connection, run_name: str) -> str | None:
    """Replace the canonical session with `run_name`, decided in received order.

    Returns the head hash. Sandboxes are separate sessions and are left alone.
    """
    with conn.transaction():
        db.lock_session(conn, CANONICAL)
        conn.execute("DELETE FROM sessions WHERE id = %s", (CANONICAL,))
        _insert_session(conn, CANONICAL, "canonical", run_name, load_rules())
    ctx = context(conn, CANONICAL)
    assert ctx is not None
    decide_all(conn, ctx, [f.source.invoice_id for f in ctx.facts])
    return db.head(conn, CANONICAL)[1] if ctx.facts else None


def ensure_canonical(conn: psycopg.Connection) -> Ctx:
    ctx = context(conn, CANONICAL)
    if ctx is None:
        load_canonical(conn, runs.default_run())
        ctx = context(conn, CANONICAL)
    assert ctx is not None
    return ctx


def create_sandbox(conn: psycopg.Connection, sid: str | None = None) -> Ctx:
    """A fresh sandbox: the canonical run's inputs and rules, with the inbox full."""
    canon = ensure_canonical(conn)
    sid = sid or secrets.token_urlsafe(18)
    with conn.transaction():
        conn.execute("DELETE FROM sessions WHERE kind = 'sandbox' AND expires_at < now()")
        conn.execute("DELETE FROM sessions WHERE id = %s AND kind = 'sandbox'", (sid,))
        _insert_session(conn, sid, "sandbox", canon.run_name, canon.rules)
    ctx = context(conn, sid)
    assert ctx is not None
    return ctx


def context(conn: psycopg.Connection, sid: str) -> Ctx | None:
    """The session's run, current rules and world; None when missing or expired."""
    row = conn.execute(
        "SELECT kind, run_name FROM sessions WHERE id = %s"
        " AND (expires_at IS NULL OR expires_at > now())",
        (sid,),
    ).fetchone()
    if row is None:
        return None
    rules = conn.execute(
        "SELECT rules_yaml FROM rule_versions WHERE session_id = %s ORDER BY id DESC LIMIT 1",
        (sid,),
    ).fetchone()
    added = [
        Beneficiary.model_validate(r["beneficiary"])
        for r in conn.execute(
            "SELECT beneficiary FROM sandbox_beneficiaries WHERE session_id = %s"
            " ORDER BY created_at, beneficiary_id",
            (sid,),
        )
    ]
    tried = tuple(
        InvoiceFacts.model_validate(r["facts"])
        for r in conn.execute(
            "SELECT facts FROM try_invoices WHERE session_id = %s ORDER BY created_at, invoice_id",
            (sid,),
        )
    )
    world = base_world()
    for ben in added:
        world = world.with_beneficiary(ben)
    return Ctx(
        session_id=sid,
        view="canonical" if row["kind"] == "canonical" else "sandbox",
        run_name=row["run_name"],
        rules=RulesConfig.model_validate(yaml.safe_load(rules["rules_yaml"])),
        world=world,
        added=tuple(b.id for b in added),
        tried=tried,
    )


# --- Rules and beneficiaries --------------------------------------------------------


def save_rules(conn: psycopg.Connection, sid: str, rules: RulesConfig) -> None:
    conn.execute(
        "INSERT INTO rule_versions (session_id, rules_yaml, hash) VALUES (%s, %s, %s)",
        (sid, yaml.safe_dump(rules.model_dump(mode="json"), sort_keys=False), rules_hash(rules)),
    )


def add_beneficiary(conn: psycopg.Connection, sid: str, ben: Beneficiary) -> None:
    conn.execute(
        "INSERT INTO sandbox_beneficiaries (session_id, beneficiary_id, beneficiary)"
        " VALUES (%s, %s, %s)",
        (sid, ben.id, Jsonb(ben.model_dump(mode="json"))),
    )


def add_tried(
    conn: psycopg.Connection,
    sid: str,
    facts: InvoiceFacts,
    sample_id: str | None,
    document: bytes | None = None,
    filename: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO try_invoices (session_id, invoice_id, sample_id, facts, document, filename)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (
            sid, facts.source.invoice_id, sample_id, Jsonb(facts.model_dump(mode="json")),
            document, filename,
        ),
    )  # fmt: skip


def uploaded(conn: psycopg.Connection, sid: str, invoice_id: str) -> tuple[bytes, str] | None:
    """An uploaded document's bytes and file name, for its page images."""
    row = conn.execute(
        "SELECT document, filename FROM try_invoices"
        " WHERE session_id = %s AND invoice_id = %s AND document IS NOT NULL",
        (sid, invoice_id),
    ).fetchone()
    return (bytes(row["document"]), row["filename"] or "") if row else None


def tried_count(conn: psycopg.Connection, sid: str, prefix: str) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM try_invoices WHERE session_id = %s AND invoice_id LIKE %s",
        (sid, prefix + "%"),
    ).fetchone()
    return row["n"]


# --- Deciding -----------------------------------------------------------------------


def records(conn: psycopg.Connection, sid: str) -> list[DecisionRecord]:
    return db.load_records(conn, sid)


def latest(recs: list[DecisionRecord]) -> dict[str, DecisionRecord]:
    """The last record per invoice: an approval appends a record after the escalation."""
    return {r.invoice_id: r for r in recs}


def decide_all(conn: psycopg.Connection, ctx: Ctx, invoice_ids: list[str]) -> list[RunStep]:
    """Decide the given invoices in received order, one transaction each."""
    wanted = set(invoice_ids)
    steps = []
    for facts in ctx.facts:
        if facts.source.invoice_id not in wanted:
            continue
        t0 = time.perf_counter()
        rec = db.record_decision(
            ctx.session_id,
            lambda ledger, f=facts: engine.decide(f, ctx.world, ctx.rules, ledger),
            conn,
        )
        steps.append(
            RunStep(
                invoice_id=rec.invoice_id,
                decision=rec.decision,
                determining_rule=rec.determining_rule,
                elapsed_ms=round((time.perf_counter() - t0) * 1000),
            )
        )
    return steps


def run_inbox(conn: psycopg.Connection, ctx: Ctx) -> list[RunStep]:
    """Ejecutar agente: every invoice of the sandbox not decided yet."""
    done = latest(records(conn, ctx.session_id))
    return decide_all(
        conn, ctx, [f.source.invoice_id for f in ctx.facts if f.source.invoice_id not in done]
    )


def redecide(conn: psycopg.Connection, sid: str) -> None:
    """Start the sandbox's chain and ledger over and decide again what had been decided."""
    if sid == CANONICAL:
        raise Refused("La ejecución canónica es de solo lectura.")
    decided = list(latest(records(conn, sid)))
    with conn.transaction():
        db.lock_session(conn, sid)
        conn.execute("DELETE FROM ledger WHERE session_id = %s", (sid,))
        conn.execute("DELETE FROM decisions WHERE session_id = %s", (sid,))
    ctx = context(conn, sid)
    assert ctx is not None
    decide_all(conn, ctx, decided)


def act(conn: psycopg.Connection, ctx: Ctx, invoice_id: str, human: HumanAction) -> DecisionRecord:
    """Approve or reject one escalation in a single transaction under the session lock."""
    if ctx.view != "sandbox":
        raise Refused("Las aprobaciones solo existen en tu sandbox.")
    with conn.transaction():
        db.lock_session(conn, ctx.session_id)
        rec = latest(records(conn, ctx.session_id)).get(invoice_id)
        if rec is None:
            if not any(f.source.invoice_id == invoice_id for f in ctx.facts):
                raise NotFound(f"No existe la factura {invoice_id}.")
            raise Refused(f"La factura {invoice_id} aún no tiene decisión.")
        try:
            new, statuses = engine.act(
                rec, human, ctx.world, ctx.rules, db.read_ledger(conn, ctx.session_id)
            )
        except engine.Refused as exc:
            raise Refused(str(exc)) from exc
        for inv, status in statuses.items():
            db.set_ledger_status(conn, ctx.session_id, inv, status)
        seq, prev = db.head(conn, ctx.session_id)
        sealed = db.seal(new, ctx.session_id, seq + 1, prev)
        db.insert_record(conn, sealed)
    return sealed
