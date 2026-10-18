"""A typical October: the 30 showcase invoices and their gold labels (PLAN section 8).

Run: uv run python data/generator/month.py [--force] [OCT-01 ...]
Existing documents are kept unless --force, so their hashes (and recorded model
responses) stay stable. Labels come from traps.yaml, never from the engine.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

import yaml
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
        else:
            raise NotImplementedError(s.channel)
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
