"""Database fixtures: each test module gets its own throwaway database.

Tests marked `db` skip when Postgres is unreachable, unless ALINKA_REQUIRE_DB=1 (the hub).
"""

import os
import secrets
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from alinka import db
from alinka.settings import get_settings
from alinka.types import Decision


def _admin_url() -> str:
    return make_conninfo(get_settings().database_url, connect_timeout=3)


@pytest.fixture(scope="module")
def db_url() -> Iterator[str]:
    try:
        admin = psycopg.connect(_admin_url(), autocommit=True)
    except psycopg.OperationalError as exc:
        if os.environ.get("ALINKA_REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres unreachable: {exc.__class__.__name__}")
    name = f"alinka_test_{secrets.token_hex(4)}"
    admin.execute(f'CREATE DATABASE "{name}"')
    params = conninfo_to_dict(get_settings().database_url) | {"dbname": name}
    url = make_conninfo(**params)
    try:
        db.migrate(url)
        yield url
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture(scope="module")
def pool(db_url) -> Iterator[ConnectionPool]:
    p = ConnectionPool(db_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
    yield p
    p.close()


class FixtureCore:
    """Stands in for alinka.decide.core in API tests: replays the hand-written fixture records."""

    def __init__(self) -> None:
        from alinka.api import runs
        from alinka.types import DecisionRecord

        lines = runs.FIXTURE_RECORDS.read_text().splitlines()
        self.records = {
            r.invoice_id: r for r in (DecisionRecord.model_validate_json(x) for x in lines if x)
        }

    def decide(self, facts, world, ledger, rules):
        rec = self.records[facts.source.invoice_id]
        if rules.approval_threshold_usd < 1000 and rec.decision.value == "PAY":
            return rec.model_copy(
                update={
                    "decision": Decision.ESCALATE,
                    "determining_rule": "R06",
                    "payment": None,
                    "reason_es": "Pendiente (R06).",
                }
            )
        return rec.model_copy(update={"facts": facts, "rules_version": rules.version})

    def approve(self, record, human, world, ledger, rules):
        decision = Decision.PAY if human.action == "approve" else Decision.HOLD
        return record.model_copy(update={"decision": decision, "human": human})


@pytest.fixture
def client(pool, monkeypatch):
    """A TestClient on the module's throwaway database, with the fixture core."""
    from fastapi.testclient import TestClient

    from alinka.api import engine
    from alinka.api.app import app

    core = FixtureCore()
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(engine, "_core", lambda: core)
    with pool.connection() as conn:
        conn.execute("DELETE FROM sessions")
    return TestClient(app)
