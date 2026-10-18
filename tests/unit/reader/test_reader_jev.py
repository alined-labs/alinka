"""JEV: question building, scoring, the budget, and failures escalating."""

from __future__ import annotations

import httpx
import pymupdf
import pytest
from pydantic import SecretStr

from alinka.cache import ResponseCache
from alinka.ingest.base import Ingested, PageData
from alinka.ingest.pdf import ingest_pdf
from alinka.settings import get_settings
from alinka.types import Channel, Computed, Field, Printed
from alinka.verify import checks, jev


def _doc() -> Ingested:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Subtotal 1.000,00  IVA 250,00", fontsize=12)
    page.insert_text((72, 130), "Total a pagar: 1.250,00 USD", fontsize=12)
    return ingest_pdf(doc.tobytes())


COMPUTED = Computed(currency="USD", total_minor=125_000)
PRINTED = Printed(total=Field(value="1.250,00"), currency=Field(value="USD"))


@pytest.fixture
def jev_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("sk-test-not-a-key"))
    return settings


def _fake(monkeypatch, answer, calls=None):
    def post(url, json, timeout, headers):
        if calls is not None:
            calls.append(json)
        assert url == jev.URL and headers["Authorization"].startswith("Bearer ")
        assert timeout <= jev.BUDGET_S
        answers = answer(json["questions"])
        return httpx.Response(
            200,
            json={
                "answers": answers,
                "usage": {"input_tokens": 10, "output_tokens": 1, "cost": 1e-6},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(jev.httpx, "post", post)


def _honest(questions):
    out = {}
    for name, q in questions.items():
        if q["type"] == "choice":
            out[name] = {"type": "choice", "choice": "1.250,00", "confidence": 0.99,
                         "probabilities": {"1.250,00": 0.99}}  # fmt: skip
        else:
            out[name] = {"type": "noul", "noul": 0.03}
    return out


def _run(tmp_path, printed=PRINTED):
    doc = _doc()
    money = checks.money_spans(doc, "USD")
    return jev.run_jev(doc, printed, COMPUTED, money, cache=ResponseCache("record", tmp_path))


def test_questions_ask_j1_twice_in_two_orders_and_j2_per_field(jev_on, monkeypatch, tmp_path):
    calls: list[dict] = []
    _fake(monkeypatch, _honest, calls)
    result = _run(tmp_path)
    (body,) = calls
    assert body["model"] == jev_on.jev_model and all(isinstance(s, str) for s in body["state"])
    q = body["questions"]
    a, b = list(q["J1a"]["criteria"]), list(q["J1b"]["criteria"])
    assert set(a) == set(b) >= {"1.250,00", "1.000,00", "250,00", "not_stated"} and a == b[::-1]
    assert {k for k in q if k.startswith("J2.")} == {"J2.total", "J2.currency"}
    assert result.risk == 0 and len(result.answers) == 4 and result.calls[0].role == "jev"


def test_disagreeing_j1_and_misread_j2_raise_the_risk(jev_on, monkeypatch, tmp_path):
    def liar(questions):
        out = _honest(questions)
        out["J1b"] = {"type": "choice", "choice": "1.000,00", "probabilities": {"1.000,00": 0.8}}
        out["J2.total"] = {"type": "noul", "noul": 0.97}
        return out

    _fake(monkeypatch, liar)
    result = _run(tmp_path)
    assert result.risk > 0.9
    assert any("J1 answers disagree" in n for n in result.notes)
    assert any("total may be misread" in n for n in result.notes)


def test_j1_not_matching_the_reader_raises_the_risk(jev_on, monkeypatch, tmp_path):
    def other(questions):
        out = _honest(questions)
        for name in ("J1a", "J1b"):
            out[name] = {"type": "choice", "choice": "1.000,00", "probabilities": {"1.000,00": 0.9}}
        return out

    _fake(monkeypatch, other)
    assert _run(tmp_path).risk >= 0.6


def test_any_failure_escalates_with_risk_1(jev_on, monkeypatch, tmp_path):
    def broken(url, json, timeout, headers):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(jev.httpx, "post", broken)
    result = _run(tmp_path)
    assert result.risk == 1.0 and result.notes[0].startswith("JEV failed")
    assert list(tmp_path.glob("*.json")) == []


def test_replay_miss_escalates(jev_on, tmp_path):
    doc = _doc()
    result = jev.run_jev(doc, PRINTED, COMPUTED, {125_000}, cache=ResponseCache("replay", tmp_path))
    assert result.risk == 1.0 and "CacheMiss" in result.notes[0]


def test_switched_off_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "jev_enabled", False)
    assert _run(tmp_path) is None


def test_state_stays_text_only_and_under_32_kb():
    page = PageData(
        number=1, width=1, height=1, text="\n".join(f"line {i} " + "x" * 80 for i in range(2000))
    )
    state = jev._state(Ingested(channel=Channel.PDF, doc_sha256="0", pages=[page]))
    assert sum(len(s.encode()) for s in state) < 32_000 and state[-1] == "[text truncated]"
