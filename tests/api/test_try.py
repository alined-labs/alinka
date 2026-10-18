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


TRACE_KEYS = {
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


def test_the_trace_endpoint_returns_the_contract_shape_and_matches_the_run(client):
    got = run(client, "ATK-12-1")
    streamed = [d for n, d in got if n == "step" and d["status"] != "running"]
    trace = client.get(f"/api/invoices/{got[-1][1]['invoice_id']}/trace").json()
    assert [s["step"] for s in trace] == STEPS
    for step, live in zip(trace, streamed, strict=True):
        assert set(step) == {"step", "status", "title_es", "summary_es", "ms", "data"}
        assert set(step["data"]) == TRACE_KEYS[step["step"]] and step["ms"] is None
        assert step["status"] == live["status"]
        if step["step"] != "received":  # the language is known only after the reading
            assert step["data"] == live["data"], step["step"]
    assert trace[1]["status"] == "flagged" and trace[1]["data"]["unicode_controls"]
    assert len(trace[4]["data"]["results"]) == 16


def test_the_trace_is_scoped_like_the_invoice(client):
    assert len(client.get("/api/invoices/OCT-01/trace", params={"view": "canonical"}).json()) == 7
    assert client.get("/api/invoices/OCT-01/trace").status_code == 404  # still in the inbox
    assert client.get("/api/invoices/NOPE/trace").status_code == 404
    client.post("/api/run")
    assert client.get("/api/invoices/OCT-01/trace").status_code == 200


def test_page_images_scale_to_150_300_and_450_dpi(client):
    from io import BytesIO

    from PIL import Image

    run(client, "GEN-090-1")  # an email: its code-rendered page, not a placeholder
    widths = []
    for scale in (1, 2, 3):
        r = client.get("/api/invoices/TRY-GEN-090-1-1/pages/1", params={"scale": scale})
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        widths.append(Image.open(BytesIO(r.content)).width)
    assert abs(widths[1] - 2 * widths[0]) <= 2 and abs(widths[2] - 3 * widths[0]) <= 3
    detail = client.get("/api/invoices/TRY-GEN-090-1-1").json()
    assert abs(detail["pages"][0]["width"] - widths[0]) <= 1
    assert client.get("/api/invoices/OCT-01/pages/1", params={"scale": 4}).status_code == 422


# --- Uploads ----------------------------------------------------------------------


@pytest.fixture
def admin(client, monkeypatch, pool):
    """ADMIN_TOKEN set, live uploads switched off again afterwards."""
    from pydantic import SecretStr

    from alinka.settings import get_settings

    monkeypatch.setattr(get_settings(), "admin_token", SecretStr("adm1n"))
    yield {"Authorization": "Bearer adm1n"}
    with pool.connection() as conn:
        conn.execute("UPDATE settings SET value = 'false' WHERE key = 'live_uploads'")
        conn.execute("DELETE FROM upload_log")


def uploads_on(client, admin):
    r = client.put("/api/admin/settings", json={"live_uploads": True}, headers=admin)
    assert r.status_code == 200 and r.json() == {"live_uploads": True}


def pdf(pages: int) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text(
            (72, 72), f"Factura de prueba (empresa ficticia), página {i + 1}"
        )
    return doc.tobytes()


def test_the_admin_switch_needs_the_token_and_is_off_without_one(client, admin, monkeypatch):
    from alinka.settings import get_settings

    body = {"live_uploads": True}
    assert client.put("/api/admin/settings", json=body).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.put("/api/admin/settings", json=body, headers=bad).status_code == 401
    uploads_on(client, admin)
    assert client.get("/api/try/samples").json()["live_uploads"] is True
    monkeypatch.setattr(get_settings(), "admin_token", None)
    assert client.put("/api/admin/settings", json=body, headers=admin).status_code == 404


def test_an_upload_runs_live_and_its_pages_come_from_the_stored_file(client, admin, monkeypatch):
    from alinka.cache import ResponseCache

    uploads_on(client, admin)
    modes = []

    def replayed(mode, directory=None):  # no model calls in tests: replay the recordings
        modes.append(mode)
        return ResponseCache("replay")

    monkeypatch.setattr(try_routes, "ResponseCache", replayed)
    data = (try_routes.ROOT / "data/generated/GEN-084-1.pdf").read_bytes()
    started = client.post("/api/try", files={"file": ("mi factura.pdf", data, "application/pdf")})
    assert started.status_code == 202, started.text
    got = events(client, started.json()["events_url"])
    done = got[-1][1]
    sha8 = __import__("hashlib").sha256(data).hexdigest()[:8]
    assert modes == ["live"] and done["invoice_id"] == f"UPL-{sha8}"
    detail = client.get(f"/api/invoices/{done['invoice_id']}").json()
    assert detail["record"]["facts"]["source"]["path"] is None
    page = client.get(f"/api/invoices/{done['invoice_id']}/pages/1", params={"scale": 2})
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert detail["pages"][0]["width"] == 1240
    again = client.post("/api/try", files={"file": ("otra.pdf", data, "application/pdf")})
    assert events(client, again.json()["events_url"])[-1][1]["invoice_id"] == f"UPL-{sha8}-2"


def test_uploads_are_checked_for_size_type_and_pages(client, admin):
    uploads_on(client, admin)
    big = b"%PDF-1.7\n" + b"0" * (4 * 1024 * 1024)
    r = client.post("/api/try", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413
    r = client.post("/api/try", files={"file": ("x.pdf", b"hola", "application/pdf")})
    assert r.status_code == 415
    r = client.post("/api/try", files={"file": ("x.pdf", b"%PDF-1.7 roto", "application/pdf")})
    assert r.status_code == 415
    r = client.post("/api/try", files={"file": ("four.pdf", pdf(4), "application/pdf")})
    assert r.status_code == 422 and "3 páginas" in r.json()["detail"]
    r = client.post("/api/try", files={"other": ("x.pdf", pdf(1), "application/pdf")})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("rows", "ago", "ip", "limit"),
    [(5, "5 minutes", "198.51.100.1", "10 minutos"), (30, "2 hours", "198.51.100.1", "por día"),
     (200, "3 hours", "198.51.100.77", "de hoy")],
)  # fmt: skip
def test_the_upload_quotas_hold(client, admin, pool, rows, ago, ip, limit):
    uploads_on(client, admin)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO upload_log (client_ip, created_at)"
            " SELECT %s, now() - %s::interval FROM generate_series(1, %s)",
            (ip, ago, rows),
        )
    mine = {"X-Client-IP": "198.51.100.1"}
    r = client.post("/api/try", files={"file": ("x.pdf", pdf(1), "application/pdf")}, headers=mine)
    assert r.status_code == 429 and limit in r.json()["detail"]
    assert int(r.headers["retry-after"]) > 0
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM upload_log").fetchone()["n"] == rows
