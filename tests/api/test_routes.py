"""D3: the routes on Postgres, sandbox isolation and the edge secret."""

import time

import pytest
from pydantic import SecretStr

from alinka.settings import get_settings

pytestmark = pytest.mark.db
CFO = {"approver": "Mariana Gómez Salcedo (CFO)"}


def counts(board) -> list[int]:
    return [c["count"] for c in board["columns"]]


def test_sandbox_starts_with_a_full_inbox_and_a_cookie(client):
    board = client.get("/api/board").json()
    assert board["view"] == "sandbox" and len(board["inbox"]) == board["total"] == 6
    assert counts(board) == [0, 0, 0]
    assert "alinka_sandbox" in client.cookies
    assert client.get("/api/board").json()["session_id"] == board["session_id"]


def test_run_decides_the_inbox_in_received_order(client):
    run = client.post("/api/run").json()
    assert run["decided"] == 6 and not run["board"]["inbox"]
    assert counts(run["board"]) == [2, 1, 3]
    assert [s["invoice_id"] for s in run["steps"]] == [f"OCT-0{i}" for i in range(1, 7)]
    assert client.post("/api/run").json()["decided"] == 0


def test_canonical_never_changes(client):
    before = client.get("/api/board", params={"view": "canonical"}).json()
    log_before = client.get("/api/log", params={"view": "canonical"}).json()
    client.post("/api/run")
    client.put("/api/rules", json={"approval_threshold_usd": 500})
    client.post("/api/invoices/OCT-03/approve", json=CFO)
    client.post("/api/sandbox/reset")
    assert client.get("/api/board", params={"view": "canonical"}).json() == before
    assert client.get("/api/log", params={"view": "canonical"}).json() == log_before


def test_sandboxes_are_private(client, pool):
    from fastapi.testclient import TestClient as TC

    from alinka.api.app import app

    client.post("/api/run")
    other = TC(app)
    assert counts(other.get("/api/board").json()) == [0, 0, 0]


def test_rule_edit_redecides_fast_and_reset_restores(client):
    client.post("/api/run")
    t0 = time.perf_counter()
    saved = client.put("/api/rules", json={"approval_threshold_usd": 500}).json()
    assert time.perf_counter() - t0 < 2
    assert saved["rules"]["rules"]["approval_threshold_usd"] == 500
    assert counts(saved["board"]) == [0, 1, 5]
    assert client.put("/api/rules", json={"monthly_cap_usd": 1}).status_code == 422
    reset = client.post("/api/sandbox/reset").json()
    assert counts(reset) == [0, 0, 0] and len(reset["inbox"]) == 6
    assert client.get("/api/rules").json()["rules"]["approval_threshold_usd"] == 2000


def test_approval_rules(client):
    client.post("/api/run")
    assert client.post("/api/invoices/OCT-03/approve", json={"approver": " "}).status_code == 422
    assert client.post("/api/invoices/OCT-06/approve", json=CFO).status_code == 409  # R01
    assert client.post("/api/invoices/OCT-04/approve", json=CFO).status_code == 409  # HOLD
    detail = client.post("/api/invoices/OCT-03/approve", json=CFO).json()
    assert detail["card"]["state"] == "PAY" and detail["card"]["approver"] == CFO["approver"]
    assert client.post("/api/invoices/OCT-03/approve", json=CFO).status_code == 409
    rejected = client.post("/api/invoices/OCT-06/reject", json=CFO).json()
    assert rejected["card"]["state"] == "HOLD"
    log = client.get("/api/log").json()
    assert [e["seq"] for e in log["entries"]] == list(range(1, 9))
    assert client.get("/api/log/verify").json()["ok"]


def test_detail_pages_and_beneficiaries(client):
    client.post("/api/run")
    detail = client.get("/api/invoices/OCT-05").json()
    assert detail["card"]["alerts"] == ["R11"] and len(detail["rules"]) == 16
    assert any(f["boxes"] for f in detail["fields"])
    png = client.get(detail["pages"][0]["url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get("/api/invoices/OCT-05/pages/99").status_code == 404
    assert client.get("/api/invoices/NOPE").status_code == 404
    body = {
        "name": "Nébula Estudio Creativo", "tax_id": "DEMO-900555111-2", "country": "CO",
        "currency": "COP", "account_on_file": "Banco Ficticio Andino · DEMO-0099",
        "contract": {"scope_es": ["diseño"], "rate_minor": 280000000, "valid_from": "2026-01-01",
                     "valid_to": "2026-12-31", "cost_center": "design"},
    }  # fmt: skip
    added = client.post("/api/beneficiaries", json=body).json()
    assert added["beneficiary"]["id"] == "SBX-01" and added["beneficiary"]["added_in_sandbox"]
    card = next(
        c for col in added["board"]["columns"] for c in col["cards"] if c["invoice_id"] == "OCT-06"
    )
    assert card["beneficiary_id"] == "SBX-01"
    assert client.post("/api/beneficiaries", json=body).status_code == 409


def test_csv_and_eval(client):
    client.post("/api/run")
    rows = client.get("/api/log/export.csv").text.strip().splitlines()
    assert rows[0] == "factura,beneficiario,monto,moneda,usd,decision,reglas,motivo,aprobador,fecha"
    assert len(rows) == 7
    assert client.get("/api/eval").json()["available"]


def test_health_reports_the_canonical_head(client):
    client.get("/api/board", params={"view": "canonical"})
    health = client.get("/api/health").json()
    assert health["database"] and len(health["canonical_head"]) == 64


def test_edge_secret_guards_everything_but_health(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "edge_secret", SecretStr("s3cret"))
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/board").status_code == 403
    assert client.get("/api/board", headers={"X-Edge-Secret": "wrong"}).status_code == 403
    assert client.get("/api/board", headers={"X-Edge-Secret": "s3cret"}).status_code == 200


def test_load_run_replaces_the_canonical_only(client, pool, capsys):
    from alinka.api import load_run

    sandbox = client.post("/api/run").json()["board"]
    assert load_run.main(["fixture", "--no-migrate"]) == 0
    out = capsys.readouterr().out
    head = out.split("head ")[1].strip()
    assert client.get("/api/health").json()["canonical_head"] == head
    assert client.get("/api/board").json() == sandbox
    assert load_run.main(["no-such-run", "--no-migrate"]) == 2
