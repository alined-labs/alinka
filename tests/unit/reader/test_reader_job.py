"""The extract job: shards, resume, summary and publish, in replay mode."""

from __future__ import annotations

import json

from alinka.jobs import extract
from alinka.types import InvoiceFacts


def test_shards_partition_the_labels():
    labels = extract.load_labels("all")
    assert len(labels) == len({label.invoice_id for label in labels}) >= 175
    parts = [extract.shard_of(labels, i, 3) for i in (1, 2, 3)]
    assert sorted(x.invoice_id for p in parts for x in p) == sorted(x.invoice_id for x in labels)


def test_run_resumes_and_publishes(tmp_path, capsys):
    out = extract.run("showcase", mode="replay", run_id="t", limit=2, runs_dir=tmp_path, jev=True)
    facts_file = out / "facts-1of1.jsonl"
    first = facts_file.read_text().splitlines()
    assert len(first) == 2
    extract.run("showcase", mode="replay", run_id="t", limit=2, runs_dir=tmp_path, jev=True)
    assert facts_file.read_text().splitlines() == first  # nothing redone
    assert "0 to do, 2 already done" in capsys.readouterr().out

    summary = json.loads((out / "summary-1of1.json").read_text())
    assert summary["invoices"] == 2 and summary["extraction_errors"] == 0
    assert summary["latency_ms_p95"] >= summary["latency_ms_p50"] > 0 and summary["cost_usd"] > 0

    target = extract.publish(out, "pub", dest=tmp_path / "published")
    lines = (target / "facts.jsonl").read_text().splitlines()
    facts = [InvoiceFacts.model_validate_json(line) for line in lines]
    assert [f.source.invoice_id for f in facts] == ["OCT-01", "OCT-02"]
    assert all(f.printed.total.grounded for f in facts)
    assert json.loads((target / "summary.json").read_text())["source_run"] == "t"


def test_cli_parses_shards():
    assert extract._shard("2/4") == (2, 4)


def test_staged_pipeline_reports_an_unreadable_file_and_a_failed_stage():
    from datetime import UTC, datetime

    from alinka.cache import ResponseCache
    from alinka.verify.facts import Staged

    staged = Staged(
        b"not a pdf", ".pdf", invoice_id="TRY-X-1", received_at=datetime(2026, 10, 18, tzinfo=UTC),
        cache=ResponseCache("replay"),
    )  # fmt: skip
    staged.ingest()
    staged.read()
    staged.check()
    facts = staged.facts()
    assert facts.flags.extraction_error.startswith("ingest:")
    assert facts.source.pages == 0 and facts.source.channel == "pdf"
    staged.error = None
    staged.fail("read", RuntimeError("boom"))
    assert staged.facts().flags.extraction_error == "read: RuntimeError: boom"


def test_every_probar_sample_reads_from_its_recordings_without_tesseract(monkeypatch):
    from alinka.api.try_routes import ROOT, SAMPLES
    from alinka.cache import ResponseCache
    from alinka.ingest import image
    from alinka.verify.facts import Staged

    monkeypatch.setattr(image.shutil, "which", lambda _: None)  # as on the hub and Azure
    for sample in SAMPLES:
        label = sample.label
        file = ROOT / label.path
        staged = Staged(
            file.read_bytes(), file.suffix, invoice_id=f"TRY-{sample.id}-1",
            received_at=label.received_at, path=label.path, cache=ResponseCache("replay"),
        )  # fmt: skip
        staged.ingest()
        staged.read()
        facts = staged.facts()
        assert facts.flags.extraction_error is None, (sample.id, facts.flags.extraction_error)
        assert facts.source.pages >= 1, sample.id


def test_an_unreadable_photo_still_counts_as_one_page():
    from datetime import UTC, datetime

    from alinka.cache import ResponseCache
    from alinka.verify.facts import Staged

    staged = Staged(
        b"not a photo", ".jpg", invoice_id="UPL-X", received_at=datetime(2026, 10, 18, tzinfo=UTC),
        cache=ResponseCache("replay"),
    )  # fmt: skip
    staged.ingest()
    assert staged.facts().source.pages == 1
