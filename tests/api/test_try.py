"""C11: Probar runs a sample through the real pipeline in the visitor's sandbox."""

import json
import threading
import time

import pytest

from alinka.api import try_routes

pytestmark = pytest.mark.db
STEPS = ["received", "sanitize", "read", "verify", "rules", "decide", "record"]


def events(client, url: str) -> list[tuple[str, object]]:
    """Every SSE event as (name, data); comments as ("comment", text)."""
    out: list[tuple[str, object]] = []
    with client.stream("GET", url) as stream:
        assert stream.status_code == 200
        name = None
        for line in stream.iter_lines():
            if line.startswith(":"):
                out.append(("comment", line[1:].strip()))
            elif line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                out.append((name, json.loads(line[5:])))
    return out


def run(client, sample_id: str) -> list[tuple[str, object]]:
    started = client.post("/api/try", json={"sample_id": sample_id})
    assert started.status_code == 202, started.text
    return events(client, started.json()["events_url"])


def test_samples_come_from_the_dataset_with_the_upload_limits(client):
    body = client.get("/api/try/samples").json()
    assert body["live_uploads"] is False
    assert body["upload_limits"] == {
        "types": ["pdf", "png", "jpg"], "max_mb": 4, "max_pages": 3,
        "per_10_min": 5, "per_day": 30, "keep_hours": 24,
    }  # fmt: skip
    samples = body["samples"]
    assert 8 <= len(samples) <= 10
    assert {s["kind"] for s in samples} == {"routine", "trap", "attack"}
    assert {s["channel"] for s in samples} == {"pdf", "image", "email", "chat"}
    assert all(s["hint_es"] and s["title_es"] and s["pages"] >= 1 for s in samples)


def test_a_sample_streams_seven_steps_in_order_and_lands_on_the_board(client):
    got = run(client, "GEN-084-1")
    steps = [d for name, d in got if name == "step"]
    assert [s["step"] for s in steps] == [x for x in STEPS for _ in range(2)]
    for running, final in zip(steps[::2], steps[1::2], strict=True):
        assert running["status"] == "running" and running["data"] == {} and running["ms"] is None
        assert final["status"] == "done" and final["data"] and final["ms"] >= 0
    by = {s["step"]: s for s in steps[1::2]}
    assert by["read"]["data"]["mode"] == "replay"
    assert all(c["cached"] for c in by["read"]["data"]["calls"] + by["verify"]["data"]["calls"])
    assert len(by["rules"]["data"]["results"]) == 16
    assert set(by["decide"]["data"]) == {
        "decision", "label_es", "determining_rule", "alerts", "reason_es", "payment"
    }  # fmt: skip
    name, done = got[-1]
    assert name == "done"
    assert done == {
        "invoice_id": "TRY-GEN-084-1-1", "decision": "PAY", "label_es": "Pagada",
        "href": "/facturas/TRY-GEN-084-1-1",
    }  # fmt: skip
    board = client.get("/api/board").json()
    cards = [c for col in board["columns"] for c in col["cards"]]
    assert any(c["invoice_id"] == "TRY-GEN-084-1-1" and c["state"] == "PAY" for c in cards)
    detail = client.get("/api/invoices/TRY-GEN-084-1-1").json()
    assert detail["record"]["seq"] == by["record"]["data"]["seq"]
    assert client.get("/api/board", params={"view": "canonical"}).json()["total"] == 6


def test_the_same_document_twice_is_held_as_a_duplicate(client):
    assert run(client, "GEN-084-1")[-1][1]["decision"] == "PAY"
    done = run(client, "DUP-GEN-084-1")[-1][1]
    assert done["invoice_id"] == "TRY-DUP-GEN-084-1-1" and done["decision"] == "HOLD"
    record = client.get(f"/api/invoices/{done['invoice_id']}").json()["record"]
    assert record["determining_rule"] == "R03"


def test_an_attack_sample_flags_the_sanitizer_step(client):
    got = run(client, "ATK-01-1")
    sanitize = next(
        d for n, d in got if n == "step" and d["step"] == "sanitize" and d["ms"] is not None
    )
    assert sanitize["status"] == "flagged" and sanitize["data"]["hidden_content"]
    assert got[-1][1]["decision"] == "ESCALATE"


def test_uploads_are_refused_while_live_uploads_is_off(client):
    r = client.post("/api/try", files={"file": ("f.pdf", b"%PDF-1.7", "application/pdf")})
    assert r.status_code == 403 and r.json()["detail"]


def test_unknown_samples_and_other_visitors_jobs_are_404(client):
    from fastapi.testclient import TestClient

    from alinka.api.app import app

    assert client.post("/api/try", json={"sample_id": "OCT-01"}).status_code == 404
    started = client.post("/api/try", json={"sample_id": "GEN-084-1"}).json()
    assert TestClient(app).get(started["events_url"]).status_code == 404
    events(client, started["events_url"])
    assert client.get("/api/try/nope/events").status_code == 404


def test_the_hourly_sample_quota_holds_per_client_ip(client, monkeypatch):
    monkeypatch.setattr(try_routes.JOBS, "samples", try_routes.Window(1, 3600))
    run(client, "GEN-084-1")
    r = client.post("/api/try", json={"sample_id": "GEN-084-1"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    other_ip = client.post(
        "/api/try", json={"sample_id": "GEN-084-1"}, headers={"X-Client-IP": "203.0.113.9"}
    )
    assert other_ip.status_code == 202
    events(client, other_ip.json()["events_url"])


def test_one_run_at_a_time_per_visitor(client, monkeypatch):
    gate = threading.Event()
    real = try_routes.run_sample
    monkeypatch.setattr(try_routes, "run_sample", lambda job, s: (gate.wait(5), real(job, s)))
    first = client.post("/api/try", json={"sample_id": "GEN-084-1"})
    second = client.post("/api/try", json={"sample_id": "GEN-084-1"})
    gate.set()
    assert first.status_code == 202
    assert second.status_code == 429 and second.headers["retry-after"]
    events(client, first.json()["events_url"])


def test_the_stream_has_no_cache_headers_and_pings(client, monkeypatch):
    monkeypatch.setattr(try_routes, "PING_S", 0.1)
    client.get("/api/board")  # the sandbox cookie
    job = try_routes.Job(id="test-ping", session_id=client.cookies["alinka_sandbox"])
    try_routes.JOBS.jobs[job.id] = job

    def finish():
        time.sleep(0.35)
        job.emit("error", {"message_es": "x"})
        job.finished = True

    threading.Thread(target=finish).start()
    with client.stream("GET", "/api/try/test-ping/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert stream.headers["cache-control"] == "no-cache"
        lines = list(stream.iter_lines())
    assert ": ping" in lines and lines.index(": ping") < lines.index("event: error")
