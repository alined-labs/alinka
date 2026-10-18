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
    Printed,
    RulesConfig,
    Source,
    Verification,
)
from alinka.verify import checks
from alinka.verify.dateorder import ambiguous_fields, date_order
from alinka.verify.ground import ground
from alinka.verify.jev import JevResult, run_jev
from alinka.verify.normalize import compute, detect_currency
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
    staged = Staged(
        data, suffix, invoice_id=invoice_id, received_at=received_at, path=path,
        cache=cache, cfg=cfg,
    )  # fmt: skip
    staged.ingest()
    staged.read()
    staged.check()
    return staged.facts(), staged.doc


class Staged:
    """The same pipeline one stage at a time (ingest, read, check), so Probar can show
    each stage as it finishes. `facts()` works after any stage."""

    def __init__(
        self,
        data: bytes,
        suffix: str,
        *,
        invoice_id: str,
        received_at: datetime,
        path: str | None = None,
        cache: ResponseCache | None = None,
        cfg: RulesConfig | None = None,
    ) -> None:
        self.data, self.suffix, self.path = data, suffix, path
        self.invoice_id, self.received_at = invoice_id, received_at
        self.cfg = cfg or load_rules()
        self.cache = cache or get_cache()
        self.doc: Ingested | None = None
        self.error: str | None = None  # ingest or stage failure: R10 escalates
        self.reader: Reading | None = None
        self.checker: Reading | None = None
        self.checked: tuple[Printed, Computed, Verification] | None = None
        self.jev: JevResult | None = None

    def ingest(self) -> None:
        try:
            self.doc = ingest_bytes(self.data, self.suffix)
        except Exception as exc:  # noqa: BLE001 - an unreadable file escalates
            self.error = f"ingest: {type(exc).__name__}: {' '.join(str(exc).split())[:200]}"

    def read(self) -> None:
        if self.doc is not None and self.error is None:
            self.reader = read(self.doc, role="reader", cache=self.cache)

    def check(self) -> None:
        doc, reader = self.doc, self.reader
        if doc is None or reader is None:
            return
        if reader.error is None:
            self.checker = read(doc, role="checker", cache=self.cache)
        printed, computed, verification = verify(doc, reader, self.checker, self.cfg)
        if reader.error is None:
            money = checks.money_spans(doc, computed.currency)
            self.jev = run_jev(doc, printed, computed, money, cache=self.cache)
        if self.jev is not None:  # JEV can only raise the risk
            verification = verification.model_copy(
                update={
                    "jev": self.jev.answers,
                    "risk": round(1 - (1 - verification.risk) * (1 - self.jev.risk), 4),
                    "notes": verification.notes + self.jev.notes,
                }
            )
        self.checked = printed, computed, verification

    def fail(self, stage: str, exc: Exception) -> None:
        """An unexpected failure in a stage: record it so the rules escalate."""
        self.error = (
            self.error or f"{stage}: {type(exc).__name__}: {' '.join(str(exc).split())[:200]}"
        )

    def facts(self) -> InvoiceFacts:
        doc, reader = self.doc, self.reader
        channel = doc.channel if doc else CHANNELS.get(self.suffix.lower(), Channel.IMAGE)
        source = Source(
            invoice_id=self.invoice_id,
            doc_sha256=doc.doc_sha256 if doc else sha256_bytes(self.data),
            path=self.path,
            channel=channel,
            language=reader.language if reader else None,
            received_at=self.received_at,
            pages=len(doc.pages) if doc else int(channel is Channel.IMAGE),  # a photo is a page
        )
        if doc is None:
            return InvoiceFacts(
                source=source, as_of=self.cfg.as_of, flags=Flags(extraction_error=self.error)
            )
        if self.checked is not None:
            printed, computed, verification = self.checked
        else:
            printed, computed, verification = (
                reader.printed if reader else Printed(),
                Computed(),
                Verification(),
            )
        error = self.error or (reader.error if reader else "read: not run")
        flags = Flags(
            hidden_content=tuple(doc.hidden_content),
            unicode_controls=tuple(doc.unicode_controls),
            html_text_mismatch=doc.html_text_mismatch,
            instructions=tuple(doc.instructions),
            reader_instructions=reader.instructions_seen if reader else (),
            extraction_error=error,
        )
        calls = tuple(
            r.call for r in (reader, self.checker) if r is not None and r.call is not None
        )
        calls += self.jev.calls if self.jev is not None else ()
        return InvoiceFacts(
            source=source, as_of=self.cfg.as_of, printed=printed, computed=computed,
            flags=flags, verification=verification, calls=calls,
        )  # fmt: skip


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
    currency = detect_currency(
        reader.printed.currency.value, reader.printed.total.quote, reader.printed.total.value,
        reader.printed.amount_in_words.value,
    )  # fmt: skip
    dates = date_order(reader.printed, reader.language, currency)
    computed = compute(reader.printed, cfg, _fx(), dates.order)

    pdfs: dict[int, pymupdf.Document] = {}
    try:
        fields = {name: ground(getattr(reader.printed, name), doc, pdfs) for name in FIELD_ORDER}
    finally:
        for pdf in pdfs.values():
            pdf.close()
    notes: list[str] = [f"date order {dates.order or 'unknown'}: {dates.reason}"]
    checker_failed = checker is None or checker.error is not None
    if checker is not None and checker.error is None:
        agreed = checks.compare(reader.printed, checker.printed, computed.currency, dates.order)
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
        ambiguous_dates=ambiguous_fields(reader.printed, dates.order),
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
