"""Probar: run one document through the real pipeline in the visitor's sandbox and stream
each step as it happens (decision "Probar contract").

A sample is read from the response cache in replay mode (no keys, no model calls); the
sanitizer, the checks, the 16 rules, the decision and the log run live. The new invoice
lands on the sandbox board like any other. Jobs live in this process: at most 2 run at
once, 1 per visitor, and each keeps its events for 10 minutes for late subscribers.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from collections import deque
from collections.abc import AsyncIterable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError

from alinka import db, trace
from alinka.api import engine, runs, sessions
from alinka.api.deps import SANDBOX_COOKIE, Conn, Sandbox
from alinka.api.models import (
    ErrorOut,
    Sample,
    Samples,
    TryDone,
    TryError,
    TryIn,
    TryStarted,
    UploadLimits,
)
from alinka.cache import ResponseCache
from alinka.jobs.extract import load_labels
from alinka.types import DECISION_ES, Label
from alinka.verify.facts import Staged

log = logging.getLogger(__name__)
router = APIRouter()

ROOT = Path(__file__).resolve().parents[2]
WORKERS = 2  # runs at once on the server
QUEUE_MAX = 8  # runs waiting for a worker before new ones are refused
KEEP_S = 600  # how long a job's events stay available
PING_S = 10.0
SAMPLES_PER_HOUR = 60  # sample runs per client IP
LIMITS = UploadLimits()
ERROR_ES = "Error técnico: no se pudo procesar la factura y no quedó nada registrado."

Kind = Literal["routine", "trap", "attack"]


@dataclass(frozen=True)
class SampleDef:
    id: str
    kind: Kind
    title_es: str
    hint_es: str
    document: str = ""  # the dataset invoice whose file it runs; default: id

    @property
    def label(self) -> Label:
        return _labels()[self.document or self.id]


SAMPLES: tuple[SampleDef, ...] = (
    SampleDef(
        "GEN-084-1", "routine", "Factura de rutina en PDF",
        "Todo cuadra con el contrato: mira cómo cada dato lleva su cita y las 16 reglas pasan.",
    ),
    SampleDef(
        "DUP-GEN-084-1", "trap", "La misma factura, enviada otra vez",
        "Es la factura de rutina reenviada: pruébala después de esa y la regla de duplicados"
        " la frena.",
        document="GEN-084-1",
    ),
    SampleDef(
        "GEN-090-1", "trap", "Beneficiario nuevo por correo",
        "Quien cobra no está en la lista de beneficiarios: la factura espera a una persona.",
    ),
    SampleDef(
        "GEN-035-1", "trap", "Por encima del umbral de aprobación",
        "El monto en dólares supera el umbral, así que una persona debe aprobarla.",
    ),
    SampleDef(
        "ATK-01-1", "attack", "Texto blanco oculto",
        "El PDF esconde texto en blanco sobre blanco; el sanitizador lo encuentra antes de"
        " que la IA lea.",
    ),
    SampleDef(
        "ATK-10-1", "attack", "Correo de cambio de cuenta",
        "Pide pagar a una cuenta nueva: la cuenta siempre sale de la lista, nunca del correo.",
    ),
    SampleDef(
        "ATK-07-1", "attack", "Nombre parecido",
        "El nombre imita a un proveedor real con una letra cambiada; la identificación no"
        " coincide.",
    ),
    SampleDef(
        "GEN-012-1", "routine", "Foto tomada con el celular",
        "Una foto se lee con OCR y con la imagen; mira la confianza de cada dato.",
    ),
    SampleDef(
        "ATK-12-1", "attack", "Chat con caracteres invisibles",
        "El mensaje lleva caracteres de ancho cero que esconden instrucciones; se detectan y"
        " se quitan.",
    ),
)  # fmt: skip


@lru_cache(maxsize=1)
def _labels() -> dict[str, Label]:
    return {label.invoice_id: label for label in load_labels("all")}


@lru_cache(maxsize=1)
def _pages() -> dict[str, int]:
    """Page counts from the recorded run of all 175, when it is there."""
    try:
        return {f.source.invoice_id: f.source.pages for f in runs.load_facts("all-jev-on")}
    except FileNotFoundError:
        return {}


def samples() -> tuple[Sample, ...]:
    out = []
    for s in SAMPLES:
        label = s.label
        out.append(
            Sample(
                id=s.id, title_es=s.title_es, channel=label.channel, kind=s.kind,
                hint_es=s.hint_es, pages=_pages().get(label.invoice_id, 1), preview_url=None,
            )
        )  # fmt: skip
    return tuple(out)


# --- Limits -----------------------------------------------------------------------


class Window:
    """At most `limit` hits per key in a sliding window of `seconds`."""

    def __init__(self, limit: int, seconds: float) -> None:
        self.limit, self.seconds = limit, seconds
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def take(self, key: str) -> int | None:
        """Count a hit and return None, or return the seconds to wait when full."""
        now = time.monotonic()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and q[0] <= now - self.seconds:
                q.popleft()
            if len(q) >= self.limit:
                return max(int(q[0] + self.seconds - now) + 1, 1)
            q.append(now)
            return None


def client_ip(request: Request) -> str:
    """X-Client-IP from the Worker, else the connection's address."""
    ip = request.headers.get("x-client-ip", "").strip()
    return ip or (request.client.host if request.client else "unknown")


def too_many(message: str, retry_after: int) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(retry_after)})


# --- Jobs -------------------------------------------------------------------------


@dataclass
class Job:
    id: str
    session_id: str
    created: float = field(default_factory=time.monotonic)
    events: list[ServerSentEvent] = field(default_factory=list)
    finished: bool = False

    def emit(self, event: str, data: object) -> None:
        self.events.append(ServerSentEvent(event=event, data=data))


class Jobs:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        self.busy: set[str] = set()  # sessions with a job queued or running
        self.waiting = 0
        self.pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="try")
        self.samples = Window(SAMPLES_PER_HOUR, 3600)

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return job if job and time.monotonic() - job.created < KEEP_S else None

    def start(self, session_id: str, work: Callable[[Job], None]) -> Job:
        with self.lock:
            now = time.monotonic()
            for jid in [j for j, job in self.jobs.items() if now - job.created >= KEEP_S]:
                del self.jobs[jid]
            if session_id in self.busy:
                raise too_many("Ya tienes una prueba en curso; espera a que termine.", 5)
            if self.waiting >= QUEUE_MAX:
                raise too_many("Hay muchas pruebas en curso; intenta en unos segundos.", 10)
            job = Job(id=secrets.token_urlsafe(12), session_id=session_id)
            self.jobs[job.id] = job
            self.busy.add(session_id)
            self.waiting += 1
        self.pool.submit(self._run, job, work)
        return job

    def _run(self, job: Job, work: Callable[[Job], None]) -> None:
        with self.lock:
            self.waiting -= 1
        try:
            work(job)
        except Exception:  # noqa: BLE001 - the run failed as a whole: tell the page
            log.exception("try job %s failed", job.id)
            job.emit("error", TryError(message_es=ERROR_ES))
        finally:
            with self.lock:
                self.busy.discard(job.session_id)
            job.finished = True  # last, so a stream that ended means the visitor is free


JOBS = Jobs()


def _stage(
    job: Job,
    staged: Staged,
    step: trace.StepName,
    work: Callable[[], None] | None,
    build: Callable[[int], trace.TraceStep],
) -> None:
    """Emit the step as running, do its work, then emit its result with the real time."""
    job.emit("step", trace.running(step))
    t0 = time.perf_counter()
    failed = False
    if work is not None:
        try:
            work()
        except Exception as exc:  # noqa: BLE001 - a failing step escalates, the run goes on
            log.exception("try job %s: step %s failed", job.id, step)
            staged.fail(step, exc)
            failed = True
    result = build(round((time.perf_counter() - t0) * 1000))
    job.emit("step", result.model_copy(update={"status": "error"}) if failed else result)


def run_document(
    job: Job,
    *,
    data: bytes,
    suffix: str,
    prefix: str,
    sample_id: str | None,
    path: str | None,
    received_at: datetime,
    mode: Literal["replay", "live"],
) -> None:
    """The seven steps for one document in the job's sandbox, ending in a done event."""
    with db.connection() as conn:
        ctx = sessions.context(conn, job.session_id)
        if ctx is None:
            raise RuntimeError("the sandbox expired")
        invoice_id = f"{prefix}-{sessions.tried_count(conn, job.session_id, prefix + '-') + 1}"
        staged = Staged(
            data, suffix, invoice_id=invoice_id, received_at=received_at, path=path,
            cache=ResponseCache(mode), cfg=ctx.rules,
        )  # fmt: skip
        risk_max = ctx.rules.verifier_risk_max
        _stage(job, staged, "received", staged.ingest,
               lambda ms: trace.received(staged.facts(), ms))  # fmt: skip
        _stage(job, staged, "sanitize", None, lambda ms: trace.sanitize(staged.facts(), ms))
        _stage(job, staged, "read", staged.read, lambda ms: trace.read(staged.facts(), mode, ms))
        _stage(job, staged, "verify", staged.check,
               lambda ms: trace.verify(staged.facts(), risk_max, ms))  # fmt: skip
        facts = staged.facts()

        job.emit("step", trace.running("rules"))
        t0 = time.perf_counter()
        marks: list[float] = []
        with conn.transaction():
            sessions.add_tried(conn, job.session_id, facts, sample_id)
            record = db.record_decision(
                job.session_id,
                lambda ledger: engine.decide(facts, ctx.world, ctx.rules, ledger),
                conn,
                marks,
            )
        done = time.perf_counter()
        decided, written = marks[0], marks[1]

    def ms(a: float, b: float) -> int:
        return round((b - a) * 1000)

    job.emit("step", trace.rules(record.results, ms(t0, decided)))
    job.emit("step", trace.running("decide"))
    job.emit("step", trace.decide(record, ms(decided, written)))
    job.emit("step", trace.running("record"))
    job.emit("step", trace.record(record, ms(written, done)))
    job.emit(
        "done",
        TryDone(
            invoice_id=record.invoice_id,
            decision=record.decision,
            label_es=DECISION_ES[record.decision],
            href=f"/facturas/{record.invoice_id}",
        ),
    )


def run_sample(job: Job, sample: SampleDef) -> None:
    label = sample.label
    file = ROOT / label.path
    run_document(
        job, data=file.read_bytes(), suffix=file.suffix,
        prefix=f"TRY-{sample.id}", sample_id=sample.id, path=label.path,
        received_at=label.received_at, mode="replay",
    )  # fmt: skip


# --- Routes -----------------------------------------------------------------------

TRY_ERRORS = {
    403: {"model": ErrorOut},
    404: {"model": ErrorOut},
    413: {"model": ErrorOut},
    415: {"model": ErrorOut},
    422: {"model": ErrorOut},
    429: {"model": ErrorOut},
}
TRY_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/TryIn"}},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {"file": {"type": "string", "format": "binary"}},
                    "required": ["file"],
                }
            },
        },
    }
}


def live_uploads(conn) -> bool:
    return db.setting(conn, "live_uploads", False) is True


@router.get("/api/try/samples")
def get_samples(conn: Conn) -> Samples:
    return Samples(live_uploads=live_uploads(conn), upload_limits=LIMITS, samples=samples())


@router.post("/api/try", status_code=202, responses=TRY_ERRORS, openapi_extra=TRY_BODY)
async def start_try(request: Request, ctx: Sandbox, conn: Conn) -> TryStarted:
    """Run a sample (JSON {"sample_id"}) or, while live uploads are on, an uploaded file."""
    kind = request.headers.get("content-type", "")
    if kind.startswith("multipart/form-data"):
        raise HTTPException(403, "Las subidas en vivo están desactivadas.")
    try:
        body = TryIn.model_validate_json(await request.body())
    except ValidationError as exc:
        raise HTTPException(422, 'Envía {"sample_id": ...} o un archivo.') from exc
    sample = next((s for s in SAMPLES if s.id == body.sample_id), None)
    if sample is None:
        raise HTTPException(404, f"No existe la muestra {body.sample_id}.")
    if wait := JOBS.samples.take(client_ip(request)):
        raise too_many(f"Llegaste al límite de {SAMPLES_PER_HOUR} pruebas por hora.", wait)
    conn.commit()  # a sandbox made by this request must be visible to the job's thread
    job = JOBS.start(ctx.session_id, lambda j: run_sample(j, sample))
    return TryStarted(job_id=job.id, events_url=f"/api/try/{job.id}/events")


def owned_job(job_id: str, request: Request) -> Job:
    job = JOBS.get(job_id)
    if job is None or request.cookies.get(SANDBOX_COOKIE) != job.session_id:
        raise HTTPException(404, f"No existe la prueba {job_id}.")
    return job


@router.get(
    "/api/try/{job_id}/events",
    response_class=EventSourceResponse,
    responses={404: {"model": ErrorOut}},
)
async def try_events(job: Annotated[Job, Depends(owned_job)]) -> AsyncIterable[ServerSentEvent]:
    """step events (each step running, then its result), then done, or error. Every
    subscriber gets all of them from the start; a ": ping" comment every 10 s."""
    sent = 0
    last = time.monotonic()
    while True:
        while sent < len(job.events):
            yield job.events[sent]
            sent += 1
            last = time.monotonic()
        if job.finished and sent == len(job.events):
            return
        if time.monotonic() - last >= PING_S:
            yield ServerSentEvent(comment="ping")
            last = time.monotonic()
        await asyncio.sleep(0.05)
