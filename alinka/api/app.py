"""The Alinka API: the read-only canonical run and a private sandbox per visitor, on Postgres."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from importlib.metadata import version

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from alinka import db
from alinka.api import pages, sessions, store, try_routes, views
from alinka.api.deps import Conn, Sandbox, Viewed
from alinka.api.models import (
    ApprovalIn,
    BeneficiaryAdded,
    BeneficiaryIn,
    BeneficiaryView,
    Board,
    ChainCheck,
    ErrorOut,
    EvalOut,
    Health,
    InvoiceDetail,
    Log,
    PageImage,
    RulesIn,
    RulesOut,
    RulesSaved,
    RunResult,
)
from alinka.api.sessions import CANONICAL, Ctx
from alinka.decide.core import mask_account
from alinka.settings import get_settings
from alinka.types import Beneficiary, Contract, HumanAction, InvoiceFacts

ERRORS = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}

app = FastAPI(
    title="Alinka API",
    version=version("alinka"),
    description="La IA lee, las reglas deciden, el registro explica.",
    separate_input_output_schemas=False,
)
app.include_router(try_routes.router)


@app.middleware("http")
async def edge_secret(request: Request, call_next):
    """When EDGE_SECRET is set, only the Worker (which adds X-Edge-Secret) may call in."""
    secret = get_settings().edge_secret
    if secret and secret.get_secret_value() and request.url.path != "/api/health":
        given = request.headers.get("x-edge-secret", "")
        if not hmac.compare_digest(given.encode(), secret.get_secret_value().encode()):
            return JSONResponse({"detail": "Acceso denegado."}, status_code=403)
    return await call_next(request)


@app.exception_handler(sessions.Refused)
async def refused(_: Request, exc: sessions.Refused) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(sessions.NotFound)
async def not_found(_: Request, exc: sessions.NotFound) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=404)


# --- Building responses -----------------------------------------------------------


def build_board(conn: psycopg.Connection, ctx: Ctx) -> Board:
    recs = sessions.records(conn, ctx.session_id)
    done = sessions.latest(recs)
    cards = []
    for f in ctx.facts:
        ben = views.beneficiary_for(f, ctx.world)
        rec = done.get(f.source.invoice_id)
        cards.append(views.record_card(rec, ben, ctx.view) if rec else views.inbox_card(f, ben))
    head = recs[-1].hash if recs else None
    return views.board(ctx.session_id, ctx.view, ctx.rules.version, cards, head)


def find_facts(ctx: Ctx, invoice_id: str) -> InvoiceFacts:
    f = next((f for f in ctx.facts if f.source.invoice_id == invoice_id), None)
    if f is None:
        raise HTTPException(404, f"No existe la factura {invoice_id}.")
    return f


def detail(conn: psycopg.Connection, ctx: Ctx, invoice_id: str) -> InvoiceDetail:
    facts = find_facts(ctx, invoice_id)
    ben = views.beneficiary_for(facts, ctx.world)
    rec = sessions.latest(sessions.records(conn, ctx.session_id)).get(invoice_id)
    page_list = tuple(
        PageImage(
            n=i, url=f"/api/invoices/{invoice_id}/pages/{i}?view={ctx.view}", width=w, height=h
        )
        for i, (w, h) in enumerate(pages.page_sizes(facts.source.path), 1)
    )
    return InvoiceDetail(
        card=views.record_card(rec, ben, ctx.view) if rec else views.inbox_card(facts, ben),
        record=rec,
        pages=page_list,
        fields=views.field_views(facts.printed),
        rules=views.rule_views(rec) if rec else (),
        payment=rec.payment if rec else None,
    )


def beneficiary_view(b: Beneficiary, added: bool) -> BeneficiaryView:
    return BeneficiaryView(
        id=b.id,
        name=b.name,
        tax_id=b.tax_id,
        country=b.country,
        currency=b.currency,
        account_masked=mask_account(b.account_on_file),
        doc_types=b.doc_types,
        contract_id=b.contract.id,
        rate_minor=b.contract.rate_minor,
        frequency=b.contract.frequency,
        cost_center=b.contract.cost_center,
        added_in_sandbox=added,
    )


def rules_out(ctx: Ctx) -> RulesOut:
    return RulesOut(
        session_id=ctx.session_id,
        view=ctx.view,
        rules=ctx.rules,
        rules_hash=store.rules_hash(ctx.rules),
        bounds=store.RULE_BOUNDS,
        beneficiaries=tuple(
            beneficiary_view(b, b.id in ctx.added) for b in ctx.world.beneficiaries
        ),
    )


def reload(conn: psycopg.Connection, ctx: Ctx) -> Ctx:
    fresh = sessions.context(conn, ctx.session_id)
    assert fresh is not None
    return fresh


# --- Routes -----------------------------------------------------------------------


@app.get("/api/health")
def health() -> Health:
    try:
        with db.connection() as conn:
            head = conn.execute(
                "SELECT hash FROM decisions WHERE session_id = %s ORDER BY seq DESC LIMIT 1",
                (CANONICAL,),
            ).fetchone()
    except Exception:  # noqa: BLE001 - health reports, never raises
        return Health(status="degraded", version=app.version, database=False)
    canonical_head = head["hash"] if head else None
    return Health(status="ok", version=app.version, canonical_head=canonical_head, database=True)


@app.get("/api/board")
def get_board(ctx: Viewed, conn: Conn) -> Board:
    return build_board(conn, ctx)


@app.post("/api/run")
def run_agent(ctx: Sandbox, conn: Conn) -> RunResult:
    """Ejecutar agente: decide the sandbox's inbox in received order from the recorded facts."""
    steps = sessions.run_inbox(conn, ctx)
    return RunResult(decided=len(steps), steps=tuple(steps), board=build_board(conn, ctx))


@app.get("/api/invoices/{invoice_id}", responses=ERRORS)
def get_invoice(invoice_id: str, ctx: Viewed, conn: Conn) -> InvoiceDetail:
    return detail(conn, ctx, invoice_id)


@app.get(
    "/api/invoices/{invoice_id}/pages/{n}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, 404: {"model": ErrorOut}},
)
def get_page(invoice_id: str, n: int, ctx: Viewed) -> Response:
    facts = find_facts(ctx, invoice_id)
    png = pages.render_page(facts.source.path, n, invoice_id)
    if png is None:
        raise HTTPException(404, f"La factura {invoice_id} no tiene página {n}.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/rules")
def get_rules(ctx: Viewed) -> RulesOut:
    return rules_out(ctx)


@app.put("/api/rules", responses={422: {"model": ErrorOut}})
def put_rules(body: RulesIn, ctx: Sandbox, conn: Conn) -> RulesSaved:
    """Save the sandbox's rules (range-checked) and re-decide the sandbox."""
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        b = store.RULE_BOUNDS[key]
        if not b.min <= value <= b.max:
            raise HTTPException(422, f"{key} debe estar entre {b.min:g} y {b.max:g}.")
    if changes:
        with conn.transaction():
            sessions.save_rules(conn, ctx.session_id, ctx.rules.model_copy(update=changes))
        sessions.redecide(conn, ctx.session_id)
    ctx = reload(conn, ctx)
    return RulesSaved(rules=rules_out(ctx), board=build_board(conn, ctx))


@app.post("/api/beneficiaries", responses={409: {"model": ErrorOut}})
def add_beneficiary(body: BeneficiaryIn, ctx: Sandbox, conn: Conn) -> BeneficiaryAdded:
    """Add a beneficiary to the sandbox's list (the way out of R01), then re-decide."""
    if any(views.norm_id(b.tax_id) == views.norm_id(body.tax_id) for b in ctx.world.beneficiaries):
        raise HTTPException(409, f"Ya existe un beneficiario con identificación {body.tax_id}.")
    n = len(ctx.added) + 1
    ben = Beneficiary(
        id=f"SBX-{n:02d}",
        **body.model_dump(exclude={"contract"}),
        contract=Contract(
            id=f"CTR-SBX-{n:02d}", currency=body.currency, **body.contract.model_dump()
        ),
    )
    with conn.transaction():
        sessions.add_beneficiary(conn, ctx.session_id, ben)
    sessions.redecide(conn, ctx.session_id)
    ctx = reload(conn, ctx)
    return BeneficiaryAdded(beneficiary=beneficiary_view(ben, True), board=build_board(conn, ctx))


def act(invoice_id: str, body: ApprovalIn, ctx: Ctx, conn, action: str) -> InvoiceDetail:
    approver = body.approver.strip()
    if not approver:
        raise HTTPException(422, "El nombre de quien aprueba es obligatorio.")
    human = HumanAction(action=action, approver=approver, note=body.note, at=datetime.now(UTC))
    sessions.act(conn, ctx, invoice_id, human)
    return detail(conn, ctx, invoice_id)


@app.post("/api/invoices/{invoice_id}/approve", responses=ERRORS)
def approve(invoice_id: str, body: ApprovalIn, ctx: Sandbox, conn: Conn) -> InvoiceDetail:
    return act(invoice_id, body, ctx, conn, "approve")


@app.post("/api/invoices/{invoice_id}/reject", responses=ERRORS)
def reject(invoice_id: str, body: ApprovalIn, ctx: Sandbox, conn: Conn) -> InvoiceDetail:
    return act(invoice_id, body, ctx, conn, "reject")


@app.post("/api/sandbox/reset")
def reset(ctx: Sandbox, conn: Conn) -> Board:
    """A fresh sandbox, copied from the canonical run, under the same cookie."""
    return build_board(conn, sessions.create_sandbox(conn, ctx.session_id))


@app.get("/api/log")
def get_log(ctx: Viewed, conn: Conn) -> Log:
    recs = sessions.records(conn, ctx.session_id)
    return Log(
        session_id=ctx.session_id,
        view=ctx.view,
        head_hash=recs[-1].hash if recs else None,
        entries=tuple(views.log_entry(r) for r in recs),
    )


@app.get("/api/log/verify")
def verify_log(ctx: Viewed, conn: Conn) -> ChainCheck:
    """Verificar cadena: recompute every hash from the stored canonical bytes."""
    return store.verify_chain(db.chain_rows(conn, ctx.session_id))


@app.get(
    "/api/log/export.csv",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_log(ctx: Viewed, conn: Conn) -> PlainTextResponse:
    names = {}
    for f in ctx.facts:
        ben = views.beneficiary_for(f, ctx.world)
        names[f.source.invoice_id] = ben.name if ben else None
    return PlainTextResponse(
        store.export_csv(sessions.records(conn, ctx.session_id), names),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="alinka-{ctx.view}.csv"'},
    )


@app.get("/api/eval")
def get_eval() -> EvalOut:
    report = store.eval_report()
    return EvalOut(available=report is not None, report=report)
