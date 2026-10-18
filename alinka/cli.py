"""The `alinka` command: decide, batch, verify and export-csv. No model calls happen here."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from alinka.audit.chain import stored_bytes, verify_chain
from alinka.audit.export import export_csv
from alinka.decide.core import Session, batch, record_decision
from alinka.decide.ledger import MemoryLedger
from alinka.types import DecisionRecord, InvoiceFacts
from alinka.world import DATA, load_rules, load_run_dir, load_world

ROOT = Path(__file__).resolve().parents[1]


def _session(name: str, rules: Path) -> Session:
    return Session(name, load_world(), load_rules(rules), MemoryLedger())


def _line(r: DecisionRecord) -> str:
    rule = f" {r.determining_rule}" if r.determining_rule else ""
    return f"{r.invoice_id}\t{r.decision.value}{rule}\t{r.reason_es}"


def read_records(path: Path) -> list[bytes]:
    return [line for line in path.read_bytes().split(b"\n") if line.strip()]


def cmd_decide(args: argparse.Namespace) -> int:
    facts = InvoiceFacts.model_validate_json(Path(args.facts).read_text())
    record = record_decision(_session(args.session, args.rules), facts)
    print(stored_bytes(record).decode() if args.json else _line(record))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    run = Path(args.run_dir)
    items = load_run_dir(run)
    if not items:
        print(f"sin facts en {run}", file=sys.stderr)
        return 1
    session = _session(args.session, args.rules)
    records = batch(session, items)
    out = Path(args.out) if args.out else ROOT / "runs" / "decisions" / f"{run.name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"".join(stored_bytes(r) + b"\n" for r in records))
    for r in records:
        print(_line(r))
    counts = {d: sum(r.decision == d for r in records) for d in ("PAY", "HOLD", "ESCALATE")}
    print(f"{len(records)} decisiones: {counts}; cabeza {session.head}; registros en {out}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    check = verify_chain(read_records(Path(args.records)))
    if check.ok:
        print(f"OK: {check.count} registros, cabeza {check.head}")
        return 0
    print(f"FALLA en el registro {check.bad_seq}: {check.error}", file=sys.stderr)
    return 1


def cmd_export_csv(args: argparse.Namespace) -> int:
    records = [DecisionRecord.model_validate_json(b) for b in read_records(Path(args.records))]
    text = export_csv(records)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alinka", description="La IA lee, las reglas deciden, el registro explica."
    )
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decide", help="decide one InvoiceFacts JSON file")
    d.add_argument("facts")
    d.add_argument("--json", action="store_true", help="print the full record")
    d.set_defaults(func=cmd_decide)

    b = sub.add_parser("batch", help="decide a run directory of facts JSONL in received order")
    b.add_argument("run_dir")
    b.add_argument("--out", help="records JSONL (default runs/decisions/<run>.jsonl)")
    b.set_defaults(func=cmd_batch)

    for sp in (d, b):
        sp.add_argument("--rules", type=Path, default=DATA / "rules.yaml")
        sp.add_argument("--session", default="canonical")

    v = sub.add_parser("verify", help="check the hash chain of a records JSONL")
    v.add_argument("records")
    v.set_defaults(func=cmd_verify)

    e = sub.add_parser("export-csv", help="the reconciliation CSV of a records JSONL")
    e.add_argument("records")
    e.add_argument("--out")
    e.set_defaults(func=cmd_export_csv)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
