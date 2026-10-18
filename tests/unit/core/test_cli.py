"""The alinka command end to end on a temporary run."""

import json
from datetime import UTC, datetime

from alinka.cli import main


def write_run(tmp_path, make_facts):
    run = tmp_path / "run"
    run.mkdir()
    first = make_facts("OCT-01", received=datetime(2026, 10, 1, tzinfo=UTC))
    again = make_facts("OCT-02", received=datetime(2026, 10, 2, tzinfo=UTC))
    lines = [json.dumps({"facts": json.loads(again.model_dump_json())}), first.model_dump_json()]
    (run / "facts.jsonl").write_text("\n".join(lines) + "\n")
    return run, first


def test_decide_one_file(tmp_path, make_facts, capsys):
    _, first = write_run(tmp_path, make_facts)
    path = tmp_path / "f.json"
    path.write_text(first.model_dump_json())
    assert main(["decide", str(path)]) == 0
    assert capsys.readouterr().out.startswith("OCT-01\tPAY\tPagada")


def test_batch_verify_and_export(tmp_path, make_facts, capsys):
    run, _ = write_run(tmp_path, make_facts)
    out = tmp_path / "records.jsonl"
    assert main(["batch", str(run), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "OCT-01\tPAY" in printed and "OCT-02\tHOLD R03" in printed

    assert main(["verify", str(out)]) == 0
    assert capsys.readouterr().out.startswith("OK: 2 registros")

    assert main(["export-csv", str(out)]) == 0
    assert capsys.readouterr().out.count("\n") == 3

    data = bytearray(out.read_bytes())
    i = data.index(b"OCT-01")
    data[i + 5] = ord("9")
    out.write_bytes(bytes(data))
    assert main(["verify", str(out)]) == 1
    assert "FALLA en el registro 1" in capsys.readouterr().err
