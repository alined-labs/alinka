"""JEV on OpenRouter's Decisions API: escalate-only checks on what the reader returned.

- J1: a Choice between the page's regex money spans plus `not_stated` for "the total
  to pay", asked twice (J1a, J1b) with the options in two different orders. If the two answers
  disagree, or neither matches the reader's total, the risk rises.
- J2: one Noul per critical field the reader filled: "is this extracted value a
  misreading of the text?"
All questions go in one request per invoice. The state is text only and kept under about 32 KB, to stay out of long-context mode.
Calls go through the response cache. The budget is 8 s per invoice with one retry;
any failure sets the risk to 1.0. JEV can only raise the risk, never lower it.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass

import httpx

from alinka.cache import Fresh, ResponseCache, get_cache, sha256_text
from alinka.ingest.base import Ingested
from alinka.money import MINOR_DIGITS, format_minor
from alinka.settings import get_settings
from alinka.types import CRITICAL_FIELDS, Computed, JevAnswer, ModelCall, Printed

URL = "https://openrouter.ai/api/alpha/decisions"
BUDGET_S = 8.0
STATE_MAX_BYTES = 30_000
MAX_OPTIONS = 12
J2_MISREAD_MIN = 0.85  # a Noul at or above this says the field is misread
J2_DOUBT_MIN = 0.5  # from here up to J2_MISREAD_MIN, a graded doubt of at most 0.3
# Measured on the month: planted one-digit misreads score 0.98, correct values at most 0.71.
J1_WEAK = 0.6  # J1 chose the reader's total with less than this probability

J2_TEXT = {
    "beneficiary_name": "the name of the seller who wants to be paid",
    "beneficiary_tax_id": "the seller's tax ID",
    "invoice_number": "the invoice number",
    "currency": "the currency of the amount due",
    "total": "the total amount due",
    "due_date": "the payment due date",
}


@dataclass(frozen=True)
class JevResult:
    answers: tuple[JevAnswer, ...]
    risk: float
    notes: tuple[str, ...]
    calls: tuple[ModelCall, ...]


def run_jev(
    doc: Ingested,
    printed: Printed,
    computed: Computed,
    money: set[int],
    *,
    cache: ResponseCache | None = None,
    seed: str = "",
) -> JevResult | None:
    """None when JEV is switched off (JEV_ENABLED=0)."""
    settings = get_settings()
    if not settings.jev_enabled:
        return None
    cache = cache or get_cache()
    state = _state(doc)
    started = time.perf_counter()
    answers: list[JevAnswer] = []
    calls: list[ModelCall] = []
    notes: list[str] = []
    risk = 0.0
    try:
        questions = {
            **_j1_questions(computed, money, seed or doc.doc_sha256),
            **_j2_questions(printed),
        }
        if questions:
            body = {"model": settings.jev_model, "state": state, "questions": questions}
            result, call = _call(cache, body, started)
            calls.append(call)
            for qname in sorted(result["answers"]):
                answers.append(_answer(qname, result["answers"][qname]))
        risk, notes = _score(answers, computed)
    except Exception as exc:  # noqa: BLE001 - any JEV failure escalates
        return JevResult(
            answers=tuple(answers),
            risk=1.0,
            notes=(f"JEV failed: {type(exc).__name__}: {' '.join(str(exc).split())[:160]}",),
            calls=tuple(calls),
        )
    return JevResult(answers=tuple(answers), risk=risk, notes=tuple(notes), calls=tuple(calls))


def _state(doc: Ingested) -> list[str]:
    """Short text strings, one per visible line block, capped below long-context mode."""
    parts: list[str] = ["Untrusted invoice document, visible text extracted by code:"]
    size = len(parts[0].encode())
    for page in doc.pages:
        for line in page.text.splitlines():
            line = line.strip()
            if not line:
                continue
            n = len(line.encode()) + 8
            if size + n > STATE_MAX_BYTES:
                parts.append("[text truncated]")
                return parts
            parts.append(line)
            size += n
    return parts


def _option(minor: int, currency: str) -> str:
    return format_minor(minor, currency).rsplit(" ", 1)[0]


def _j1_questions(computed: Computed, money: set[int], seed: str) -> dict:
    """The same Choice twice, the options in two different shuffled orders."""
    currency = computed.currency
    if currency not in MINOR_DIGITS or not money:
        return {}
    amounts = sorted(money, reverse=True)[:MAX_OPTIONS]
    if computed.total_minor is not None and computed.total_minor not in amounts:
        amounts = [computed.total_minor, *amounts[: MAX_OPTIONS - 1]]
    options = [_option(a, currency) for a in amounts] + ["not_stated"]
    first = options[:]
    random.Random(sha256_text(seed + "J1")).shuffle(first)
    questions = {}
    for name, order in (("J1a", first), ("J1b", first[::-1])):
        questions[name] = {
            "type": "choice",
            "instructions": "Which amount is the total to pay on this invoice "
            "(the amount due, after taxes and withholdings)?",
            "criteria": {
                o: (
                    "the total to pay is not printed on the document"
                    if o == "not_stated"
                    else f"the total amount to pay is {o} {currency}"
                )
                for o in order
            },
        }
    return questions


def _j2_questions(printed: Printed) -> dict:
    questions = {}
    for name in CRITICAL_FIELDS:
        value = getattr(printed, name).value
        if value is None:
            continue
        questions[f"J2.{name}"] = {
            "type": "noul",
            "instructions": f"An extractor read {J2_TEXT[name]} as {json.dumps(value, ensure_ascii=False)}. "
            "Is this extracted value a misreading of the text?",
            "criteria": {
                "true": "the document shows a different value for this field (other "
                "characters, digits or words), or does not show it at all",
                "false": "the document shows this value for this field; labels, prefixes "
                "and formatting printed around it do not matter",
            },
        }
    return questions


def _call(cache: ResponseCache, body: dict, started: float) -> tuple[dict, ModelCall]:
    settings = get_settings()
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False)
    prompt_hash = sha256_text(json.dumps(sorted(body["questions"]), ensure_ascii=False))
    input_hash = sha256_text(canonical)

    def post() -> Fresh:
        key = settings.openrouter_api_key
        if key is None:
            raise RuntimeError("no OpenRouter key")
        last: Exception | None = None
        for _attempt in range(2):  # one retry
            left = BUDGET_S - (time.perf_counter() - started)
            if left <= 0.5:
                break
            try:
                response = httpx.post(
                    URL,
                    json=body,
                    timeout=left,
                    headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                )
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage") or {}
                return Fresh(
                    response={"answers": data["answers"], "model": data.get("model")},
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                    cost_usd=float(usage.get("cost") or 0.0),
                    stop_reason="end_turn",
                )
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
        raise TimeoutError(f"JEV budget of {BUDGET_S:.0f} s spent") from last

    request = {"role": "jev", "model": body["model"], "questions": sorted(body["questions"])}
    cached = cache.call(
        model=body["model"],
        prompt_hash=prompt_hash,
        input_hash=input_hash,
        request=request,
        fn=post,
    )
    return cached.response, cached.model_call("jev")


def _answer(name: str, raw: dict) -> JevAnswer:
    if raw.get("type") == "choice":
        choice = str(raw["choice"])
        probs = raw.get("probabilities") or {}
        return JevAnswer(
            question=name,
            answer=choice,
            probability=float(probs.get(choice, raw.get("confidence") or 0.0)),
            confidence=raw.get("confidence"),
        )
    p = float(raw["noul"])
    return JevAnswer(question=name, answer="yes" if p >= J2_MISREAD_MIN else "no", probability=p)


def _score(answers: list[JevAnswer], computed: Computed) -> tuple[float, list[str]]:
    parts: list[tuple[float, str]] = []
    j1 = [a for a in answers if a.question.startswith("J1")]
    if len(j1) == 2 and computed.currency and computed.total_minor is not None:
        reader = _option(computed.total_minor, computed.currency)
        a, b = (x.answer for x in j1)
        if a != b:
            parts.append((0.5, f"JEV J1 answers disagree: {a} vs {b}"))
        if reader not in (a, b):
            parts.append((0.6, f"JEV J1 chose {a} / {b}, the reader read {reader}"))
        elif min(x.probability for x in j1 if x.answer == reader) < J1_WEAK:
            parts.append((0.2, "JEV J1 is unsure of the total"))
    for a in answers:
        if not a.question.startswith("J2."):
            continue
        if a.probability >= J2_MISREAD_MIN:
            parts.append((min(a.probability, 0.95), f"JEV J2: {a.question[3:]} may be misread"))
        elif a.probability >= J2_DOUBT_MIN:
            doubt = 0.3 * (a.probability - J2_DOUBT_MIN) / (J2_MISREAD_MIN - J2_DOUBT_MIN)
            parts.append((round(doubt, 4), f"JEV J2: some doubt on {a.question[3:]}"))
    keep = 1.0
    for p, _ in parts:
        keep *= 1 - p
    return round(1 - keep, 4), [n for _, n in parts]
