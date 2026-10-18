"""The evaluation (`make eval`): decide every labelled invoice from recorded facts, in replay.

Writes evals/report.json, EVAL_REPORT.md and evals/disagreements.csv. Exits 1 when any
invoice whose gold decision is not PAY was paid: the one number that must stay 0.

Facts come from a recorded run in data/runs/<name>/ (Lane C), or from the labels' gold
fields with --gold, which shows what the rules decide when the reading is perfect.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from alinka.decide.core import Session, batch
from alinka.decide.ledger import MemoryLedger
from alinka.money import parse_amount
from alinka.rules import norm_text
from alinka.types import Decision, DecisionRecord, InvoiceFacts, Label, Outcome, RulesConfig
from alinka.world import World, load_rules, load_world
from evals.gold import SIMULATED, gold_facts
from evals.stats import clopper_pearson_upper, percentile

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labels"
RUNS = ROOT / "data" / "runs"
OUT = ROOT / "evals"
EXPLANATIONS = OUT / "explanations.yaml"
THRESHOLDS = tuple(round(t * 0.05, 2) for t in range(1, 21))
AMOUNT_FIELDS = {"total", "subtotal", "tax_total"}


@dataclass
class Facts:
    facts: InvoiceFacts
    latency_ms: float | None = None
    cost_usd: float | None = None


def load_labels() -> list[Label]:
    labels = [
        Label.model_validate_json(line)
        for path in sorted(LABELS.glob("*.jsonl"))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    return sorted(labels, key=lambda lb: (lb.received_at, lb.invoice_id))


def load_run(run: Path) -> dict[str, Facts]:
    """Facts per invoice; wrapper lines may carry the job's latency_ms and cost_usd."""
    out: dict[str, Facts] = {}
    for path in sorted(run.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            meta = {} if "source" in raw else raw
            facts = InvoiceFacts.model_validate(raw if "source" in raw else raw["facts"])
            calls = facts.calls
            out[facts.source.invoice_id] = Facts(
                facts,
                meta.get("latency_ms", sum(c.latency_ms for c in calls) if calls else None),
                meta.get("cost_usd", sum(c.cost_usd for c in calls) if calls else None),
            )
    return out


def newest_run() -> Path | None:
    if not RUNS.is_dir():
        return None
    runs = [p for p in RUNS.iterdir() if p.is_dir() and any(p.glob("*.jsonl"))]
    runs = [p for p in runs if not p.name.endswith(("-nojev", "-jev-off"))]
    full = [p for p in runs if p.name == "all-jev-on"]  # Lane C's full run of all 175
    return full[0] if full else max(runs, key=lambda p: p.stat().st_mtime, default=None)


def jev_off_run(run: Path) -> Path | None:
    """The same documents read with JEV off: <run>-nojev, or *-jev-on paired with *-jev-off."""
    names = [f"{run.name}-nojev"]
    if run.name.endswith("-jev-on"):
        names.append(run.name.removesuffix("-jev-on") + "-jev-off")
    return next((run.parent / n for n in names if (run.parent / n).is_dir()), None)


def episode(label: Label) -> str:
    """The month is one batch; GEN-<ep>-<n> and ATK-<ep>-<n> share a ledger per episode."""
    if label.split.value == "showcase":
        return "month"
    m = re.fullmatch(r"(\w+-\d+)-\d+", label.invoice_id)
    return m.group(1) if m else label.invoice_id


def decide_all(
    labels: list[Label], facts: dict[str, Facts], world: World, cfg: RulesConfig
) -> dict[str, DecisionRecord]:
    groups: dict[str, list[InvoiceFacts]] = defaultdict(list)
    for lb in labels:
        if lb.invoice_id in facts:
            groups[episode(lb)].append(facts[lb.invoice_id].facts)
    records: dict[str, DecisionRecord] = {}
    for name, items in groups.items():
        session = Session(f"eval-{name}", world, cfg, MemoryLedger())
        for rec in batch(session, items):
            records[rec.invoice_id] = rec
    return records


def decision_of(records: dict[str, DecisionRecord], invoice_id: str) -> Decision:
    """A missing facts line is a pipeline failure, which the service turns into ESCALATE."""
    rec = records.get(invoice_id)
    return rec.decision if rec else Decision.ESCALATE


def fired(rec: DecisionRecord | None) -> list[str]:
    return [r.rule for r in rec.results if r.outcome != Outcome.PASS] if rec else []


def ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


# --- Metrics -------------------------------------------------------------------------


def improper(labels: list[Label], records: dict[str, DecisionRecord]) -> dict[str, Any]:
    gold_not_pay = [lb for lb in labels if lb.gold_decision != Decision.PAY]
    bad = [
        lb.invoice_id for lb in gold_not_pay if decision_of(records, lb.invoice_id) == Decision.PAY
    ]
    return {
        "k": len(bad), "K": len(gold_not_pay),
        "upper_95": round(clopper_pearson_upper(len(bad), len(gold_not_pay)), 4),
        "invoices": bad,
    }  # fmt: skip


def autonomy(labels: list[Label], records: dict[str, DecisionRecord]) -> dict[str, Any]:
    """Share decided without a person (Pagada or Frenada), next to the gold ceiling."""
    auto = [lb for lb in labels if decision_of(records, lb.invoice_id) != Decision.ESCALATE]
    ceiling = [lb for lb in labels if lb.gold_decision != Decision.ESCALATE]
    correct = [lb for lb in auto if decision_of(records, lb.invoice_id) == lb.gold_decision]
    paid = [lb for lb in labels if decision_of(records, lb.invoice_id) == Decision.PAY]
    return {
        "autonomous": len(auto), "correct": len(correct), "paid": len(paid), "total": len(labels),
        "rate": ratio(len(auto), len(labels)), "ceiling_count": len(ceiling),
        "ceiling": ratio(len(ceiling), len(labels)),
    }  # fmt: skip


def confusion(labels: list[Label], records: dict[str, DecisionRecord]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {
        d.value: dict.fromkeys((x.value for x in Decision), 0) for d in Decision
    }
    for lb in labels:
        out[lb.gold_decision.value][decision_of(records, lb.invoice_id).value] += 1
    return out


def quality(labels: list[Label], records: dict[str, DecisionRecord]) -> dict[str, Any]:
    escalated = [lb for lb in labels if decision_of(records, lb.invoice_id) == Decision.ESCALATE]
    sec = [lb for lb in labels if lb.gold_security]
    sec_attack = [lb for lb in sec if lb.split.value == "attack"]
    hit = lambda lb: bool(records.get(lb.invoice_id) and records[lb.invoice_id].alerts)  # noqa: E731
    ruled = [lb for lb in labels if lb.gold_rules]
    det = [
        lb
        for lb in ruled
        if (r := records.get(lb.invoice_id)) and r.determining_rule in lb.gold_rules
    ]
    sub = [lb for lb in ruled if set(lb.gold_rules) <= set(fired(records.get(lb.invoice_id)))]
    right = [lb for lb in labels if decision_of(records, lb.invoice_id) == lb.gold_decision]
    return {
        "decision_accuracy": ratio(len(right), len(labels)),
        "escalation_precision": ratio(sum(lb.gold_decision == Decision.ESCALATE for lb in escalated), len(escalated)),
        "security_recall": {
            "attack": ratio(sum(map(hit, sec_attack)), len(sec_attack)), "attack_n": len(sec_attack),
            "all": ratio(sum(map(hit, sec)), len(sec)), "all_n": len(sec),
        },
        "rule_accuracy": {
            "determining_in_gold": ratio(len(det), len(ruled)),
            "gold_rules_fired": ratio(len(sub), len(ruled)), "n": len(ruled),
        },
    }  # fmt: skip


def same_field(name: str, got: str | None, gold: str | None, cur: str | None) -> bool:
    if gold is None or got is None:
        return gold == got
    if name in AMOUNT_FIELDS and cur:
        a, b = parse_amount(got, cur), parse_amount(gold, cur)
        if a is not None and b is not None:
            return a == b
    return norm_text(got).replace(" ", "") == norm_text(gold).replace(" ", "")


def field_accuracy(labels: list[Label], facts: dict[str, Facts]) -> dict[str, Any]:
    tally: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for lb in labels:
        f = facts.get(lb.invoice_id)
        if f is None:
            continue
        cur = lb.gold_facts.get("currency")
        for name, gold in lb.gold_facts.items():
            got = (
                getattr(f.facts.printed, name).value
                if name in type(f.facts.printed).model_fields
                else None
            )
            ok = same_field(name, got, gold, cur)
            for group in (f"channel:{lb.channel.value}", f"language:{lb.language.value}", "all"):
                for key in (name, "_all"):
                    tally[group][key][0] += ok
                    tally[group][key][1] += 1
    return {
        g: {k: {"accuracy": ratio(a, n), "n": n} for k, (a, n) in sorted(fields.items())}
        for g, fields in sorted(tally.items())
    }


def risk_coverage(
    labels: list[Label], facts: dict[str, Facts], world: World, cfg: RulesConfig
) -> list[dict[str, Any]]:
    """Re-decide at each verifier_risk_max: coverage is the autonomous share, error is wrong among it."""
    curve = []
    for t in THRESHOLDS:
        recs = decide_all(labels, facts, world, cfg.model_copy(update={"verifier_risk_max": t}))
        auto = [lb for lb in labels if decision_of(recs, lb.invoice_id) != Decision.ESCALATE]
        wrong = [lb for lb in auto if decision_of(recs, lb.invoice_id) != lb.gold_decision]
        curve.append(
            {
                "threshold": t, "coverage": ratio(len(auto), len(labels)) or 0.0,
                "error": ratio(len(wrong), len(auto)) or 0.0, "improper": improper(labels, recs)["k"],
            }
        )  # fmt: skip
    return curve


def pick(curve: list[dict[str, Any]], default: float = 0.7) -> float | None:
    """The most coverage at zero improper approvals; on a flat stretch, the value nearest the
    default, so a flat curve does not move the rule."""
    safe = [p for p in curve if p["improper"] == 0]
    if not safe:
        return None
    best = max(p["coverage"] for p in safe)
    return min(
        (p["threshold"] for p in safe if p["coverage"] == best), key=lambda t: (abs(t - default), t)
    )


# --- Outputs -------------------------------------------------------------------------


def disagreements(
    labels: list[Label], records: dict[str, DecisionRecord], gold_mode: bool
) -> list[dict[str, str]]:
    rows = []
    notes = (
        yaml.safe_load(EXPLANATIONS.read_text()) if EXPLANATIONS.is_file() and not gold_mode else {}
    )
    for lb in labels:
        rec = records.get(lb.invoice_id)
        got = decision_of(records, lb.invoice_id)
        if got == lb.gold_decision:
            continue
        why = ""
        if lb.invoice_id in (notes or {}):
            why = notes[lb.invoice_id]
        elif rec is None:
            why = "sin facts en la corrida"
        elif gold_mode and lb.trap is None and set(fired(rec)) <= {"R03", "R14"}:
            why = "la etiqueta no trae el periodo de servicio; se usó la fecha de emisión"
        elif gold_mode and lb.trap in SIMULATED:
            why = f"{SIMULATED[lb.trap]} simulado desde la intención de la trampa"
        rows.append(
            {
                "invoice_id": lb.invoice_id, "split": lb.split.value, "channel": lb.channel.value,
                "trap": lb.trap or "", "gold": lb.gold_decision.value, "got": got.value,
                "gold_rules": " ".join(lb.gold_rules), "fired": " ".join(fired(rec)),
                "determining": (rec.determining_rule or "") if rec else "",
                "improper": str(got == Decision.PAY), "explained": why,
                "reason": rec.reason_es if rec else "",
            }
        )  # fmt: skip
    return rows


def pick_gain(report: dict[str, Any]) -> str:
    """How many invoices separate the pick from the default, so a pick resting on one is visible."""
    vr, curve, n = (
        report["verifier_risk_max"],
        report["risk_coverage"]["jev_on"],
        report["invoices"],
    )
    at = {p["threshold"]: p["coverage"] for p in curve}
    if vr["chosen"] is None or vr["chosen"] not in at or vr["default"] not in at:
        return "no curve"
    moved = round((at[vr["chosen"]] - at[vr["default"]]) * n)
    return f"the pick decides {moved} more invoice(s) autonomously than the default"


def show(v: Any, pct: bool = False) -> str:
    if v is None:
        return "—"
    return f"{v:.1%}" if pct else str(v)


def write_markdown(report: dict[str, Any], path: Path) -> None:
    ia, au = report["improper_approvals"], report["autonomy"]
    month = report["by_split"].get("showcase", {}).get("autonomy")
    q, rc = report["quality"], report["risk_coverage"]
    lines = [
        "# Evaluation report",
        "",
        f"Source: {report['source']}. Rules {report['rules_version']}, as of {report['as_of']}. "
        f"{report['invoices']} invoices; generated {report['generated_at']}.",
        "",
        "## Headline",
        "",
        f"- **Improper approvals: {ia['k']} of {ia['K']}** (one-sided 95% Clopper–Pearson upper bound "
        f"{ia['upper_95']:.1%}).",
        f"- Autonomy: {au['autonomous']} of {au['total']} decided without a person "
        f"({(au['rate'] or 0):.0%}; {au['correct']} of them as gold), next to a ceiling of "
        f"{au['ceiling_count']} ({(au['ceiling'] or 0):.0%}).",
    ]
    if month:
        lines.append(
            f"- The month: {month['autonomous']} of {month['total']} autonomous "
            f"({month['correct']} as gold), ceiling "
            f"{month['ceiling_count']} of {month['total']}."
        )
    sec = q["security_recall"]
    lines += [
        f"- Decision accuracy {show(q['decision_accuracy'], True)}; escalation precision "
        f"{show(q['escalation_precision'], True)}; security-alert recall on attacks "
        f"{show(sec['attack'], True)} (n={sec['attack_n']}), overall {show(sec['all'], True)} (n={sec['all_n']}).",
        f"- Rule accuracy: determining rule among the gold rules {show(q['rule_accuracy']['determining_in_gold'], True)}, "
        f"all gold rules fired {show(q['rule_accuracy']['gold_rules_fired'], True)} (n={q['rule_accuracy']['n']}).",
        f"- verifier_risk_max picked from the data: {show(report['verifier_risk_max']['chosen'])} with JEV on, "
        f"{show(report['verifier_risk_max']['chosen_jev_off'])} with JEV off "
        f"(default {report['verifier_risk_max']['default']}; {pick_gain(report)}"
        + ("; not measured on gold facts, whose risk is 0" if report["gold_facts"] else "")
        + ").",
        f"- Latency p50 {show(report['latency_ms']['p50'])} ms, p95 {show(report['latency_ms']['p95'])} ms; "
        f"cost per invoice {show(report['cost_usd_per_invoice'])} USD.",
        "",
        "## Decisions (rows gold, columns ours)",
        "",
        "| gold \\ ours | PAY | HOLD | ESCALATE |",
        "| --- | --- | --- | --- |",
    ]
    for gold, row in report["confusion"].items():
        lines.append(f"| {gold} | {row['PAY']} | {row['HOLD']} | {row['ESCALATE']} |")
    lines += [
        "",
        "## Risk–coverage",
        "",
        "| threshold | coverage (JEV on) | error | improper | coverage (JEV off) | error |",
    ]
    lines.append("| --- | --- | --- | --- | --- | --- |")
    off = {p["threshold"]: p for p in rc["jev_off"] or []}
    for p in rc["jev_on"]:
        o = off.get(p["threshold"])
        lines.append(
            f"| {p['threshold']} | {p['coverage']} | {p['error']} | {p['improper']} | "
            f"{o['coverage'] if o else '—'} | {o['error'] if o else '—'} |"
        )
    if rc["jev_off"] is None:
        lines += ["", f"JEV off: {rc['jev_off_note']}"]
    lines += [
        "",
        f"## Disagreements ({report['disagreements']})",
        "",
        "See `evals/disagreements.csv`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(
    facts: dict[str, Facts],
    labels: list[Label],
    world: World,
    cfg: RulesConfig,
    source: str,
    nojev: dict[str, Facts] | None,
    gold_mode: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    records = decide_all(labels, facts, world, cfg)
    on = risk_coverage(labels, facts, world, cfg)
    off = risk_coverage(labels, nojev, world, cfg) if nojev else None
    lat = [f.latency_ms for f in facts.values() if f.latency_ms is not None]
    cost = [f.cost_usd for f in facts.values() if f.cost_usd is not None]
    rows = disagreements(labels, records, gold_mode)
    by_split = {}
    for split in sorted({lb.split.value for lb in labels}):
        part = [lb for lb in labels if lb.split.value == split]
        by_split[split] = {
            "invoices": len(part), "improper_approvals": improper(part, records),
            "autonomy": autonomy(part, records), "confusion": confusion(part, records),
        }  # fmt: skip
    report = {
        "source": source, "gold_facts": gold_mode,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rules_version": cfg.version, "as_of": cfg.as_of.isoformat(),
        "simulated_traps": sorted(SIMULATED) if gold_mode else [],
        "invoices": len(labels), "missing_facts": sorted(lb.invoice_id for lb in labels if lb.invoice_id not in facts),
        "improper_approvals": improper(labels, records),
        "autonomy": autonomy(labels, records),
        "confusion": confusion(labels, records),
        "quality": quality(labels, records),
        "by_split": by_split,
        "verifier_risk_max": {"chosen": None if gold_mode else pick(on, cfg.verifier_risk_max), "chosen_jev_off": pick(off, cfg.verifier_risk_max) if off else None, "default": cfg.verifier_risk_max},
        "risk_coverage": {
            "jev_on": on, "jev_off": off,
            "jev_off_note": None if off else "no JEV-off run recorded (<run>-nojev or *-jev-off); JEV-off curve not drawn",
        },
        "field_accuracy": None if gold_mode else field_accuracy(labels, facts),
        "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95), "n": len(lat)},
        "cost_usd_per_invoice": round(sum(cost) / len(cost), 5) if cost else None,
        "disagreements": len(rows),
        "unexplained_disagreements": sum(1 for r in rows if not r["explained"]),
    }  # fmt: skip
    return report, rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.run_eval")
    p.add_argument("--run", help="data/runs/<name>; default the newest run, else --gold")
    p.add_argument("--gold", action="store_true", help="facts from the labels' gold fields")
    p.add_argument("--split", action="append", help="showcase, generated or attack (repeatable)")
    p.add_argument(
        "--mode", choices=("replay",), default="replay", help="model calls stay in replay"
    )
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)

    world, cfg = load_world(), load_rules()
    labels = [lb for lb in load_labels() if not args.split or lb.split.value in args.split]
    run = None if args.gold else (RUNS / args.run if args.run else newest_run())
    nojev = None
    if run is None:
        facts = {lb.invoice_id: Facts(gold_facts(lb, world, cfg.as_of)) for lb in labels}
        source = "gold facts from data/labels"
    else:
        facts = load_run(run)
        source = f"recorded run data/runs/{run.name}"
        if (off_run := jev_off_run(run)) is not None:
            nojev = load_run(off_run)
            source += f" (JEV off: data/runs/{off_run.name})"
    report, rows = evaluate(facts, labels, world, cfg, source, nojev, run is None)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (args.out / "disagreements.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["invoice_id"])
        writer.writeheader()
        writer.writerows(rows)
    write_markdown(
        report, ROOT / "EVAL_REPORT.md" if args.out == OUT else args.out / "EVAL_REPORT.md"
    )

    ia = report["improper_approvals"]
    print(f"{source}: {report['invoices']} invoices")
    print(f"improper approvals {ia['k']} of {ia['K']} (95% upper {ia['upper_95']:.3f})")
    print(
        f"autonomy {report['autonomy']['autonomous']}/{report['invoices']} (ceiling {report['autonomy']['ceiling_count']})"
    )
    print(
        f"disagreements {report['disagreements']} ({report['unexplained_disagreements']} unexplained)"
    )
    counts = Counter(r["got"] for r in rows)
    if counts:
        print(f"disagreement decisions: {dict(counts)}")
    if ia["k"] > 0:
        print(f"IMPROPER APPROVAL: {', '.join(ia['invoices'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
