"""D1: every route answers from the fixtures, and the edge secret guards all but health."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from alinka.api.app import app
from alinka.settings import get_settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_and_board_start_with_a_full_inbox(client):
    assert client.get("/api/health").json()["status"] == "ok"
    board = client.get("/api/board").json()
    assert board["view"] == "sandbox"
    assert len(board["inbox"]) == board["total"] > 0
    assert [c["count"] for c in board["columns"]] == [0, 0, 0]
    assert "alinka_sandbox" in client.cookies


def test_run_moves_the_inbox_into_three_columns(client):
    run = client.post("/api/run").json()
    board = run["board"]
    assert run["decided"] == board["total"]
    assert not board["inbox"]
    assert sum(c["count"] for c in board["columns"]) == board["total"]
    assert [c["label_es"] for c in board["columns"]] == [
        "Pagada", "Frenada", "Pendiente de aprobación",
    ]  # fmt: skip


def test_canonical_board_is_decided_and_untouched_by_the_sandbox(client):
    before = client.get("/api/board", params={"view": "canonical"}).json()
    client.post("/api/run")
    client.post("/api/invoices/OCT-03/approve", json={"approver": "Mariana Gómez Salcedo (CFO)"})
    after = client.get("/api/board", params={"view": "canonical"}).json()
    assert before == after and before["head_hash"]


def test_approval_needs_a_name_and_never_passes_r01(client):
    client.post("/api/run")
    assert client.post("/api/invoices/OCT-03/approve", json={"approver": ""}).status_code == 422
    assert client.post("/api/invoices/OCT-06/approve", json={"approver": "Ana"}).status_code == 409
    detail = client.post("/api/invoices/OCT-03/approve", json={"approver": "Ana"}).json()
    assert detail["card"]["state"] == "PAY" and detail["card"]["approver"] == "Ana"
    assert detail["payment"]["account_masked"].endswith("****3218")
    assert client.get("/api/log/verify").json()["ok"]


def test_invoice_detail_has_pages_fields_and_all_rules(client):
    client.post("/api/run")
    detail = client.get("/api/invoices/OCT-05").json()
    assert detail["card"]["alerts"] == ["R11"] and not detail["card"]["approvable"]
    assert len(detail["rules"]) == 16
    assert any(f["boxes"] for f in detail["fields"])
    png = client.get(detail["pages"][0]["url"])
    assert png.headers["content-type"] == "image/png"
    assert client.get("/api/invoices/NOPE").status_code == 404


def test_rules_are_range_checked(client):
    assert client.put("/api/rules", json={"approval_threshold_usd": 5}).status_code == 422
    saved = client.put("/api/rules", json={"approval_threshold_usd": 1500}).json()
    assert saved["rules"]["rules"]["approval_threshold_usd"] == 1500


def test_csv_lists_every_decision(client):
    client.post("/api/run")
    rows = client.get("/api/log/export.csv").text.strip().splitlines()
    assert rows[0].startswith("factura,beneficiario,monto,moneda,usd,decision")
    assert len(rows) - 1 == len(client.get("/api/log").json()["entries"])


def test_edge_secret_guards_everything_but_health(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "edge_secret", SecretStr("s3cret"))
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/board").status_code == 403
    assert client.get("/api/board", headers={"X-Edge-Secret": "wrong"}).status_code == 403
    assert client.get("/api/board", headers={"X-Edge-Secret": "s3cret"}).status_code == 200
