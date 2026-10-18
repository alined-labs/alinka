"""The shared contracts load, validate and round-trip, so make check is green from the seed."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from alinka.types import (
    DECISION_ES,
    RULE_IDS,
    RULE_NAMES_ES,
    Channel,
    Decision,
    DecisionRecord,
    Field,
    InvoiceFacts,
    Outcome,
    Printed,
    RuleResult,
    RulesConfig,
    Source,
)

ROOT = Path(__file__).resolve().parents[1]


def facts() -> InvoiceFacts:
    return InvoiceFacts(
        source=Source(
            invoice_id="OCT-01",
            doc_sha256="0" * 64,
            channel=Channel.PDF,
            received_at=datetime(2026, 10, 1, 14, 0, tzinfo=UTC),
        ),
        as_of=date(2026, 10, 17),
        printed=Printed(total=Field(value="1.200,00", quote="Total: $ 1.200,00")),
    )


def test_rules_yaml_matches_the_contract():
    cfg = RulesConfig.model_validate(yaml.safe_load((ROOT / "data/rules.yaml").read_text()))
    assert cfg.approval_threshold_usd == 2000
    assert cfg.as_of == date(2026, 10, 17)


def test_vocabulary_is_complete():
    assert len(RULE_IDS) == 16 and set(RULE_NAMES_ES) == set(RULE_IDS)
    assert DECISION_ES[Decision.ESCALATE] == "Pendiente de aprobación"


def test_facts_round_trip_and_are_frozen():
    f = facts()
    assert InvoiceFacts.model_validate_json(f.model_dump_json()) == f
    with pytest.raises(ValidationError):
        f.as_of = date(2026, 1, 1)  # type: ignore[misc]


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Field.model_validate({"value": "x", "bogus": 1})


def test_decision_record_round_trip():
    results = tuple(
        RuleResult(rule=r, outcome=Outcome.PASS, message_key=f"{r}.ok") for r in RULE_IDS
    )
    rec = DecisionRecord(
        record_id="rec-1",
        session="canonical",
        seq=1,
        prev_hash="0" * 64,
        hash="f" * 64,
        invoice_id="OCT-01",
        decision=Decision.PAY,
        results=results,
        reason_es="Pagada: cumple las 16 reglas.",
        facts=facts(),
        rules_version="2026-10-18.1",
        rules_hash="a" * 64,
        as_of=date(2026, 10, 17),
        code_version="0.1.0",
        created_at=datetime(2026, 10, 18, 9, 0, tzinfo=UTC),
    )
    assert DecisionRecord.model_validate_json(rec.model_dump_json()) == rec


def test_settings_default_to_replay_without_keys(monkeypatch, tmp_path):
    from alinka.settings import Settings

    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("CACHE_MODE", raising=False)
    s = Settings()
    assert s.cache_mode == "replay" and s.anthropic_api_key is None
