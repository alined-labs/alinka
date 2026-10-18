"""A typical October: the 30 showcase invoices and their gold labels (PLAN section 8).

Run: uv run python data/generator/month.py [--force] [OCT-01 ...]
Existing documents are kept unless --force, so their hashes (and recorded model
responses) stay stable. Labels come from traps.yaml, never from the engine.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

import yaml
from channels import chat, email
from common import DATA, HERE, write_image, write_jsonl, write_pdf
from forms import Line, Spec, build

COT = timezone(timedelta(hours=-5))
TRAPS = yaml.safe_load((HERE / "traps.yaml").read_text())
OUT = DATA / "showcase"
EXT = {"pdf": "pdf", "image": "jpg", "email": "eml", "chat": "txt"}
LANG = {"en": {"us_invoice"}, "es": set()}


def at(day: int, hh: int, mm: int) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=COT)


D = date

SPECS: list[Spec] = [
    # --- The first five: routine PDFs across four printed forms ------------------------
    Spec(
        id="OCT-01",
        ben="BEN-10",
        form="us_invoice",
        channel="pdf",
        received=at(1, 9, 10),
        number="CR-2026-0930",
        issue=D(2026, 9, 30),
        due=D(2026, 10, 30),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        lines=[
            Line("Cloud hosting – compute (4 vCPU nodes), September 2026", "1", "month", 78000),
            Line("Block storage, 2 TB", "2", "TB", 24000),
            Line("Bandwidth overage", "1", "lot", 16000),
        ],
    ),
    Spec(
        id="OCT-02",
        ben="BEN-03",
        form="co_cobro",
        channel="pdf",
        received=at(1, 10, 25),
        number="2026-019",
        issue=D(2026, 9, 30),
        due=D(2026, 10, 15),
        period=(D(2026, 9, 16), D(2026, 9, 30)),
        concept="Servicios de desarrollo frontend: componentes de la interfaz web y accesibilidad, "
        "segunda quincena de septiembre de 2026.",
        lines=[Line("Desarrollo frontend, segunda quincena de septiembre", "1", "quincena", 72000)],
    ),
    Spec(
        id="OCT-03",
        ben="BEN-02",
        form="co_cobro",
        channel="pdf",
        received=at(1, 15, 40),
        number="041",
        issue=D(2026, 9, 30),
        due=D(2026, 10, 10),
        period=(D(2026, 9, 16), D(2026, 9, 30)),
        concept="Desarrollo backend: API de pagos e integraciones, segunda quincena de "
        "septiembre de 2026.",
        lines=[Line("Desarrollo backend (API e integraciones)", "1", "quincena", 310000000)],
    ),
    Spec(
        id="OCT-04",
        ben="BEN-01",
        form="co_factura",
        channel="pdf",
        received=at(2, 11, 5),
        number="DEMO-FAC-0042",
        issue=D(2026, 10, 1),
        due=D(2026, 10, 31),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        lines=[
            Line("Diseño de interfaz: 14 pantallas del flujo de pagos", "1", "servicio", 390000000),
            Line("Actualización del sistema de diseño (componentes)", "1", "servicio", 130000000),
        ],
    ),
    Spec(
        id="OCT-05",
        ben="BEN-06",
        form="mx_cfdi",
        channel="pdf",
        received=at(2, 16, 30),
        number="A-1187",
        issue=D(2026, 10, 2),
        due=D(2026, 10, 31),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        lines=[
            Line(
                "Pruebas de software y aseguramiento de calidad, septiembre 2026",
                "1",
                "E48 servicio",
                2600000,
            )
        ],
    ),
    # --- The rest of October, in received order (decided in this order) ----------------
    # Operations has 2,200 USD: OCT-06, -07 and -17 fit, so OCT-24 and OCT-25 cannot.
    Spec(
        id="OCT-06",
        ben="BEN-04",
        form="co_factura",
        channel="image",
        received=at(3, 9, 20),
        number="CST-0318",
        issue=D(2026, 10, 1),
        due=D(2026, 10, 31),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        lines=[
            Line("Soporte técnico y mesa de ayuda, septiembre 2026", "1", "mes", 280000000),
            Line("Mantenimiento preventivo de equipos (12 equipos)", "1", "servicio", 80000000),
        ],
    ),
    Spec(
        id="OCT-07",
        ben="BEN-07",
        form="mx_cfdi",
        channel="pdf",
        received=at(5, 10, 5),
        number="T-0562",
        issue=D(2026, 10, 3),
        due=D(2026, 10, 18),
        period=(D(2026, 9, 21), D(2026, 10, 2)),
        lines=[
            Line(
                "Traducción y localización al inglés de la guía de usuario (18,400 palabras)",
                "1",
                "E48 servicio",
                980000,
            )
        ],
    ),
    Spec(
        id="OCT-08",
        ben="BEN-11",
        form="us_invoice",
        channel="pdf",
        received=at(5, 14, 30),
        number="QS-10293",
        issue=D(2026, 9, 30),
        due=D(2026, 10, 30),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        trap="words_unparseable",
        words="F?ur h?ndr?d tw?nty and ??/100 US D?llars",
        lines=[Line("Documentation wiki subscription, Team plan, user seats", "20", "seat", 42000)],
    ),
    Spec(
        id="OCT-09",
        ben="BEN-12",
        form="us_invoice",
        channel="email",
        received=at(6, 8, 45),
        number="HLS-2026-09",
        issue=D(2026, 9, 30),
        due=D(2026, 10, 30),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        trap="over_threshold",
        lines=[
            Line("24/7 security monitoring (security operations center)", "1", "month", 180000),
            Line("Compliance evidence reporting", "1", "month", 60000),
        ],
    ),
    Spec(
        id="OCT-10",
        ben="BEN-05",
        form="co_cobro",
        channel="pdf",
        received=at(6, 11, 10),
        number="CC-2026-14",
        issue=D(2026, 10, 3),
        due=D(2026, 10, 13),
        period=(D(2026, 9, 22), D(2026, 10, 2)),
        concept="Ilustración de 6 piezas gráficas para la página de inicio, entrega del "
        "2 de octubre de 2026.",
        lines=[Line("Ilustración: 6 piezas gráficas", "1", "entrega", 65000)],
    ),
    Spec(
        id="OCT-11",
        form="co_cobro",
        channel="chat",
        received=at(7, 16, 20),
        number="001",
        issue=D(2026, 10, 7),
        due=D(2026, 10, 17),
        period=(D(2026, 10, 1), D(2026, 10, 7)),
        trap="new_beneficiary",
        seller={
            "name": "Laura Cifuentes Rojas",
            "tax_id": "DEMO-CC-1098765432",
            "lines": ["Calle Demo 19 # 4-07, Pereira, Risaralda", "laura.cifuentes@correo.invalid"],
            "account": "Banco Ficticio Andino · Ahorros DEMO-0012-9904-77",
            "country": "CO",
            "currency": "COP",
        },
        message="Buenas tardes, soy Laura Cifuentes. El equipo de producto me pidió enviarles "
        "por aquí mi cuenta de cobro por los artículos del centro de ayuda.",
        concept="Redacción de 8 artículos para el centro de ayuda, octubre de 2026.",
        lines=[Line("Redacción de artículos del centro de ayuda", "8", "artículo", 240000000)],
    ),
    Spec(
        id="OCT-12",
        ben="BEN-07",
        form="mx_cfdi",
        channel="pdf",
        received=at(7, 17, 45),
        number="T-0571",
        issue=D(2026, 10, 7),
        due=D(2026, 10, 22),
        period=(D(2026, 9, 21), D(2026, 10, 2)),
        trap="duplicate_fiscal_id",
        fiscal_seed="DEMO020202CD2:T-0562",  # OCT-07's folio fiscal under a new folio
        lines=[
            Line(
                "Traducción y localización al inglés de la guía de usuario (18,400 palabras)",
                "1",
                "E48 servicio",
                980000,
            )
        ],
    ),
    Spec(
        id="OCT-13",
        ben="BEN-13",
        form="es_factura",
        channel="pdf",
        received=at(8, 9, 0),
        number="A-2026-087",
        issue=D(2026, 10, 6),
        due=D(2026, 11, 5),
        period=(D(2026, 9, 28), D(2026, 10, 3)),
        lines=[
            Line("Sprint de diseño de 5 días con el equipo de producto", "5", "día", 80000),
            Line("Pruebas de usabilidad moderadas, 5 participantes", "5", "sesión", 40000),
        ],
    ),
    Spec(
        id="OCT-14",
        ben="BEN-08",
        form="br_nfse",
        channel="pdf",
        received=at(8, 13, 15),
        number="000214",
        issue=D(2026, 10, 1),
        due=D(2026, 10, 31),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        trap="over_threshold",
        lines=[
            Line(
                "Identidade visual e motion graphics, campanha de setembro / "
                "Brand identity and motion graphics, September visual campaign",
                "1",
                "mês",
                1350000,
            )
        ],
    ),
    Spec(
        id="OCT-15",
        ben="BEN-02",
        form="co_cobro",
        channel="image",
        received=at(9, 10, 40),
        number="036",
        issue=D(2026, 7, 31),
        due=D(2026, 8, 15),
        period=(D(2026, 7, 16), D(2026, 7, 31)),
        trap="due_past_grace",
        concept="Desarrollo backend: integraciones del API de facturación, segunda quincena de "
        "julio de 2026.",
        lines=[Line("Desarrollo backend (API e integraciones)", "1", "quincena", 310000000)],
    ),
    Spec(
        id="OCT-16",
        ben="BEN-09",
        form="ar_fe",
        channel="pdf",
        received=at(9, 15, 0),
        number="00003-00000127",
        issue=D(2026, 10, 1),
        due=D(2026, 10, 16),
        period=(D(2026, 9, 1), D(2026, 9, 30)),
        trap="near_threshold",
        lines=[
            Line(
                "Desarrollo móvil: aplicación iOS y Android en Flutter, septiembre 2026",
                "1",
                "mes",
                195000,
            )
        ],
    ),
    Spec(
        id="OCT-17",
        ben="BEN-07",
        form="mx_cfdi",
        channel="email",
        received=at(10, 9, 30),
        number="T-0580",
        issue=D(2026, 10, 9),
        due=D(2026, 10, 24),
        period=(D(2026, 10, 3), D(2026, 10, 9)),
        message="Buen día. Les compartimos los datos del CFDI por el subtitulado de los videos "
        "de capacitación.",
        lines=[
            Line("Subtitulado al español de 4 videos de capacitación", "1", "E48 servicio", 950000)
        ],
    ),
    Spec(
        id="OCT-18",
        ben="BEN-06",
        form="mx_cfdi",
        channel="email",
        received=at(12, 10, 0),
        number="A-1201",
        issue=D(2026, 10, 10),
        due=D(2026, 10, 31),
        period=(D(2026, 10, 1), D(2026, 10, 31)),
        lines=[
            Line(
                "Pruebas de software y aseguramiento de calidad, octubre 2026",
                "1",
                "E48 servicio",
                2600000,
            )
        ],
    ),
    Spec(
        id="OCT-19",
        form="us_invoice",
        channel="email",
        received=at(12, 11, 20),
        number="TGA-00417",
        issue=D(2026, 10, 9),
        due=D(2026, 11, 8),
        trap="new_beneficiary",
        seller={
            "name": "Tallgrass Demo Analytics, LLC",
            "tax_id": "DEMO-83-5521907",
            "lines": [
                "1800 Demo Prairie Rd., Suite 12, Omaha, NE 68102",
                "billing@tallgrass-analytics.invalid",
            ],
            "account": "Demo Plains Bank · ABA DEMO-1040 · Acct DEMO-3317-0099",
            "country": "US",
            "currency": "USD",
        },
        message="Hi team, thanks for the kickoff call! Here is our first invoice for the "
        "analytics setup.",
        lines=[
            Line("Product analytics dashboard setup", "1", "project", 60000),
            Line("Event tracking plan and QA", "1", "project", 18000),
        ],
    ),
    Spec(
        id="OCT-20",
        ben="BEN-05",
        form="co_cobro",
        channel="chat",
        received=at(13, 8, 50),
        number="CC-2026-14",
        issue=D(2026, 10, 3),
        due=D(2026, 10, 13),
        period=(D(2026, 9, 22), D(2026, 10, 2)),
        trap="duplicate_number",
        message="Hola, buenos días. Les reenvío la cuenta de cobro CC-2026-14 por si no les llegó.",
        concept="Ilustración de 6 piezas gráficas para la página de inicio, entrega del "
        "2 de octubre de 2026.",
        lines=[Line("Ilustración: 6 piezas gráficas", "1", "entrega", 65000)],
    ),
    Spec(
        id="OCT-21",
        ben="BEN-01",
        form="co_factura",
        channel="pdf",
        received=at(13, 14, 10),
        number="DEMO-FAC-0047",
        issue=D(2026, 10, 13),
        due=D(2026, 11, 12),
        period=(D(2026, 10, 1), D(2026, 10, 31)),
        trap="off_contract_amount",
        lines=[
            Line(
                "Diseño de interfaz: 18 pantallas del módulo de reportes",
                "1",
                "servicio",
                450000000,
            ),
            Line("Prototipos interactivos y sistema de diseño", "1", "servicio", 170000000),
        ],
    ),
    Spec(
        id="OCT-22",
        ben="BEN-13",
        form="es_factura",
        channel="pdf",
        received=at(14, 9, 25),
        number="A-2026-091",
        issue=D(2026, 10, 13),
        due=D(2026, 11, 12),
        period=(D(2026, 10, 5), D(2026, 10, 9)),
        trap="off_contract_scope",
        lines=[
            Line(
                "Desarrollo backend: migración de base de datos y API de exportación",
                "1",
                "proyecto",
                120000,
            )
        ],
    ),
    Spec(
        id="OCT-23",
        ben="BEN-11",
        form="us_invoice",
        channel="email",
        received=at(14, 16, 40),
        number="QS-10377",
        issue=D(2026, 10, 14),
        due=D(2026, 11, 13),
        period=(D(2026, 10, 1), D(2026, 10, 31)),
        lines=[Line("Documentation wiki subscription, Team plan, user seats", "20", "seat", 42000)],
    ),
    Spec(
        id="OCT-24",
        ben="BEN-07",
        form="mx_cfdi",
        channel="pdf",
        received=at(15, 10, 10),
        number="T-0588",
        issue=D(2026, 10, 14),
        due=D(2026, 10, 29),
        period=(D(2026, 10, 10), D(2026, 10, 14)),
        trap="insufficient_budget",
        lines=[
            Line(
                "Localización al portugués de la aplicación móvil (2,150 cadenas)",
                "1",
                "E48 servicio",
                1020000,
            )
        ],
    ),
    Spec(
        id="OCT-25",
        ben="BEN-04",
        form="co_factura",
        channel="pdf",
        received=at(15, 11, 30),
        number="CST-0331",
        issue=D(2026, 10, 15),
        due=D(2026, 11, 14),
        period=(D(2026, 10, 1), D(2026, 10, 31)),
        trap="insufficient_budget",
        lines=[
            Line("Soporte técnico y mesa de ayuda, octubre 2026", "1", "mes", 280000000),
            Line("Mantenimiento de redes y equipos", "1", "servicio", 80000000),
        ],
    ),
    Spec(
        id="OCT-26",
        ben="BEN-03",
        form="co_cobro",
        channel="chat",
        received=at(16, 9, 5),
        number="2026-020",
        issue=D(2026, 10, 15),
        due=D(2026, 10, 30),
        period=(D(2026, 10, 1), D(2026, 10, 15)),
        message="¡Hola! Les comparto la cuenta de cobro de la primera quincena de octubre.",
        concept="Servicios de desarrollo frontend: componentes React del tablero y mejoras de "
        "accesibilidad, primera quincena de octubre de 2026.",
        lines=[Line("Desarrollo frontend, primera quincena de octubre", "1", "quincena", 72000)],
    ),
    Spec(
        id="OCT-27",
        ben="BEN-02",
        form="co_cobro",
        channel="image",
        received=at(16, 10, 50),
        number="042",
        issue=D(2026, 10, 15),
        due=D(2026, 10, 25),
        period=(D(2026, 10, 1), D(2026, 10, 15)),
        concept="Desarrollo backend: API de pagos y base de datos de conciliación, primera "
        "quincena de octubre de 2026.",
        lines=[Line("Desarrollo backend (API y base de datos)", "1", "quincena", 310000000)],
    ),
    Spec(
        id="OCT-28",
        ben="BEN-05",
        form="co_cobro",
        channel="chat",
        received=at(16, 15, 15),
        number="CC-2026-15",
        issue=D(2026, 10, 15),
        due=D(2026, 10, 25),
        period=(D(2026, 10, 5), D(2026, 10, 15)),
        message="Hola, les envío la cuenta de cobro de la segunda entrega de octubre.",
        concept="Iconografía: set de 24 íconos para la aplicación móvil, entrega del "
        "15 de octubre de 2026.",
        lines=[Line("Iconografía: 24 íconos", "1", "entrega", 65000)],
    ),
    Spec(
        id="OCT-29",
        ben="BEN-13",
        form="es_factura",
        channel="image",
        received=at(17, 9, 40),
        number="A-2026-094",
        issue=D(2026, 10, 15),
        due=D(2026, 11, 14),
        period=(D(2026, 10, 12), D(2026, 10, 15)),
        lines=[Line("Entrevistas con usuarios e informe de hallazgos", "8", "sesión", 118000)],
    ),
    Spec(
        id="OCT-30",
        ben="BEN-13",
        form="es_factura",
        channel="email",
        received=at(17, 11, 0),
        number="A-2026-095",
        issue=D(2026, 10, 16),
        due=D(2026, 11, 15),
        period=(D(2026, 10, 13), D(2026, 10, 16)),
        currency="USD",
        trap="currency_mismatch",
        message="Buenos días. Os enviamos la factura de las pruebas de usabilidad remotas.",
        lines=[Line("Pruebas de usabilidad remotas, 5 participantes", "5", "sesión", 130000)],
    ),
]


def language(s: Spec) -> str:
    return "en" if s.form in {"us_invoice", "br_nfse"} else "es"


def label(s: Spec, path: str, facts: dict) -> dict:
    t = TRAPS["traps"][s.trap] if s.trap else TRAPS["routine"]
    return {
        "invoice_id": s.id,
        "split": "showcase",
        "channel": s.channel,
        "language": language(s),
        "path": path,
        "received_at": s.received.isoformat(),
        "trap": s.trap,
        "gold_decision": t["decision"],
        "gold_rules": t["rules"],
        "gold_security": t["security"],
        "gold_facts": facts,
        "beneficiary_id": s.ben,
    }


def render(s: Spec, force: bool) -> dict:
    template, ctx, facts = build(s)
    out = OUT / f"{s.id}.{EXT[s.channel]}"
    if force or not out.exists():
        if s.channel == "pdf":
            write_pdf(template, ctx, out)
        elif s.channel == "image":
            tmp = OUT / f".{s.id}.pdf"
            write_pdf(template, ctx, tmp)
            write_image(tmp, out, seed=s.id)
            tmp.unlink()
        elif s.channel == "email":
            email(out, s, ctx)
        else:
            chat(out, s, ctx)
    return label(s, str(out.relative_to(DATA.parent)), facts)


def main(argv: list[str]) -> None:
    force = "--force" in argv
    only = {a for a in argv if a.startswith("OCT-")}
    rows = [render(s, force) for s in SPECS if not only or s.id in only]
    if not only:
        write_jsonl(DATA / "labels/showcase.jsonl", rows)
    print(f"{len(rows)} documents in {OUT.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main(sys.argv[1:])
