"""Write one sample response per route to alinka/api/fixtures/samples/ for the web's fixture mode.

Run `uv run python -m alinka.api.samples` after changing the models or the fixtures.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from alinka.api.app import app

OUT = Path(__file__).resolve().parent / "fixtures" / "samples"
APPROVER = {"approver": "Mariana Gómez Salcedo (CFO)"}


def main() -> None:
    c = TestClient(app)
    calls = {
        "health": c.get("/api/health"),
        "board_inbox": c.get("/api/board"),
        "run": c.post("/api/run"),
        "board_canonical": c.get("/api/board", params={"view": "canonical"}),
        "invoice_OCT-05": c.get("/api/invoices/OCT-05"),
        "rules": c.get("/api/rules"),
        "approve_OCT-03": c.post("/api/invoices/OCT-03/approve", json=APPROVER),
        "log": c.get("/api/log"),
        "log_verify": c.get("/api/log/verify"),
        "eval": c.get("/api/eval"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, resp in calls.items():
        resp.raise_for_status()
        body = resp.json()
        if name in {"run", "board_inbox", "approve_OCT-03", "log", "log_verify", "rules"}:
            body = json.loads(json.dumps(body).replace(c.cookies["alinka_sandbox"], "sandbox-demo"))
        (OUT / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
