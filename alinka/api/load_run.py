"""Load a recorded run as the read-only canonical session and print its head hash.

    uv run python -m alinka.api.load_run <name>     # data/runs/<name>/*.jsonl
    uv run python -m alinka.api.load_run fixture    # the API's hand-written facts

Sandboxes already open keep their copy; new ones copy the run loaded here.
"""

from __future__ import annotations

import argparse
import sys

from alinka import db
from alinka.api import runs, sessions


def load(name: str, migrate: bool = True) -> tuple[str | None, int]:
    if migrate:
        db.migrate()
    facts = runs.load_facts(name)
    with db.connection() as conn:
        head = sessions.load_canonical(conn, name)
    return head, len(facts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alinka.api.load_run", description=__doc__)
    parser.add_argument("name", nargs="?", default=None, help="run name; default: the newest")
    parser.add_argument("--no-migrate", action="store_true", help="skip applying migrations")
    args = parser.parse_args(argv)
    name = args.name or runs.default_run()
    try:
        head, n = load(name, migrate=not args.no_migrate)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"canonical run {name}: {n} invoices decided")
    print(f"head {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
