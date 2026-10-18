"""The Alinka API. D1: every route answers from alinka/api/fixtures/ (kept per sandbox in memory)."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from alinka.api import pages, store, views
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
    RunStep,
    View,
)
from alinka.settings import get_settings
from alinka.types import (
    Beneficiary,
    Contract,
    Decision,
    DecisionRecord,
    HumanAction,
    PaymentPreview,
    RulesConfig,
)

SANDBOX_COOKIE = "alinka_sandbox"
SANDBOX_TTL_S = 24 * 3600
CANONICAL = "canonical"
ERRORS = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}

app = FastAPI(
    title="Alinka API",
    version=version("alinka"),
    description="La IA lee, las reglas deciden, el registro explica.",
    separate_input_output_schemas=False,
)


@app.middleware("http")
async def edge_secret(request: Request, call_next):
    """When EDGE_SECRET is set, only the Worker (which adds X-Edge-Secret) may call in."""
    secret = get_settings().edge_secret
    if secret and secret.get_secret_value() and request.url.path != "/api/health":
        given = request.headers.get("x-edge-secret", "")
        if not hmac.compare_digest(given.encode(), secret.get_secret_value().encode()):
            return JSONResponse({"detail": "Acceso denegado."}, status_code=403)
    return await call_next(request)


# --- Sessions (fixture mode: in memory) -----------------------------------------


class Sandbox:
    def __init__(self, session_id: str) -> None:
        self.session = store.fixture_session(session_id, "sandbox", decided=False)
        self.rules: RulesConfig = store.load_rules()
        self.added: list[Beneficiary] = []


SANDBOXES: dict[str, Sandbox] = {}


def sandbox(request: Request, response: Response) -> Sandbox:
    """The visitor's sandbox from the HttpOnly cookie, created with a full inbox on first visit."""
    sid = request.cookies.get(SANDBOX_COOKIE)
    if not sid or sid not in SANDBOXES:
        sid = secrets.token_urlsafe(18)
        SANDBOXES[sid] = Sandbox(sid)
        response.set_cookie(
            SANDBOX_COOKIE,
            sid,
            max_age=SANDBOX_TTL_S,
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        )
    return SANDBOXES[sid]


SandboxDep = Annotated[Sandbox, Depends(sandbox)]
ViewQ = Annotated[View, Query(description="sandbox (default) or the read-only canonical run")]


def canonical() -> store.FixtureSession:
    return store.fixture_session(CANONICAL, "canonical", decided=True)


def session_for(view: View, sbx: Sandbox) -> store.FixtureSession:
    return canonical() if view == "canonical" else sbx.session


def beneficiaries(sbx: Sandbox | None) -> tuple[Beneficiary, ...]:
    return store.load_beneficiaries() + tuple(sbx.added if sbx else ())


def head(s: store.FixtureSession) -> str | None:
    return s.records[-1].hash if s.records else None


def latest(s: store.FixtureSession) -> dict[str, DecisionRecord]:
    """The last record per invoice: an approval appends a record after the escalation."""
    return {r.invoice_id: r for r in s.records}


def build_board(s: store.FixtureSession, rules: RulesConfig, bens) -> Board:
    done = latest(s)
    cards = []
    for f in s.facts:
        ben = views.beneficiary_for(f, bens)
        rec = done.get(f.source.invoice_id)
        cards.append(views.record_card(rec, ben, s.view) if rec else views.inbox_card(f, ben))
    return views.board(s.session_id, s.view, rules.version, cards, head(s))


def sandbox_board(sbx: Sandbox) -> Board:
    return build_board(sbx.session, sbx.rules, beneficiaries(sbx))


def redecide(sbx: Sandbox) -> None:
    """Fixture mode can't run the rules: re-deciding re-applies the fixture decisions."""
    sbx.session = store.fixture_session(sbx.session.session_id, "sandbox", decided=True)


def find_facts(s: store.FixtureSession, invoice_id: str):
    f = next((f for f in s.facts if f.source.invoice_id == invoice_id), None)
    if f is None:
        raise HTTPException(404, f"No existe la factura {invoice_id}.")
    return f


def beneficiary_view(b: Beneficiary, added: bool) -> BeneficiaryView:
    return BeneficiaryView(
        id=b.id,
        name=b.name,
        tax_id=b.tax_id,
        country=b.country,
        currency=b.currency,
        account_masked=views.mask_account(b.account_on_file),
        doc_types=b.doc_types,
        contract_id=b.contract.id,
        rate_minor=b.contract.rate_minor,
        frequency=b.contract.frequency,
        cost_center=b.contract.cost_center,
        added_in_sandbox=added,
    )


# --- Routes -------------------------------------------------------------------


@app.get("/api/health")
def health() -> Health:
    return Health(status="ok", version=app.version, canonical_head=head(canonical()))


@app.get("/api/board")
def get_board(sbx: SandboxDep, view: ViewQ = "sandbox") -> Board:
    if view == "canonical":
        return build_board(canonical(), store.load_rules(), beneficiaries(None))
    return sandbox_board(sbx)


@app.post("/api/run")
def run_agent(sbx: SandboxDep) -> RunResult:
    """Ejecutar agente: decide the sandbox's inbox in received order."""
    pending = {c.invoice_id for c in sandbox_board(sbx).inbox}
    redecide(sbx)
    steps = tuple(
        RunStep(
            invoice_id=r.invoice_id,
            decision=r.decision,
            determining_rule=r.determining_rule,
            elapsed_ms=40,
        )
        for r in sbx.session.records
        if r.invoice_id in pending
    )
    return RunResult(decided=len(steps), steps=steps, board=sandbox_board(sbx))


@app.get("/api/invoices/{invoice_id}", responses=ERRORS)
def get_invoice(invoice_id: str, sbx: SandboxDep, view: ViewQ = "sandbox") -> InvoiceDetail:
    s = session_for(view, sbx)
    facts = find_facts(s, invoice_id)
    bens = beneficiaries(None if view == "canonical" else sbx)
    ben = views.beneficiary_for(facts, bens)
    rec = latest(s).get(invoice_id)
    sizes = pages.page_sizes(facts.source.path)
    page_list = tuple(
        PageImage(n=i, url=f"/api/invoices/{invoice_id}/pages/{i}?view={view}", width=w, height=h)
        for i, (w, h) in enumerate(sizes, 1)
    )
    return InvoiceDetail(
        card=views.record_card(rec, ben, view) if rec else views.inbox_card(facts, ben),
        record=rec,
        pages=page_list,
        fields=views.field_views(facts.printed),
        rules=views.rule_views(rec) if rec else (),
        payment=rec.payment if rec else None,
    )


@app.get(
    "/api/invoices/{invoice_id}/pages/{n}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, 404: {"model": ErrorOut}},
)
def get_page(invoice_id: str, n: int, sbx: SandboxDep, view: ViewQ = "sandbox") -> Response:
    facts = find_facts(session_for(view, sbx), invoice_id)
    png = pages.render_page(facts.source.path, n, invoice_id)
    if png is None:
        raise HTTPException(404, f"La factura {invoice_id} no tiene página {n}.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


def rules_out(sbx: Sandbox, view: View) -> RulesOut:
    rules = store.load_rules() if view == "canonical" else sbx.rules
    added = {b.id for b in sbx.added} if view == "sandbox" else set()
    bens = beneficiaries(sbx if view == "sandbox" else None)
    return RulesOut(
        session_id=CANONICAL if view == "canonical" else sbx.session.session_id,
        view=view,
        rules=rules,
        rules_hash=store.rules_hash(rules),
        bounds=store.RULE_BOUNDS,
        beneficiaries=tuple(beneficiary_view(b, b.id in added) for b in bens),
    )


@app.get("/api/rules")
def get_rules(sbx: SandboxDep, view: ViewQ = "sandbox") -> RulesOut:
    return rules_out(sbx, view)


@app.put("/api/rules", responses={422: {"model": ErrorOut}})
def put_rules(body: RulesIn, sbx: SandboxDep) -> RulesSaved:
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        b = store.RULE_BOUNDS[key]
        if not b.min <= value <= b.max:
            raise HTTPException(422, f"{key} debe estar entre {b.min:g} y {b.max:g}.")
    sbx.rules = sbx.rules.model_copy(update=changes)
    redecide(sbx)
    return RulesSaved(rules=rules_out(sbx, "sandbox"), board=sandbox_board(sbx))


@app.post("/api/beneficiaries", responses={409: {"model": ErrorOut}})
def add_beneficiary(body: BeneficiaryIn, sbx: SandboxDep) -> BeneficiaryAdded:
    bens = beneficiaries(sbx)
    if any(views.norm_id(b.tax_id) == views.norm_id(body.tax_id) for b in bens):
        raise HTTPException(409, f"Ya existe un beneficiario con identificación {body.tax_id}.")
    n = len(sbx.added) + 1
    ben = Beneficiary(
        id=f"SBX-{n:02d}",
        **body.model_dump(exclude={"contract"}),
        contract=Contract(
            id=f"CTR-SBX-{n:02d}", currency=body.currency, **body.contract.model_dump()
        ),
    )
    sbx.added.append(ben)
    redecide(sbx)
    return BeneficiaryAdded(beneficiary=beneficiary_view(ben, True), board=sandbox_board(sbx))


def act(invoice_id: str, body: ApprovalIn, sbx: Sandbox, action: str) -> InvoiceDetail:
    rec = latest(sbx.session).get(invoice_id)
    if rec is None:
        find_facts(sbx.session, invoice_id)
        raise HTTPException(409, f"La factura {invoice_id} aún no tiene decisión.")
    if action == "approve" and not views.can_approve(rec, "sandbox"):
        raise HTTPException(409, f"La factura {invoice_id} no se puede aprobar.")
    if action == "reject" and (rec.decision != Decision.ESCALATE or rec.human is not None):
        raise HTTPException(409, f"La factura {invoice_id} no está pendiente de aprobación.")
    human = HumanAction(action=action, approver=body.approver, note=body.note, at=datetime.now(UTC))
    ben = views.beneficiary_for(rec.facts, beneficiaries(sbx))
    c = rec.facts.computed
    if action == "approve":
        decision = Decision.PAY
        reason = f"Pagada: aprobada por {body.approver}. {rec.reason_es}"
        payment = (
            PaymentPreview(
                beneficiary_id=ben.id,
                beneficiary_name=ben.name,
                account_masked=views.mask_account(ben.account_on_file),
                amount_minor=c.total_minor or 0,
                currency=c.currency or ben.currency,
                usd_minor=c.usd_minor or 0,
            )
            if ben
            else None
        )
    else:
        decision, payment = Decision.HOLD, None
        reason = f"Frenada: rechazada por {body.approver}. {rec.reason_es}"
    prev = sbx.session.records[-1].hash
    draft = rec.model_copy(
        update={
            "record_id": f"{sbx.session.session_id[:8]}-{len(sbx.session.records) + 1:04d}",
            "session": sbx.session.session_id,
            "seq": len(sbx.session.records) + 1,
            "prev_hash": prev,
            "decision": decision,
            "reason_es": reason,
            "payment": payment,
            "human": human,
            "created_at": human.at,
        }
    )
    new = draft.model_copy(update={"hash": store.chain_hash(prev, store.record_bytes(draft))})
    sbx.session.records.append(new)
    return get_invoice(invoice_id, sbx, "sandbox")


@app.post("/api/invoices/{invoice_id}/approve", responses=ERRORS)
def approve(invoice_id: str, body: ApprovalIn, sbx: SandboxDep) -> InvoiceDetail:
    return act(invoice_id, body, sbx, "approve")


@app.post("/api/invoices/{invoice_id}/reject", responses=ERRORS)
def reject(invoice_id: str, body: ApprovalIn, sbx: SandboxDep) -> InvoiceDetail:
    return act(invoice_id, body, sbx, "reject")


@app.post("/api/sandbox/reset")
def reset(sbx: SandboxDep) -> Board:
    fresh = Sandbox(sbx.session.session_id)
    SANDBOXES[sbx.session.session_id] = fresh
    return sandbox_board(fresh)


@app.get("/api/log")
def get_log(sbx: SandboxDep, view: ViewQ = "sandbox") -> Log:
    s = session_for(view, sbx)
    return Log(
        session_id=s.session_id,
        view=view,
        head_hash=head(s),
        entries=tuple(views.log_entry(r) for r in s.records),
    )


@app.get("/api/log/verify")
def verify_log(sbx: SandboxDep, view: ViewQ = "sandbox") -> ChainCheck:
    s = session_for(view, sbx)
    return store.verify_chain(
        [(r.seq, r.prev_hash, r.hash, store.record_bytes(r)) for r in s.records]
    )


@app.get(
    "/api/log/export.csv",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_log(sbx: SandboxDep, view: ViewQ = "sandbox") -> PlainTextResponse:
    s = session_for(view, sbx)
    bens = beneficiaries(None if view == "canonical" else sbx)
    names = {}
    for f in s.facts:
        ben = views.beneficiary_for(f, bens)
        names[f.source.invoice_id] = ben.name if ben else None
    return PlainTextResponse(
        store.export_csv(s.records, names),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="alinka-{view}.csv"'},
    )


@app.get("/api/eval")
def get_eval() -> EvalOut:
    report = store.eval_report()
    return EvalOut(available=report is not None, report=report)
