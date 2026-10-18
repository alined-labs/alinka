"""One document to `InvoiceFacts`: sanitize, read twice, verify in code."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import pymupdf

from alinka.cache import ResponseCache, get_cache, sha256_bytes
from alinka.extract.claude import Reading, read
from alinka.extract.schema import FIELD_ORDER
from alinka.ingest.base import Ingested
from alinka.ingest.dispatch import ingest_bytes
from alinka.types import (
    CRITICAL_FIELDS,
    Channel,
    Computed,
    Flags,
    InvoiceFacts,
    Language,
    Printed,
    RulesConfig,
    Source,
    Verification,
)
from alinka.verify import checks
from alinka.verify.ground import ground
from alinka.verify.jev import run_jev
from alinka.verify.normalize import compute
from alinka.world import load_rules, load_world

ROOT = Path(__file__).resolve().parents[2]
CHANNELS = {".pdf": Channel.PDF, ".eml": Channel.EMAIL, ".txt": Channel.CHAT}


def facts_for_path(
    path: Path,
    *,
    invoice_id: str,
    received_at: datetime,
    cache: ResponseCache | None = None,
    cfg: RulesConfig | None = None,
) -> tuple[InvoiceFacts, Ingested | None]:
    data = path.read_bytes()
    try:
        rel = str(path.resolve().relative_to(ROOT))
    except ValueError:
        rel = path.name
    return facts_for_bytes(
        data, path.suffix, invoice_id=invoice_id, received_at=received_at, path=rel,
        cache=cache, cfg=cfg,
    )  # fmt: skip


def facts_for_bytes(
    data: bytes,
    suffix: str,
    *,
    invoice_id: str,
    received_at: datetime,
    path: str | None = None,
    cache: ResponseCache | None = None,
    cfg: RulesConfig | None = None,
) -> tuple[InvoiceFacts, Ingested | None]:
    cfg = cfg or load_rules()
    cache = cache or get_cache()
    channel = CHANNELS.get(suffix.lower(), Channel.IMAGE)
    try:
        doc = ingest_bytes(data, suffix)
    except Exception as exc:  # noqa: BLE001 - an unreadable file escalates
        source = Source(
            invoice_id=invoice_id, doc_sha256=sha256_bytes(data), path=path,
            channel=channel, received_at=received_at,
        )  # fmt: skip
        error = f"ingest: {type(exc).__name__}: {' '.join(str(exc).split())[:200]}"
        return InvoiceFacts(
            source=source, as_of=cfg.as_of, flags=Flags(extraction_error=error)
        ), None

    reader = read(doc, role="reader", cache=cache)
    checker = read(doc, role="checker", cache=cache) if reader.error is None else None
    printed, computed, verification = verify(doc, reader, checker, cfg)
    jev = None
    if reader.error is None:
        money = checks.money_spans(doc, computed.currency)
        jev = run_jev(doc, printed, computed, money, cache=cache)
    if jev is not None:  # JEV can only raise the risk
        verification = verification.model_copy(
            update={
                "jev": jev.answers,
                "risk": round(1 - (1 - verification.risk) * (1 - jev.risk), 4),
                "notes": verification.notes + jev.notes,
            }
        )
    flags = Flags(
        hidden_content=tuple(doc.hidden_content),
        unicode_controls=tuple(doc.unicode_controls),
        html_text_mismatch=doc.html_text_mismatch,
        instructions=tuple(doc.instructions),
        reader_instructions=reader.instructions_seen,
        extraction_error=reader.error,
    )
    source = Source(
        invoice_id=invoice_id,
        doc_sha256=doc.doc_sha256,
        path=path,
        channel=doc.channel,
        language=reader.language,
        received_at=received_at,
        pages=len(doc.pages),
    )
    calls = tuple(r.call for r in (reader, checker) if r is not None and r.call is not None)
    calls += jev.calls if jev is not None else ()
    facts = InvoiceFacts(
        source=source, as_of=cfg.as_of, printed=printed, computed=computed, flags=flags,
        verification=verification, calls=calls,
    )  # fmt: skip
    return facts, doc


@lru_cache(maxsize=1)
def _fx() -> tuple:
    return load_world().fx


def verify(
    doc: Ingested,
    reader: Reading,
    checker: Reading | None,
    cfg: RulesConfig,
    as_of: date | None = None,
) -> tuple[Printed, Computed, Verification]:
    if reader.error is not None:
        return reader.printed, Computed(), Verification(risk=1.0, notes=(reader.error,))
    month_first = reader.language == Language.EN
    computed = compute(reader.printed, cfg, _fx(), month_first)

    pdfs: dict[int, pymupdf.Document] = {}
    try:
        fields = {name: ground(getattr(reader.printed, name), doc, pdfs) for name in FIELD_ORDER}
    finally:
        for pdf in pdfs.values():
            pdf.close()
    notes: list[str] = []
    checker_failed = checker is None or checker.error is not None
    if checker is not None and checker.error is None:
        agreed = checks.compare(reader.printed, checker.printed, computed.currency, month_first)
        fields = {n: f.model_copy(update={"agreed": agreed[n]}) for n, f in fields.items()}
    elif checker is not None:
        notes.append(checker.error or "checker failed")
    printed = reader.printed.model_copy(update=fields)

    ungrounded = [
        n for n in CRITICAL_FIELDS if fields[n].value is not None and not fields[n].grounded
    ]
    disagreements = [n for n in CRITICAL_FIELDS if fields[n].agreed is False]
    in_regex = checks.amount_in_regex(doc, computed)
    reconcile = checks.totals_reconcile(computed)
    ocr = [p.ocr_confidence for p in doc.pages if p.ocr_confidence is not None]
    risk, why = checks.risk(
        printed, ungrounded=ungrounded, disagreements=disagreements, in_regex=in_regex,
        reconcile=reconcile, checker_failed=checker_failed, ocr_confidence=min(ocr) if ocr else None,
    )  # fmt: skip
    verification = Verification(
        disagreements=tuple(disagreements),
        ungrounded=tuple(ungrounded),
        amount_in_regex=in_regex,
        totals_reconcile=reconcile,
        risk=risk,
        notes=tuple(notes + why),
    )
    return printed, computed, verification
