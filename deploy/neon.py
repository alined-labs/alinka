"""Prepare Neon for the deploy (P2): apply the migrations, then load the canonical run.

    uv run python deploy/neon.py [run]      # default: the newest recorded run (showcase)

DATABASE_URL in .env is Neon's pooled string, which the API uses. Migrations and the bulk
load go to the direct endpoint instead (the same host without -pooler), as Neon advises.
Prints what it applied and the canonical head hash, never the connection string.
"""

from __future__ import annotations

import os
import sys

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from alinka.settings import Settings, get_settings


def direct_url(url: str) -> str:
    """Neon's direct endpoint for a pooled connection string; any other URL unchanged."""
    params = conninfo_to_dict(url)
    host = params.get("host") or ""
    if "-pooler." not in host:
        return url
    return make_conninfo(**{**params, "host": host.replace("-pooler.", ".", 1)})


def main(argv: list[str]) -> int:
    url = Settings().database_url
    neon = (conninfo_to_dict(url).get("host") or "").endswith(".neon.tech")
    print("database: Neon, direct endpoint" if neon else "database: not Neon")
    os.environ["DATABASE_URL"] = direct_url(url)  # this process only
    get_settings.cache_clear()

    from alinka import db
    from alinka.api import load_run

    if db.main(["migrate"]) != 0:
        return 1
    return load_run.main([*argv, "--no-migrate"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
