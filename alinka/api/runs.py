"""Recorded InvoiceFacts runs: data/runs/<name>/*.jsonl from Lane C, or the API fixtures."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from alinka.types import InvoiceFacts

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data" / "runs"
FIXTURE_RUN = "fixture"
FIXTURE_FACTS = Path(__file__).resolve().parent / "fixtures" / "facts.jsonl"


def _parse(line: str) -> InvoiceFacts | None:
    raw = json.loads(line)
    if "source" not in raw:  # a wrapper such as {"facts": {...}, "latency_ms": ...}
        raw = raw.get("facts")
    return InvoiceFacts.model_validate(raw) if raw else None


@lru_cache(maxsize=16)
def load_facts(name: str) -> tuple[InvoiceFacts, ...]:
    """Every invoice of a run in received order; the last line wins for a repeated invoice."""
    if name == FIXTURE_RUN:
        lines = FIXTURE_FACTS.read_text().splitlines()
    else:
        run = (RUNS / name).resolve()
        if run.parent != RUNS.resolve() or not run.is_dir():
            raise FileNotFoundError(f"no run named {name!r} in data/runs/")
        lines = [x for f in sorted(run.glob("*.jsonl")) for x in f.read_text().splitlines()]
    facts: dict[str, InvoiceFacts] = {}
    for line in lines:
        if line.strip() and (f := _parse(line)) is not None:
            facts[f.source.invoice_id] = f
    return tuple(sorted(facts.values(), key=lambda f: (f.source.received_at, f.source.invoice_id)))


PREFERRED_RUN = "showcase"  # the October month, the board the demo opens on


def default_run() -> str:
    """data/runs/showcase when recorded, else the fixtures. Other runs load only by name."""
    if any((RUNS / PREFERRED_RUN).glob("*.jsonl")):
        return PREFERRED_RUN
    return FIXTURE_RUN
