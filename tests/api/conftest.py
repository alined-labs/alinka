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
