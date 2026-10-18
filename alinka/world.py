"""Typed loaders for the fictional world: rules, payer, beneficiaries and FX."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from alinka.fx import load_fx
from alinka.types import Beneficiary, Company, FxUsed, InvoiceFacts, RulesConfig

DATA = Path(__file__).resolve().parents[1] / "data"


def load_rules(path: Path = DATA / "rules.yaml") -> RulesConfig:
    return RulesConfig.model_validate(yaml.safe_load(path.read_text()))


def rules_hash(cfg: RulesConfig) -> str:
    return hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()


def load_company(path: Path = DATA / "company.yaml") -> Company:
    return Company.model_validate(yaml.safe_load(path.read_text()))


def load_beneficiaries(path: Path = DATA / "vendors.yaml") -> tuple[Beneficiary, ...]:
    raw = yaml.safe_load(path.read_text())["beneficiaries"]
    return tuple(Beneficiary.model_validate(b) for b in raw)


@dataclass(frozen=True)
class World:
    company: Company
    beneficiaries: tuple[Beneficiary, ...]
    fx: tuple[FxUsed, ...] = field(default=())

    def beneficiary(self, ben_id: str) -> Beneficiary | None:
        return next((b for b in self.beneficiaries if b.id == ben_id), None)

    def with_beneficiary(self, ben: Beneficiary) -> World:
        """A copy with one more beneficiary (the sandbox's way out of R01)."""
        return World(self.company, (*self.beneficiaries, ben), self.fx)


def load_world(data: Path = DATA) -> World:
    return World(
        company=load_company(data / "company.yaml"),
        beneficiaries=load_beneficiaries(data / "vendors.yaml"),
        fx=load_fx(data / "fx.yaml"),
    )


def load_run_dir(run_dir: Path) -> tuple[InvoiceFacts, ...]:
    """Recorded facts from *.jsonl (bare facts or {"facts": ...} lines), in received order.

    The last line wins for a repeated invoice, as in Lane C's resumable runs.
    """
    facts: dict[str, InvoiceFacts] = {}
    for path in sorted(run_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw = raw if "source" in raw else raw.get("facts")
            if raw:
                f = InvoiceFacts.model_validate(raw)
                facts[f.source.invoice_id] = f
    return tuple(sorted(facts.values(), key=lambda f: (f.source.received_at, f.source.invoice_id)))
