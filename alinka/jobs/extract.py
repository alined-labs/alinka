"""Extract InvoiceFacts for a split of the dataset.

    uv run python -m alinka.jobs.extract --split showcase --mode replay
    uv run python -m alinka.jobs.extract --split all --shard 1/2 --concurrency 3 --mode record
    uv run python -m alinka.jobs.extract --split all --mode replay --jev off --publish all-jev-off

Writes runs/<run_id>/facts-<i>of<N>.jsonl (one InvoiceFacts per line, in finishing
order) and summary-<i>of<N>.json (flags, latency and cost). Invoices already in the
shard's facts file without an extraction error are skipped, so an interrupted run
resumes and failed invoices are retried (the last line for an invoice wins). `--publish NAME` merges
every shard of the run into data/runs/NAME/, which the API and the evaluation load.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from alinka.cache import ResponseCache
from alinka.settings import get_settings
from alinka.types import InvoiceFacts, Label
from alinka.verify.facts import facts_for_path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labels"
RUNS = ROOT / "runs"
PUBLISHED = ROOT / "data" / "runs"
SPLITS = ("showcase", "generated", "attack")


def load_labels(split: str) -> list[Label]:
    names = SPLITS if split == "all" else (split,)
    labels: list[Label] = []
    for name in names:
        path = LABELS / f"{name}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                labels.append(Label.model_validate_json(line))
    return sorted(labels, key=lambda label: label.invoice_id)


def shard_of(labels: list[Label], i: int, n: int) -> list[Label]:
    return [label for k, label in enumerate(labels) if k % n == i - 1]


def _done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: dict[str, bool] = {}  # invoice -> finished without an extraction error
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            done[raw["source"]["invoice_id"]] = not raw["flags"]["extraction_error"]
    return {invoice for invoice, ok in done.items() if ok}  # errors are retried


def run(
    split: str,
    *,
    mode: str,
    shard: tuple[int, int] = (1, 1),
    concurrency: int = 3,
    run_id: str | None = None,
    jev: bool | None = None,
    limit: int | None = None,
    runs_dir: Path = RUNS,
) -> Path:
    settings = get_settings()
    if jev is not None:
        settings.jev_enabled = jev
    run_id = run_id or f"{split}-{mode}-jev{'on' if settings.jev_enabled else 'off'}"
    out = runs_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    i, n = shard
    facts_path = out / f"facts-{i}of{n}.jsonl"
    summary_path = out / f"summary-{i}of{n}.json"
    labels = shard_of(load_labels(split), i, n)[:limit]
    done = _done(facts_path)
    todo = [label for label in labels if label.invoice_id not in done]
    cache = ResponseCache(mode)  # type: ignore[arg-type]
    lock = threading.Lock()
    print(f"{run_id} shard {i}/{n}: {len(todo)} to do, {len(done)} already done", flush=True)

    def one(label: Label) -> None:
        start = time.perf_counter()
        facts, _ = facts_for_path(
            ROOT / label.path, invoice_id=label.invoice_id, received_at=label.received_at,
            cache=cache,
        )  # fmt: skip
        wall_ms = round((time.perf_counter() - start) * 1000)
        line = facts.model_dump_json()
        with lock:
            with facts_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            _status(facts, wall_ms)

    with ThreadPoolExecutor(max_workers=max(concurrency, 1)) as pool:
        for future in [pool.submit(one, label) for label in todo]:
            future.result()

    summary = summarize(_read(facts_path), split=split, mode=mode, jev=settings.jev_enabled)
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "invoices_detail"}), flush=True)
    return out


def _status(facts: InvoiceFacts, wall_ms: int) -> None:
    v, fl = facts.verification, facts.flags
    alerts = len(fl.hidden_content) + len(fl.unicode_controls) + len(fl.instructions)
    alerts += len(fl.reader_instructions) + int(fl.html_text_mismatch)
    error = f" ERROR {fl.extraction_error[:80]}" if fl.extraction_error else ""
    print(
        f"  {facts.source.invoice_id:<12} {wall_ms:>6} ms  risk {v.risk:.2f}  alerts {alerts}{error}",
        flush=True,
    )


def _read(path: Path) -> list[InvoiceFacts]:
    by_id: dict[str, InvoiceFacts] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                facts = InvoiceFacts.model_validate_json(line)
                by_id[facts.source.invoice_id] = facts
    return sorted(by_id.values(), key=lambda f: f.source.invoice_id)


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def summarize(facts: list[InvoiceFacts], **meta) -> dict:
    """Per invoice: model latency (the recorded calls, so replay reports real numbers) and cost."""
    rows = []
    for f in facts:
        fl = f.flags
        rows.append(
            {
                "invoice_id": f.source.invoice_id,
                "channel": f.source.channel.value,
                "model_latency_ms": sum(c.latency_ms for c in f.calls),
                "cost_usd": round(sum(c.cost_usd for c in f.calls), 6),
                "risk": f.verification.risk,
                "extraction_error": fl.extraction_error,
                "hidden_content": len(fl.hidden_content),
                "unicode_controls": len(fl.unicode_controls),
                "html_text_mismatch": fl.html_text_mismatch,
                "instructions": len(fl.instructions),
                "reader_instructions": len(fl.reader_instructions),
            }
        )
    latencies = [r["model_latency_ms"] for r in rows]
    return {
        **meta,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "invoices": len(rows),
        "extraction_errors": sum(1 for r in rows if r["extraction_error"]),
        "flagged": sum(
            1
            for r in rows
            if r["hidden_content"]
            or r["unicode_controls"]
            or r["html_text_mismatch"]
            or r["instructions"]
            or r["reader_instructions"]
        ),  # fmt: skip
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "latency_ms_p50": _p(latencies, 0.5),
        "latency_ms_p95": _p(latencies, 0.95),
        "invoices_detail": rows,
    }


def publish(run_dir: Path, name: str, dest: Path = PUBLISHED) -> Path:
    """Merge every shard of a run into data/runs/<name>/facts.jsonl plus summary.json."""
    facts: dict[str, InvoiceFacts] = {}
    for path in sorted(run_dir.glob("facts-*.jsonl")):
        for f in _read(path):
            facts[f.source.invoice_id] = f
    ordered = sorted(facts.values(), key=lambda f: (f.source.received_at, f.source.invoice_id))
    target = dest / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with (target / "facts.jsonl").open("w", encoding="utf-8") as out:
        for f in ordered:
            out.write(f.model_dump_json() + "\n")
    meta = {}
    shard_summaries = sorted(run_dir.glob("summary-*.json"))
    if shard_summaries:
        first = json.loads(shard_summaries[0].read_text())
        meta = {k: first[k] for k in ("split", "mode", "jev") if k in first}
    summary = summarize(ordered, **meta, source_run=run_dir.name)
    (target / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    return target


def _shard(text: str) -> tuple[int, int]:
    i, n = (int(x) for x in text.split("/"))
    if not 1 <= i <= n:
        raise argparse.ArgumentTypeError("shard must be i/N with 1 <= i <= N")
    return i, n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alinka.jobs.extract", description=__doc__)
    parser.add_argument("--split", choices=(*SPLITS, "all"), required=True)
    parser.add_argument("--mode", choices=("record", "replay", "live"), default="replay")
    parser.add_argument("--shard", type=_shard, default=(1, 1), help="i/N, 1-based")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--jev", choices=("on", "off"), default=None, help="default: settings")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--publish", metavar="NAME", default=None, help="copy to data/runs/NAME")
    args = parser.parse_args(argv)
    out = run(
        args.split,
        mode=args.mode,
        shard=args.shard,
        concurrency=args.concurrency,
        run_id=args.run_id,
        jev=None if args.jev is None else args.jev == "on",
        limit=args.limit,
    )
    if args.publish:
        print(f"published {publish(out, args.publish).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
