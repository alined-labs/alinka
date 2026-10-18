"""C11: the seven Probar steps keep the contract's shape (decision "Probar contract")."""

from alinka.api import runs, tracing
from alinka.decide import core
from alinka.decide.ledger import MemoryLedger
from alinka.world import load_rules, load_world

KEYS = {
    "received": {"invoice_id", "channel", "pages", "sha8", "filename", "language"},
    "sanitize": {"hidden_content", "unicode_controls", "html_text_mismatch", "instructions"},
    "read": {"mode", "calls", "fields", "stamps", "instructions_seen", "error"},
    "verify": {
        "calls", "fields", "ungrounded", "disagreements", "amount_in_regex",
        "totals_reconcile", "jev", "risk", "risk_max",
    },
    "rules": {"results"},
    "decide": {"decision", "label_es", "determining_rule", "alerts", "reason_es", "payment"},
    "record": {"record_id", "seq", "hash8", "prev_hash8"},
}  # fmt: skip


def records():
    session = core.Session(
        id="t", world=load_world(), cfg=load_rules(), ledger=MemoryLedger(), records=[]
    )
    return core.batch(session, runs.load_facts(runs.FIXTURE_RUN))


def test_build_trace_gives_seven_steps_with_exactly_the_contract_keys():
    for record in records():
        steps = [s.model_dump(mode="json") for s in tracing.build_trace(record)]
        assert [s["step"] for s in steps] == list(tracing.STEPS)
        for s in steps:
            assert set(s) == {"step", "status", "title_es", "summary_es", "ms", "data"}
            assert set(s["data"]) == KEYS[s["step"]], s["step"]
            assert s["ms"] is None and s["status"] in {"done", "flagged", "error"}
            assert s["title_es"] == tracing.TITLES_ES[s["step"]] and s["summary_es"]
        rules = steps[4]["data"]["results"]
        assert [r["rule"] for r in rules] == [f"R{i:02d}" for i in range(1, 17)]
        assert all(set(r) == {"rule", "name_es", "outcome", "security", "approvable",
                              "sentence_es"} for r in rules)  # fmt: skip
        fields = steps[2]["data"]["fields"]
        assert set(fields) == set(steps[3]["data"]["fields"]) and "total" in fields
        assert all(set(f) == {"value", "quote", "confidence"} for f in fields.values())
        assert all(set(f) == {"grounded", "agreed", "boxes"} for f in steps[3]["data"]["fields"].values())  # fmt: skip
        assert steps[5]["data"]["decision"] == record.decision.value
        assert steps[6]["data"]["hash8"] == record.hash[:8]


def test_statuses_follow_the_contract():
    for record in records():
        by = {s.step: s for s in tracing.build_trace(record)}
        assert by["received"].status == by["decide"].status == by["record"].status == "done"
        failing = [r for r in record.results if r.outcome.value != "pass"]
        assert by["rules"].status == ("flagged" if failing else "done")
        v = record.facts.verification
        doubt = v.ungrounded or v.disagreements or v.risk >= load_rules().verifier_risk_max
        if doubt:
            assert by["verify"].status == "flagged"
        assert tracing.running("read").model_dump()["data"] == {}
