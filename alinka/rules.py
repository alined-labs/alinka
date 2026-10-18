"""The sixteen rules (PLAN section 7). Each is a pure function (facts, world, ledger, cfg).

A rule that needs the listed beneficiary passes as not applicable when R01 cannot resolve
one: R01 already escalates, and an unknown supplier must not turn into a HOLD elsewhere.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta

from alinka.decide.ledger import ACTIVE, SPENT, Ledger
from alinka.fx import usd_of
from alinka.money import format_minor, parse_amount
from alinka.types import (
    CRITICAL_FIELDS,
    Beneficiary,
    Confidence,
    InvoiceFacts,
    Outcome,
    RuleId,
    RuleResult,
    RulesConfig,
    Scalar,
)
from alinka.world import World

PASS, HOLD, ESCALATE = Outcome.PASS, Outcome.HOLD, Outcome.ESCALATE

# --- Normalisation ---------------------------------------------------------------


def norm_id(text: str | None) -> str | None:
    """Tax IDs, invoice numbers and fiscal IDs: NFKC, upper case, letters and digits only."""
    if not text:
        return None
    s = "".join(c for c in unicodedata.normalize("NFKC", text).upper() if c.isalnum())
    return s or None


def norm_text(text: str | None) -> str:
    """Names and free text: NFKC, casefold, accents removed, punctuation to spaces."""
    s = unicodedata.normalize("NFKC", text or "").casefold()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def scripts(text: str) -> set[str]:
    """Unicode scripts of the letters, from their character names (LATIN, CYRILLIC, GREEK...)."""
    out = set()
    for c in unicodedata.normalize("NFKC", text).casefold():
        if c.isalpha():
            out.add(unicodedata.name(c, "UNKNOWN").split()[0])
    return out


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def period_key(d: date | None, frequency: str) -> str | None:
    if d is None:
        return None
    if frequency == "monthly":
        return f"{d.year}-{d.month:02d}"
    if frequency == "biweekly":
        return f"{d.year}-{d.month:02d}-{'a' if d.day <= 15 else 'b'}"
    if frequency == "weekly":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return d.isoformat()  # per_delivery


# --- Facts the rules share ---------------------------------------------------------


def resolve(facts: InvoiceFacts, world: World, cfg: RulesConfig) -> Beneficiary | None:
    """The listed beneficiary whose tax ID and name both match, or None."""
    tax = norm_id(facts.printed.beneficiary_tax_id.value)
    name = facts.printed.beneficiary_name.value or ""
    if tax is None or len(scripts(name)) > 1:
        return None
    for ben in world.beneficiaries:
        if norm_id(ben.tax_id) == tax:
            return ben if similarity(name, ben.name) >= cfg.name_similarity_min else None
    return None


def claimed(facts: InvoiceFacts, world: World) -> Beneficiary | None:
    """The listed beneficiary the document claims to be: by tax ID, else the closest name."""
    tax = norm_id(facts.printed.beneficiary_tax_id.value)
    for ben in world.beneficiaries:
        if tax and norm_id(ben.tax_id) == tax:
            return ben
    name = facts.printed.beneficiary_name.value
    if not name or not world.beneficiaries:
        return None
    best = max(world.beneficiaries, key=lambda b: similarity(name, b.name))
    return best if similarity(name, best.name) >= 0.8 else None


def currency(facts: InvoiceFacts) -> str | None:
    if facts.computed.currency:
        return facts.computed.currency
    code = (facts.printed.currency.value or "").strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else None


def total_minor(facts: InvoiceFacts) -> int | None:
    if facts.computed.total_minor is not None:
        return facts.computed.total_minor
    cur = currency(facts)
    try:
        return parse_amount(facts.printed.total.value, cur) if cur else None
    except KeyError:
        return None


def usd_minor(facts: InvoiceFacts, world: World, cfg: RulesConfig) -> int | None:
    """USD minor units, rounded up, from the official rate in code; None when unknown."""
    total, cur = total_minor(facts), currency(facts)
    if total is None or cur is None:
        return None
    try:
        got = usd_of(total, cur, cfg.as_of, cfg.fx_max_age_days, world.fx)
    except KeyError:
        return None
    return None if got is None else got[0]


def period_base(facts: InvoiceFacts) -> date:
    c = facts.computed
    return c.period_start or c.issue_date or facts.source.received_at.date()


def invoice_number(facts: InvoiceFacts) -> str | None:
    return facts.computed.invoice_number_norm or norm_id(facts.printed.invoice_number.value)


def usd(minor: int) -> str:
    return format_minor(minor, "USD")


def limit(minor: int) -> str:
    """Configured limits are whole USD and read as written in the rules: 2.000 USD."""
    text = usd(minor)
    return text.replace(",00 USD", " USD")


def result(
    rule: RuleId,
    outcome: Outcome,
    key: str,
    *,
    security: bool = False,
    approvable: bool = True,
    **values: Scalar,
) -> RuleResult:
    return RuleResult(
        rule=rule,
        outcome=outcome,
        security=security,
        approvable=approvable,
        values=values,
        message_key=f"{rule}.{key}",
    )


def amount_unknown(rule: RuleId) -> RuleResult:
    return result(rule, ESCALATE, "amount_unknown")


# --- R01 to R16 ---------------------------------------------------------------------

Rule = Callable[[InvoiceFacts, World, Ledger, RulesConfig], RuleResult]


def r01(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    name = facts.printed.beneficiary_name.value or ""
    tax = norm_id(facts.printed.beneficiary_tax_id.value)
    shown = facts.printed.beneficiary_tax_id.value
    if len(scripts(name)) > 1:
        return result(
            "R01", ESCALATE, "mixed_scripts", security=True, approvable=False,
            name=name, scripts=", ".join(sorted(scripts(name))),
        )  # fmt: skip
    by_tax = next((b for b in world.beneficiaries if tax and norm_id(b.tax_id) == tax), None)
    if by_tax is not None:
        sim = round(similarity(name, by_tax.name), 3)
        if sim >= cfg.name_similarity_min:
            return result("R01", PASS, "ok", beneficiary_id=by_tax.id, name=by_tax.name)
        return result(
            "R01", ESCALATE, "tax_id_other_name", security=True, approvable=False,
            name=name, tax_id=shown, listed_name=by_tax.name, similarity=sim,
        )  # fmt: skip
    if world.beneficiaries and name:
        best = max(world.beneficiaries, key=lambda b: similarity(name, b.name))
        sim = round(similarity(name, best.name), 3)
        if sim >= cfg.name_similarity_min:
            return result(
                "R01", ESCALATE, "lookalike", security=True, approvable=False,
                name=name, tax_id=shown, listed_name=best.name, listed_tax_id=best.tax_id,
                similarity=sim,
            )  # fmt: skip
    return result("R01", ESCALATE, "not_listed", approvable=False, name=name, tax_id=shown)


def r02(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    ben, cur = resolve(facts, world, cfg), currency(facts)
    if cur is None:
        return result("R02", ESCALATE, "currency_unknown", printed=facts.printed.currency.value)
    if ben is not None and cur != ben.currency:
        return result(
            "R02", HOLD, "currency_mismatch",
            currency=cur, expected=ben.currency, country=ben.country, beneficiary=ben.name,
        )  # fmt: skip
    if cur != "USD" and usd_of(1, cur, cfg.as_of, cfg.fx_max_age_days, world.fx) is None:
        return result("R02", ESCALATE, "no_fx", currency=cur, max_age_days=cfg.fx_max_age_days)
    if ben is None:
        return result("R02", PASS, "not_applicable", currency=cur)
    return result("R02", PASS, "ok", currency=cur, country=ben.country)


def r03(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    ben = resolve(facts, world, cfg)
    number, fiscal = invoice_number(facts), norm_id(facts.printed.fiscal_id.value)
    total, cur = total_minor(facts), currency(facts)
    period = period_key(period_base(facts), ben.contract.frequency) if ben else None
    for e in ledger.entries():
        if e.status not in ACTIVE or e.invoice_id == facts.source.invoice_id:
            continue
        same_ben = ben is not None and e.beneficiary_id == ben.id
        if same_ben and number and e.invoice_number_norm == number:
            key = "duplicate_number"
        elif fiscal and e.fiscal_id_norm == fiscal:
            key = "duplicate_fiscal_id"
        elif e.doc_sha256 == facts.source.doc_sha256:
            key = "duplicate_document"
        elif same_ben and total == e.amount_minor and cur == e.currency and period == e.period:
            key = "duplicate_amount_period"
        else:
            continue
        return result(
            "R03", HOLD, key,
            invoice_number=facts.printed.invoice_number.value,
            beneficiary=ben.name if ben else facts.printed.beneficiary_name.value,
            earlier_invoice=e.invoice_id, earlier_status=str(e.status),
            earlier_date=e.decided.isoformat(), earlier_amount=format_minor(e.amount_minor, e.currency),
        )  # fmt: skip
    return result("R03", PASS, "ok")


def r04(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    ben = resolve(facts, world, cfg)
    if ben is None:
        return result("R04", PASS, "not_applicable")
    ctr, total, cur = ben.contract, total_minor(facts), currency(facts)
    if total is None or cur is None:
        return amount_unknown("R04")
    ceiling = ctr.rate_minor * (100 + ctr.tolerance_pct) / 100
    if cur == ctr.currency:
        over = total > ceiling
        shown, agreed = format_minor(total, cur), format_minor(ctr.rate_minor, ctr.currency)
    else:  # R02 holds already; compare in USD so the excess is still visible
        mine = usd_minor(facts, world, cfg)
        cap = usd_of(int(ceiling), ctr.currency, cfg.as_of, cfg.fx_max_age_days, world.fx)
        if mine is None or cap is None:
            return amount_unknown("R04")
        over = mine > cap[0]
        shown, agreed = usd(mine), format_minor(ctr.rate_minor, ctr.currency)
    if over:
        return result(
            "R04", HOLD, "over_rate",
            amount=shown, rate=agreed, tolerance_pct=ctr.tolerance_pct, contract=ctr.id,
        )  # fmt: skip
    text = norm_text(facts.printed.service_text.value)
    if not text:
        return result("R04", ESCALATE, "scope_unreadable", contract=ctr.id)
    keywords = [*ctr.scope_es, *ctr.scope_en]
    hit = next((k for k in keywords if norm_text(k) and f" {norm_text(k)} " in f" {text} "), None)
    if hit is None:
        return result(
            "R04", HOLD, "off_scope",
            service=facts.printed.service_text.value, scope=", ".join(ctr.scope_es), contract=ctr.id,
        )  # fmt: skip
    return result("R04", PASS, "ok", amount=shown, rate=agreed, keyword=hit, contract=ctr.id)


def r05(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    amount = usd_minor(facts, world, cfg)
    if amount is None:
        return amount_unknown("R05")
    cap = cfg.per_payment_cap_usd * 100
    if amount > cap:
        return result("R05", HOLD, "over_cap", approvable=False, usd=usd(amount), cap=limit(cap))
    return result("R05", PASS, "ok", usd=usd(amount), cap=limit(cap))


def r06(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    amount = usd_minor(facts, world, cfg)
    if amount is None:
        return amount_unknown("R06")
    threshold = cfg.approval_threshold_usd * 100
    band_floor = threshold * (100 - cfg.approval_band_pct) / 100
    values: dict[str, Scalar] = {"usd": usd(amount), "threshold": limit(threshold)}
    if amount > threshold:
        return result("R06", ESCALATE, "over_threshold", **values)
    values |= {"band_pct": cfg.approval_band_pct, "band_floor": usd(int(band_floor))}
    if amount >= band_floor:
        return result("R06", ESCALATE, "near_threshold", **values)
    return result("R06", PASS, "ok", **values)


def r07(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    amount = usd_minor(facts, world, cfg)
    if amount is None:
        return amount_unknown("R07")
    month = (cfg.as_of.year, cfg.as_of.month)
    spent = sum(
        e.usd_minor
        for e in ledger.entries()
        if e.status in SPENT and (e.decided.year, e.decided.month) == month
    )
    cap = cfg.monthly_cap_usd * 100
    values: dict[str, Scalar] = {"usd": usd(amount), "spent": usd(spent), "cap": limit(cap)}
    if spent + amount > cap:
        return result("R07", HOLD, "over_monthly_cap", approvable=False, **values)
    return result("R07", PASS, "ok", **values)


def r08(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    amount = usd_minor(facts, world, cfg)
    if amount is None:
        return amount_unknown("R08")
    entries = [e for e in ledger.entries() if e.status in SPENT]
    balance = world.company.balance_usd_minor - sum(e.usd_minor for e in entries)
    if amount > balance:
        return result(
            "R08", HOLD, "balance", approvable=False, usd=usd(amount), balance=usd(balance)
        )
    ben = resolve(facts, world, cfg)
    center = next(
        (c for c in world.company.cost_centers if ben and c.id == ben.contract.cost_center), None
    )
    if center is None:
        return result("R08", PASS, "balance_ok", usd=usd(amount), balance=usd(balance))
    month = (cfg.as_of.year, cfg.as_of.month)
    used = sum(
        e.usd_minor
        for e in entries
        if e.cost_center == center.id and (e.decided.year, e.decided.month) == month
    )
    left = center.budget_usd_minor - used
    values: dict[str, Scalar] = {
        "usd": usd(amount), "balance": usd(balance), "cost_center": center.name_es,
        "budget_left": usd(left), "budget": usd(center.budget_usd_minor),
    }  # fmt: skip
    if amount > left:
        return result("R08", HOLD, "budget", approvable=False, **values)
    return result("R08", PASS, "ok", **values)


def r09(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    due = facts.computed.due_date
    if due is None:
        return result("R09", ESCALATE, "due_unparseable", printed=facts.printed.due_date.value)
    limit = cfg.as_of - timedelta(days=cfg.due_grace_days)
    values: dict[str, Scalar] = {
        "due_date": due.isoformat(), "as_of": cfg.as_of.isoformat(), "grace_days": cfg.due_grace_days,
    }  # fmt: skip
    if due < limit:
        return result("R09", ESCALATE, "past_grace", days_past=(cfg.as_of - due).days, **values)
    return result("R09", PASS, "ok", **values)


def r10(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    if facts.flags.extraction_error:
        return result("R10", ESCALATE, "extraction_error", error=facts.flags.extraction_error[:200])
    v = facts.verification
    weak = [
        f
        for f in CRITICAL_FIELDS
        if getattr(facts.printed, f).value is not None
        and (getattr(facts.printed, f).confidence != Confidence.HIGH or not getattr(facts.printed, f).grounded)
    ]  # fmt: skip
    missing = [
        f
        for f in ("beneficiary_name", "currency", "total")
        if getattr(facts.printed, f).value is None
    ]
    disagree = sorted(
        {
            *v.disagreements,
            *(f for f in CRITICAL_FIELDS if getattr(facts.printed, f).agreed is False),
        }
    )
    if missing or total_minor(facts) is None:
        return result("R10", ESCALATE, "missing", fields=", ".join(missing) or "total")
    if v.ungrounded or weak:
        return result(
            "R10", ESCALATE, "low_confidence", fields=", ".join(sorted({*v.ungrounded, *weak}))
        )
    if disagree:
        return result("R10", ESCALATE, "disagreement", fields=", ".join(disagree))
    if v.amount_in_regex is False or v.totals_reconcile is False:
        return result(
            "R10", ESCALATE, "totals",
            amount_in_regex=v.amount_in_regex, totals_reconcile=v.totals_reconcile,
        )  # fmt: skip
    if v.risk >= cfg.verifier_risk_max:
        return result(
            "R10", ESCALATE, "risk", risk=round(v.risk, 3), risk_max=cfg.verifier_risk_max
        )
    return result("R10", PASS, "ok", risk=round(v.risk, 3), risk_max=cfg.verifier_risk_max)  # fmt: skip


def r11(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    fl = facts.flags
    found: list[tuple[str, tuple[str, ...]]] = [
        ("hidden_content", fl.hidden_content),
        ("unicode_controls", fl.unicode_controls),
        ("html_text_mismatch", ("HTML y texto plano difieren",) if fl.html_text_mismatch else ()),
        ("instructions", fl.instructions),
        ("reader_instructions", fl.reader_instructions),
    ]
    hits = [(k, items) for k, items in found if items]
    if hits:
        key, items = hits[0]
        return result(
            "R11", ESCALATE, key, security=True,
            detail=items[0][:160], findings=sum(len(i) for _, i in hits),
            kinds=", ".join(k for k, _ in hits),
        )  # fmt: skip
    return result("R11", PASS, "ok")


def digits(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text) if c.isdigit())


def r12(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    printed = facts.printed.bank_account.value
    ben = resolve(facts, world, cfg) or claimed(facts, world)
    if not printed or ben is None:
        return result("R12", PASS, "not_applicable")
    # Grouping-insensitive: the printed digits must sit inside the listed account's digits,
    # so a masked tail ("****0010") passes and any other account number does not.
    shown = digits(printed)
    foreign = len(shown) >= 4 and shown not in digits(ben.account_on_file)
    if foreign:
        return result(
            "R12", ESCALATE, "account_differs", security=True, approvable=False,
            printed=printed[:120], beneficiary=ben.name,
        )  # fmt: skip
    return result("R12", PASS, "ok", beneficiary=ben.name)


def r13(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    amount = usd_minor(facts, world, cfg)
    if amount is None:
        return amount_unknown("R13")
    ben = resolve(facts, world, cfg)
    received = facts.source.received_at.date()
    window = timedelta(days=cfg.split_window_days)
    prior = [
        e
        for e in ledger.entries()
        if ben is not None
        and e.beneficiary_id == ben.id
        and e.status in ACTIVE
        and e.invoice_id != facts.source.invoice_id
        and abs(received - e.received) <= window
    ]
    total = amount + sum(e.usd_minor for e in prior)
    threshold = cfg.split_threshold_usd * 100
    values: dict[str, Scalar] = {
        "usd": usd(amount), "window_total": usd(total), "threshold": limit(threshold),
        "window_days": cfg.split_window_days, "others": len(prior),
        "other_invoices": ", ".join(e.invoice_id for e in prior),
    }  # fmt: skip
    if total > threshold:
        return result("R13", ESCALATE, "split" if prior else "single", **values)
    return result("R13", PASS, "ok", **values)


def r14(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    ben = resolve(facts, world, cfg)
    if ben is None:
        return result("R14", PASS, "not_applicable")
    ctr, c = ben.contract, facts.computed
    start = c.period_start or c.issue_date or facts.source.received_at.date()
    end = c.period_end or start
    if start < ctr.valid_from or end > ctr.valid_to:
        return result(
            "R14", HOLD, "outside_validity",
            period_start=start.isoformat(), period_end=end.isoformat(),
            valid_from=ctr.valid_from.isoformat(), valid_to=ctr.valid_to.isoformat(), contract=ctr.id,
        )  # fmt: skip
    period = period_key(period_base(facts), ctr.frequency)
    if ctr.frequency != "per_delivery":
        same = [
            e
            for e in ledger.entries()
            if e.beneficiary_id == ben.id
            and e.status in ACTIVE
            and e.period == period
            and e.invoice_id != facts.source.invoice_id
        ]
        if same:
            return result(
                "R14", HOLD, "frequency",
                frequency=ctr.frequency, period=period, earlier_invoice=same[0].invoice_id,
                contract=ctr.id,
            )  # fmt: skip
    return result("R14", PASS, "ok", frequency=ctr.frequency, period=period)


def r15(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    words = facts.printed.amount_in_words.value
    c = facts.computed
    if not words:
        return result("R15", PASS, "not_printed")
    total, cur = total_minor(facts), currency(facts) or "USD"
    if c.words_unparseable or c.words_minor is None or total is None:
        return result("R15", ESCALATE, "unparseable", words=words[:160])
    if c.words_minor != total:
        return result(
            "R15", HOLD, "differs",
            words=words[:160], words_amount=format_minor(c.words_minor, cur),
            digits=format_minor(total, cur),
        )  # fmt: skip
    return result("R15", PASS, "ok", digits=format_minor(total, cur))


# Tax IDs a national e-invoice prints for any foreign buyer: Mexico's SAT generic RFC for
# foreign residents (CFDI). With the payer's name, they still identify the payer.
GENERIC_FOREIGN_BUYER_IDS = frozenset({"XEXX010101000"})

PAYABLE = re.compile(r"\b(factura|cuenta de cobro|cuenta cobro|invoice|tax invoice|bill)\b")
NOT_PAYABLE = re.compile(
    r"\b(proforma|pro forma|cotizacion|quotation|quote|estimate|presupuesto|nota credito|"
    r"nota de credito|credit note|orden de compra|purchase order)\b"
)
BAD_STAMPS = re.compile(r"\b(anulada|anulado|pagada|pagado|paid|void|borrador|draft|proforma)\b")


def r16(facts: InvoiceFacts, world: World, ledger: Ledger, cfg: RulesConfig) -> RuleResult:
    p, c, company = facts.printed, facts.computed, world.company
    doc = norm_text(p.doc_type.value)
    if NOT_PAYABLE.search(doc) or (doc and not PAYABLE.search(doc)):
        return result("R16", HOLD, "doc_type", doc_type=p.doc_type.value)
    stamps = [s for s in p.stamps if BAD_STAMPS.search(norm_text(s))]
    if stamps:
        return result("R16", HOLD, "stamp", stamp=", ".join(stamps))
    buyer = p.buyer_name.value
    if buyer and similarity(buyer, company.name) < cfg.name_similarity_min:
        if norm_text(company.name.split(",")[0]) not in norm_text(buyer):
            return result("R16", HOLD, "buyer", buyer=buyer, payer=company.name)
    buyer_tax = c.buyer_tax_id_norm or norm_id(p.buyer_tax_id.value)
    foreign_ok = buyer_tax in GENERIC_FOREIGN_BUYER_IDS and bool(buyer)  # name matched above
    if buyer_tax and buyer_tax != norm_id(company.tax_id) and not foreign_ok:
        return result(
            "R16", HOLD, "buyer_tax_id",
            buyer=buyer or "sin nombre", buyer_tax_id=p.buyer_tax_id.value or buyer_tax,
            payer=company.name, payer_tax_id=company.tax_id,
        )  # fmt: skip
    total = total_minor(facts)
    if total is not None and total <= 0:
        return result("R16", HOLD, "non_positive", total=p.total.value)
    if c.issue_date is not None and c.issue_date > cfg.as_of:
        return result(
            "R16",
            HOLD,
            "future_issue",
            issue_date=c.issue_date.isoformat(),
            as_of=cfg.as_of.isoformat(),
        )
    if not doc or not buyer:
        return result("R16", ESCALATE, "unreadable", doc_type=p.doc_type.value, buyer=buyer)
    return result("R16", PASS, "ok", doc_type=p.doc_type.value, buyer=buyer)


RULES: dict[RuleId, Rule] = {
    "R01": r01, "R02": r02, "R03": r03, "R04": r04, "R05": r05, "R06": r06, "R07": r07, "R08": r08,
    "R09": r09, "R10": r10, "R11": r11, "R12": r12, "R13": r13, "R14": r14, "R15": r15, "R16": r16,
}  # fmt: skip
