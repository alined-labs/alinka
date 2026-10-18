"""The evaluation set: 120 seeded invoices in episodes, with gold labels (PLAN section 8).

Run: uv run python data/generator/generate.py

Invoice IDs are GEN-<episode>-<n>. Each episode is decided as its own batch, in received
order, on a fresh ledger with the world files: most are one invoice, and the duplicate,
budget, frequency and split traps carry routine priors that pay first. The mix is 72
routine and 48 traps, 72 Spanish and 48 English, and 72 PDF, 12 image, 18 email and 18
chat. Details are seeded by run, shard and episode; labels come from traps.yaml.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from random import Random

import yaml
from channels import EXT, write_doc
from common import DATA, HERE, MONTHS_ES, amount_words_es, write_jsonl
from forms import Line, Spec, build

RUN = "gen-2026-10"
SHARDS = 4
COT = timezone(timedelta(hours=-5))
TRAPS = yaml.safe_load((HERE / "traps.yaml").read_text())
OUT = DATA / "generated"
D = date

# --- What each listed beneficiary bills ---------------------------------------------
# forms by language, number pattern, payment terms in days, line texts (with {m} for the
# month or module) and the share of the amount on each line.

MODS_ES = ["pagos", "reportes", "onboarding", "facturación", "configuración", "notificaciones"]
MODS_EN = ["payments", "reports", "onboarding", "billing", "settings", "notifications"]

CAT: dict[str, dict] = {
    "BEN-01": dict(
        forms={"es": "co_factura"},
        num="DEMO-FAC-{:04d}",
        start=510,
        terms=30,
        es=[
            ("Diseño de interfaz: pantallas del módulo de {mod}", 0.75),
            ("Actualización del sistema de diseño (componentes)", 0.25),
        ],
    ),
    "BEN-02": dict(
        forms={"es": "co_cobro"},
        num="{:03d}",
        start=120,
        terms=10,
        es=[("Desarrollo backend: API e integraciones del módulo de {mod}", 1.0)],
    ),
    "BEN-03": dict(
        forms={"es": "co_cobro", "en": "us_invoice"},
        num="2026-{:03d}",
        start=140,
        terms=15,
        es=[("Desarrollo frontend: componentes de la interfaz web del módulo de {mod}", 1.0)],
        en=[("Frontend development: React components for the {mod} web interface", 1.0)],
    ),
    "BEN-04": dict(
        forms={"es": "co_factura"},
        num="CST-{:04d}",
        start=610,
        terms=30,
        es=[
            ("Soporte técnico y mesa de ayuda, {month}", 0.78),
            ("Mantenimiento preventivo de equipos", 0.22),
        ],
    ),
    "BEN-05": dict(
        forms={"es": "co_cobro", "en": "us_invoice"},
        num="CC-2026-{:02d}",
        start=40,
        terms=10,
        es=[("Ilustración: piezas gráficas para el módulo de {mod}", 1.0)],
        en=[("Illustration: graphic assets for the {mod} screens", 1.0)],
    ),
    "BEN-06": dict(
        forms={"es": "mx_cfdi"},
        num="A-{:04d}",
        start=1500,
        terms=20,
        es=[("Pruebas de software y aseguramiento de calidad, {month}", 1.0)],
    ),
    "BEN-07": dict(
        forms={"es": "mx_cfdi"},
        num="T-{:04d}",
        start=900,
        terms=15,
        es=[("Traducción y localización al inglés del módulo de {mod}", 1.0)],
    ),
    "BEN-08": dict(
        forms={"en": "br_nfse"},
        num="{:06d}",
        start=230,
        terms=30,
        en=[("Identidade visual e motion graphics / Brand identity and motion graphics", 1.0)],
    ),
    "BEN-09": dict(
        forms={"es": "ar_fe", "en": "us_invoice"},
        num="00003-{:08d}",
        start=140,
        terms=15,
        es=[("Desarrollo móvil: aplicación iOS y Android en Flutter, {month}", 1.0)],
        en=[("Mobile development: iOS and Android app in Flutter, {month}", 1.0)],
    ),
    "BEN-10": dict(
        forms={"en": "us_invoice"},
        num="CR-2026-{:04d}",
        start=1100,
        terms=30,
        en=[
            ("Cloud hosting: compute nodes, {month}", 0.66),
            ("Block storage", 0.2),
            ("Bandwidth", 0.14),
        ],
    ),
    "BEN-11": dict(
        forms={"en": "us_invoice"},
        num="QS-{:05d}",
        start=11000,
        terms=30,
        en=[("Documentation wiki subscription, Team plan, user seats", 1.0)],
    ),
    "BEN-12": dict(
        forms={"en": "us_invoice"},
        num="HLS-2026-{:03d}",
        start=110,
        terms=30,
        en=[
            ("24/7 security monitoring (security operations center), {month}", 0.75),
            ("Compliance evidence reporting", 0.25),
        ],
    ),
    "BEN-13": dict(
        forms={"es": "es_factura", "en": "us_invoice"},
        num="A-2026-{:03d}",
        start=300,
        terms=30,
        es=[
            ("Sprint de diseño con el equipo de producto", 0.6),
            ("Pruebas de usabilidad con usuarios", 0.4),
        ],
        en=[("Design sprint with the product team", 0.6), ("Usability testing sessions", 0.4)],
    ),
}

VENDORS = {b["id"]: b for b in yaml.safe_load((DATA / "vendors.yaml").read_text())["beneficiaries"]}

# New suppliers on no list entry (R01). Fictional, and like no listed name.
NEW = {
    "co": dict(
        form="co_cobro",
        num="001",
        currency="COP",
        amount=220000000,
        seller={
            "name": "Camila Restrepo Vélez",
            "tax_id": "DEMO-CC-1144556677",
            "lines": [
                "Calle Demo 70 # 12-08, Medellín, Antioquia",
                "camila.restrepo@correo.invalid",
            ],
            "account": "Banco Ficticio Andino · Ahorros DEMO-0012-6620-31",
            "country": "CO",
            "currency": "COP",
        },
        es=[("Redacción técnica de la documentación del API", 1.0)],
    ),
    "us": dict(
        form="us_invoice",
        num="JDM-1042",
        currency="USD",
        amount=86000,
        seller={
            "name": "Juniper Demo Metrics, LLC",
            "tax_id": "DEMO-91-2033418",
            "lines": [
                "77 Demo Market St., Suite 5, Denver, CO 80202",
                "ar@juniper-metrics.invalid",
            ],
            "account": "Demo Mountain Bank · ABA DEMO-1070 · Acct DEMO-5521-0042",
            "country": "US",
            "currency": "USD",
        },
        en=[("Customer survey design and analysis", 1.0)],
    ),
    "mx": dict(
        form="mx_cfdi",
        num="B-0077",
        currency="MXN",
        amount=1150000,
        seller={
            "name": "Servicios Creativos Demo del Norte S.A. de C.V.",
            "tax_id": "DEMO030303EF3",
            "lines": [
                "Av. Demo 300, Col. Ficticia, Monterrey, N.L., C.P. 64000",
                "cfdi@sc-norte.invalid",
            ],
            "account": "Banco Ficticio del Norte · CLABE DEMO 0000 0000 0000 31",
            "country": "MX",
            "currency": "MXN",
        },
        es=[("Edición de video para materiales de capacitación", 1.0)],
    ),
}


# --- Slots: one invoice before its language and channel are fixed --------------------


@dataclass
class Slot:
    ben: str | None
    trap: str | None
    period: tuple[date, date]
    issue: date
    received: datetime
    amount: int
    texts: dict[str, list[tuple[str, float]]]  # lines by language
    forms: dict[str, str]
    number: str
    over: dict = field(default_factory=dict)  # extra Spec fields
    lang: str = ""
    channel: str = ""
    lock: str = ""  # channel this slot must use


def month_es(d: date) -> str:
    return f"{MONTHS_ES.split()[d.month - 1]} de {d.year}"


def month_en(d: date) -> str:
    return f"{d.strftime('%B')} {d.year}"


class Episode:
    """Seeded by run, shard and episode index; builds the slots of one batch."""

    counters: dict[str, int] = {}

    def __init__(self, index: int):
        self.index = index
        self.rng = Random(f"{RUN}/{index % SHARDS}/{index}")
        self.mod = self.rng.randrange(len(MODS_ES))

    def number(self, ben: str) -> str:
        c = CAT[ben]
        n = Episode.counters.get(ben, c["start"])
        Episode.counters[ben] = n + 1
        return c["num"].format(n)

    def period(self, ben: str, kind: str = "") -> tuple[date, date]:
        freq = VENDORS[ben]["contract"]["frequency"]
        if freq == "monthly":
            return D(2026, 9, 1), D(2026, 9, 30)
        if freq == "biweekly":
            return self.rng.choice(
                [(D(2026, 9, 16), D(2026, 9, 30)), (D(2026, 10, 1), D(2026, 10, 15))]
            )
        end = D(2026, 9, 20) + timedelta(days=self.rng.randrange(0, 22))
        return end - timedelta(days=self.rng.randrange(4, 9)), end

    def received(self, issue: date, after: datetime | None = None) -> datetime:
        day = max(issue, D(2026, 10, 1)) + timedelta(days=self.rng.randrange(0, 4))
        if after:
            day = max(day, after.date() + timedelta(days=self.rng.randrange(1, 4)))
        day = min(day, D(2026, 10, 17))
        return datetime(
            day.year,
            day.month,
            day.day,
            self.rng.randrange(8, 17),
            self.rng.randrange(60),
            tzinfo=COT,
        )

    def amount(self, ben: str) -> int:
        rate = VENDORS[ben]["contract"]["rate_minor"]
        if ben == "BEN-10":
            return int(round(rate * self.rng.uniform(0.95, 1.05), -2))
        if ben == "BEN-07":
            return int(round(rate * self.rng.uniform(0.96, 1.04), -3))
        if ben == "BEN-13":
            return round(rate * self.rng.uniform(0.98, 1.02) / 500) * 500
        return rate

    def routine(self, ben: str, after: datetime | None = None, **kw) -> Slot:
        period = kw.pop("period", None) or self.period(ben)
        issue = kw.pop("issue", None) or min(
            period[1] + timedelta(days=self.rng.randrange(0, 2)), D(2026, 10, 16)
        )
        c = CAT[ben]
        fill = {"mod": MODS_ES[self.mod], "month": month_es(period[0])}
        fill_en = {"mod": MODS_EN[self.mod], "month": month_en(period[0])}
        texts = {
            lang: [(t.format(**(fill if lang == "es" else fill_en)), share) for t, share in c[lang]]
            for lang in ("es", "en")
            if lang in c
        }
        return Slot(
            ben=ben,
            trap=kw.pop("trap", None),
            period=period,
            issue=issue,
            received=kw.pop("received", None) or self.received(issue, after),
            amount=kw.pop("amount", None) or self.amount(ben),
            texts=kw.pop("texts", None) or texts,
            forms=kw.pop("forms", None) or dict(c["forms"]),
            number=kw.pop("number", None) or self.number(ben),
            lock=kw.pop("lock", ""),
            over=kw,
        )


def garble(words: str) -> str:
    """Replaces the first vowel of every word, as a broken font or encoding would."""
    return re.sub(
        r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+",
        lambda m: re.sub(r"[AEIOUaeiouÁÉÍÓÚáéíóú]", "?", m[0], count=1),
        words,
    )


# --- The 48 traps and their priors (PLAN section 8 mix) -----------------------------

Build = Callable[[Episode], list[Slot]]


def single(ben: str, trap: str, **kw) -> Build:
    return lambda e: [e.routine(ben, trap=trap, **kw)]


def resend(ben: str, trap: str, new_number: bool = False, fiscal: bool = False) -> Build:
    """A routine prior pays; then the same invoice, its fiscal ID or its amount returns."""

    def build(e: Episode) -> list[Slot]:
        p = e.routine(ben)
        over = dict(p.over)
        if fiscal:
            over["fiscal_seed"] = f"{VENDORS[ben]['tax_id']}:{p.number}"
        later = e.received(p.issue, p.received)
        number = e.number(ben) if new_number else p.number
        return [p, replace(p, trap=trap, received=later, number=number, over=over)]

    return build


def second(ben: str, trap: str, same_period: bool = False, prior_kw=None, **kw) -> Build:
    """A routine prior pays; then a second invoice from the same beneficiary arrives."""

    def build(e: Episode) -> list[Slot]:
        p = e.routine(ben, **(prior_kw or {}))
        extra = {"period": p.period, "issue": p.issue} if same_period else {}
        return [p, e.routine(ben, after=p.received, trap=trap, **extra, **kw)]

    return build


def budget(ben: str, **kw) -> Build:
    """Three operations invoices pay, leaving less than one more of the 2,200 USD budget."""

    def build(e: Episode) -> list[Slot]:
        a = e.routine("BEN-04")
        b = e.routine("BEN-07", after=a.received, amount=980000)
        c = e.routine("BEN-07", after=b.received, amount=950000)
        return [a, b, c, e.routine(ben, after=c.received, trap="insufficient_budget", **kw)]

    return build


def new_supplier(key: str) -> Build:
    def build(e: Episode) -> list[Slot]:
        n = NEW[key]
        period = (D(2026, 10, 1), D(2026, 10, 9))
        issue = D(2026, 10, 9)
        lang = "en" if key == "us" else "es"
        return [
            Slot(
                ben=None,
                trap="new_beneficiary",
                period=period,
                issue=issue,
                received=e.received(issue),
                amount=n["amount"],
                texts={lang: n[lang]},
                forms={lang: n["form"]},
                number=n["num"],
                over={"seller": n["seller"]},
            )
        ]

    return build


OCT = (D(2026, 10, 1), D(2026, 10, 31))
JUL = (D(2026, 7, 1), D(2026, 7, 31))
OTHER_BUYER = {"name": "Otra Empresa Demo LLC", "tax_id": "DEMO-77-1234567"}
EN_SCOPE = "Copywriting for onboarding emails and help articles"

TRAP_EPISODES: list[Build] = [
    *(resend(b, "duplicate_number") for b in ("BEN-05", "BEN-07", "BEN-13")),
    *(resend(b, "duplicate_fiscal_id", new_number=True, fiscal=True) for b in ("BEN-07", "BEN-06")),
    *(resend(b, "duplicate_same_amount_period", new_number=True) for b in ("BEN-13", "BEN-05")),
    *(new_supplier(k) for k in ("co", "us", "mx")),
    single(
        "BEN-11",
        "off_contract_amount",
        amount=56000,
        texts={
            "en": [
                ("Documentation wiki subscription, Team plan, user seats", 0.75),
                ("Premium analytics add-on for the wiki subscription", 0.25),
            ]
        },
    ),
    single("BEN-03", "off_contract_amount", amount=89000),
    single("BEN-10", "off_contract_amount", amount=142000),
    single(
        "BEN-13",
        "off_contract_scope",
        texts={
            "es": [("Desarrollo backend: migración de base de datos y API de exportación", 1.0)],
            "en": [("Backend development: database migration and export API", 1.0)],
        },
    ),
    single("BEN-10", "off_contract_scope", texts={"en": [(EN_SCOPE, 1.0)]}),
    single(
        "BEN-06",
        "off_contract_scope",
        texts={"es": [("Traducción al inglés de manuales de usuario", 1.0)]},
    ),
    single("BEN-12", "over_threshold"),
    single(
        "BEN-12",
        "over_threshold",
        amount=245000,
        period=(D(2026, 8, 1), D(2026, 8, 31)),
        issue=D(2026, 9, 30),
    ),
    single("BEN-08", "over_threshold"),
    budget("BEN-07", amount=1020000),
    budget("BEN-04", period=OCT, issue=D(2026, 10, 15)),
    budget("BEN-07", amount=1040000),
    single("BEN-09", "near_threshold", forms={"es": "ar_fe"}),
    single("BEN-09", "near_threshold", forms={"en": "us_invoice"}),
    single("BEN-11", "due_past_grace", period=JUL, issue=D(2026, 7, 31)),
    single(
        "BEN-02", "due_past_grace", period=(D(2026, 7, 1), D(2026, 7, 15)), issue=D(2026, 7, 15)
    ),
    single("BEN-10", "words_unparseable", garble=True),
    single("BEN-06", "words_unparseable", garble=True),
    single("BEN-07", "currency_mismatch", amount=53000, currency="USD"),
    single(
        "BEN-05", "currency_mismatch", amount=260000000, forms={"es": "co_cobro"}, currency="COP"
    ),
    single(
        "BEN-12",
        "over_cap",
        amount=1200000,
        texts={
            "en": [("24/7 security monitoring, five months prepaid (Sep 2026 to Jan 2027)", 1.0)]
        },
    ),
    single(
        "BEN-01",
        "over_cap",
        amount=2600000000,
        texts={
            "es": [
                ("Diseño de interfaz y sistema de diseño, cinco meses (sep. 2026 a ene. 2027)", 1.0)
            ]
        },
    ),
    second("BEN-11", "frequency_exceeded", same_period=True, amount=42800),
    second("BEN-02", "frequency_exceeded", same_period=True, amount=315000000),
    single(
        "BEN-05",
        "service_outside_validity",
        period=(D(2026, 3, 2), D(2026, 3, 27)),
        issue=D(2026, 10, 2),
    ),
    single(
        "BEN-03",
        "service_outside_validity",
        period=(D(2026, 2, 16), D(2026, 2, 28)),
        issue=D(2026, 10, 5),
    ),
    single("BEN-04", "low_quality_scan", lock="image", scan="low"),
    single("BEN-06", "low_quality_scan", lock="image", scan="low"),
    second(
        "BEN-13",
        "split_pair",
        prior_kw={"forms": {"es": "es_factura"}},
        forms={"es": "es_factura"},
        amount=115000,
    ),
    second(
        "BEN-13",
        "split_pair",
        prior_kw={"forms": {"en": "us_invoice"}},
        forms={"en": "us_invoice"},
        amount=118000,
    ),
    single("BEN-04", "words_differ", words_for=340000000),
    single("BEN-03", "words_differ", words_for=70000, forms={"es": "co_cobro"}),
    single("BEN-10", "other_buyer", buyer=OTHER_BUYER),
    single("BEN-01", "other_buyer", buyer=OTHER_BUYER),
    single("BEN-13", "proforma", kind="Factura proforma", forms={"es": "es_factura"}),
    single("BEN-11", "proforma", kind="Proforma invoice"),
    single("BEN-10", "future_issue_date", period=OCT, issue=D(2026, 10, 31)),
    single("BEN-06", "future_issue_date", period=OCT, issue=D(2026, 10, 24)),
]

# 52 routine episodes of one invoice each, across the beneficiaries that can pay alone.
ROUTINE = {"BEN-10": 8, "BEN-11": 8, "BEN-13": 6, "BEN-03": 5, "BEN-05": 5, "BEN-02": 5}
ROUTINE |= {"BEN-01": 4, "BEN-04": 3, "BEN-06": 4, "BEN-07": 4}


# --- Language and channel quotas ---------------------------------------------------

QUOTA = {"en": 48, "chat": 18, "image": 12, "email": 18}
FLIP_ORDER = ("BEN-13", "BEN-09", "BEN-05", "BEN-03")


def assign(slots: list[Slot], rng: Random) -> None:
    """Fixes each slot's language and channel so the set hits the planned mix exactly."""
    for s in slots:
        s.lang = "es" if "es" in s.forms else "en"
    # Chats are typed cuentas de cobro, so they take Spanish cobro slots first.
    cobro = [s for s in slots if s.forms.get("es") == "co_cobro" and not s.lock]
    rng.shuffle(cobro)
    for s in cobro[: QUOTA["chat"]]:
        s.lock = "chat"
    assert sum(s.lock == "chat" for s in slots) == QUOTA["chat"], "not enough cobro slots for chat"
    # English: flip flexible slots until 48.
    flexible = [s for s in slots if s.lang == "es" and "en" in s.forms and s.lock != "chat"]
    flexible.sort(key=lambda s: FLIP_ORDER.index(s.ben) if s.ben in FLIP_ORDER else 9)
    need = QUOTA["en"] - sum(s.lang == "en" for s in slots)
    assert 0 <= need <= len(flexible), f"English needs {need} of {len(flexible)} flexible slots"
    for s in flexible[:need]:
        s.lang = "en"
    # Images, then emails (any form but the cuenta de cobro), then PDF.
    free = [s for s in slots if not s.lock]
    rng.shuffle(free)
    images = QUOTA["image"] - sum(s.lock == "image" for s in slots)
    for s in free[:images]:
        s.lock = "image"
    mailable = [s for s in free[images:] if s.forms[s.lang] != "co_cobro"]
    for s in mailable[: QUOTA["email"]]:
        s.lock = "email"
    for s in slots:
        s.channel = s.lock or "pdf"


# --- Specs, documents and labels ---------------------------------------------------


def lines(s: Slot, form: str) -> list[Line]:
    texts = s.texts[s.lang]
    unit = {"co_cobro": "entrega"}.get(form, "servicio" if s.lang == "es" else "service")
    if s.ben == "BEN-11" and texts[0][1] == 1.0:
        return [Line(texts[0][0], "20", "seat", s.amount)]
    step = (
        100000
        if (s.over.get("currency") or VENDORS.get(s.ben, {}).get("currency")) == "COP"
        else 100
    )
    out, left = [], s.amount
    for i, (text, share) in enumerate(texts):
        part = left if i == len(texts) - 1 else round(s.amount * share / step) * step
        out.append(Line(text, "1", unit, part))
        left -= part
    return out


def spec(s: Slot, invoice_id: str) -> Spec:
    form = s.forms[s.lang]
    terms = CAT[s.ben]["terms"] if s.ben else 30
    over = dict(s.over)
    garbled, words_for = over.pop("garble", False), over.pop("words_for", None)
    sp = Spec(
        id=invoice_id,
        ben=s.ben,
        form=form,
        channel=s.channel,
        received=s.received,
        number=s.number,
        issue=s.issue,
        due=s.issue + timedelta(days=terms),
        period=s.period,
        trap=s.trap,
        lines=lines(s, form),
        concept=f"{s.texts[s.lang][0][0]}, {month_es(s.period[0])}." if form == "co_cobro" else "",
        **over,
    )
    if words_for:
        sp.words = amount_words_es(words_for, sp.currency or VENDORS[s.ben]["currency"])
    if garbled:
        _, ctx, _ = build(sp)
        sp.words = garble(ctx["words"])
    return sp


def label(sp: Spec, path: str, facts: dict) -> dict:
    t = TRAPS["traps"][sp.trap] if sp.trap else TRAPS["routine"]
    return {
        "invoice_id": sp.id,
        "split": "generated",
        "channel": sp.channel,
        "language": "en" if sp.form in {"us_invoice", "br_nfse"} else "es",
        "path": path,
        "received_at": sp.received.isoformat(),
        "trap": sp.trap,
        "gold_decision": t["decision"],
        "gold_rules": t["rules"],
        "gold_security": t["security"],
        "gold_facts": facts,
        "beneficiary_id": sp.ben,
    }


def episodes() -> list[list[Slot]]:
    builds: list[Build] = [*TRAP_EPISODES]
    for ben, n in ROUTINE.items():
        builds += [lambda e, b=ben: [e.routine(b)]] * n
    Random(f"{RUN}/order").shuffle(builds)
    return [build(Episode(i)) for i, build in enumerate(builds, 1)]


def main(argv: list[str]) -> None:
    eps = episodes()
    slots = [s for ep in eps for s in ep]
    assert len(slots) == 120 and sum(s.trap is None for s in slots) == 72, len(slots)
    assign(slots, Random(f"{RUN}/channels"))
    rows = []
    for i, ep in enumerate(eps, 1):
        for n, s in enumerate(ep, 1):
            sp = spec(s, f"GEN-{i:03d}-{n}")
            template, ctx, facts = build(sp)
            out = OUT / f"{sp.id}.{EXT[sp.channel]}"
            write_doc(sp, template, ctx, out)
            rows.append(label(sp, str(out.relative_to(DATA.parent)), facts))
    write_jsonl(DATA / "labels/generated.jsonl", rows)
    print(f"{len(rows)} documents in {OUT.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main(sys.argv[1:])
