"""Country forms: turn one invoice spec into a template context and its printed gold facts.

A spec (see month.py) names the beneficiary, the form, the number, dates and lines. Each
form decides the labels, tax wording, fiscal block and number formats its country prints.
Gold facts are the critical strings exactly as the form prints them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from common import (
    FICTIONAL_EN,
    FICTIONAL_ES,
    VERIFY,
    amount_words_en,
    amount_words_es,
    cae,
    cfdi_uuid,
    chave,
    company,
    cufe,
    digits,
    fdate,
    money,
    qr_svg,
    sello,
    vendors,
)

COMPANY = company()
# Seller tax-ID labels on the English invoice, by country.
TAX_LABEL_EN = {"US": "EIN", "CO": "C.C.", "AR": "CUIT", "ES": "NIF", "MX": "RFC", "BR": "CNPJ"}
VENDORS = vendors()

BUYER_LINES = ["500 Demo Avenue, Suite 210", "Wilmington, DE 19801, USA", "ap@ceiba-demo.invalid"]

# Fictional seller addresses and contacts by beneficiary.
SELLER_LINES = {
    "BEN-01": [
        "Calle Ficticia 12 # 34-56, Medellín, Antioquia",
        "facturacion@andes-diseno.invalid",
    ],
    "BEN-02": ["Carrera Demo 45 # 10-20, Bogotá D.C.", "mateo.quintero@correo.invalid"],
    "BEN-03": ["Avenida Ficticia 8 # 2-31, Cali, Valle", "valentina.ospina@correo.invalid"],
    "BEN-04": ["Vía Demo 77 # 50-12, Barranquilla, Atlántico", "cartera@caribe-soporte.invalid"],
    "BEN-05": ["Transversal Demo 3 # 9-14, Manizales, Caldas", "julian.herrera@correo.invalid"],
    "BEN-06": [
        "Av. Ficticia 1200, Col. Demo, Guadalajara, Jal., C.P. 44100",
        "cfdi@aztlan.invalid",
    ],
    "BEN-07": ["Calle Demo 45, Centro, León, Gto., C.P. 37000", "facturas@bajio-trad.invalid"],
    "BEN-08": ["Rua Fictícia, 321, Vila Demo, São Paulo - SP", "financeiro@ipe-criativa.invalid"],
    "BEN-09": ["Calle Ficticia 1450, Córdoba, Argentina", "tomas.ferreyra@correo.invalid"],
    "BEN-10": ["2200 Demo Parkway, Suite 400, Austin, TX 78701", "billing@cobaltridge.invalid"],
    "BEN-11": ["88 Fictional St., Floor 3, Portland, OR 97204", "ar@quillstack.invalid"],
    "BEN-12": ["410 Demo Harbor Blvd., Seattle, WA 98101", "invoices@harborlight.invalid"],
    "BEN-13": ["Calle Ficticia 23, 2.º, 46001 Valencia", "admin@estudio-albahaca.invalid"],
}


@dataclass
class Line:
    desc: str
    qty: str  # as printed: "1", "30", "0.5"
    unit: str  # UN/ECE Rec 20 label as printed: "servicio", "mes", "h", "seat"
    amount_minor: int  # line net


@dataclass
class Spec:
    id: str
    form: str  # co_factura, co_cobro, mx_cfdi, br_nfse, ar_fe, es_factura, us_invoice
    channel: str  # pdf, image, email, chat
    received: datetime  # aware
    number: str
    issue: date
    due: date
    lines: list[Line]
    ben: str | None = None  # listed beneficiary this document is (or claims to be)
    trap: str | None = None
    seller: dict | None = None  # overrides: name, tax_id, lines, account (new or fake sellers)
    currency: str | None = None  # defaults to the beneficiary's
    period: tuple[date, date] | None = None
    concept: str = ""
    words: str | None = None  # override the amount in words (R15 traps)
    fiscal_seed: str | None = None  # reuse another document's fiscal ID (R03 traps)
    buyer: dict | None = None
    stamps: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)
    print_account: bool = True
    account: str | None = None  # an account printed instead of the one on file (R12)
    message: str = ""  # email intro or first chat message
    kind: str | None = None  # document title override, e.g. a proforma (R16)
    scan: str = "normal"  # image channel: "normal" phone scan or "low" quality (R10)
    subject: str = ""  # email subject


def _seller(s: Spec) -> dict:
    base = VENDORS[s.ben] if s.ben else {}
    over = s.seller or {}
    return {
        "name": over.get("name", base.get("name")),
        "tax_id": over.get("tax_id", base.get("tax_id")),
        "lines": over.get("lines", SELLER_LINES.get(s.ben or "", [])),
        "account": s.account or over.get("account", base.get("account_on_file")),
        "country": over.get("country", base.get("country")),
        "currency": over.get("currency", base.get("currency")),
    }


def _buyer(s: Spec, tax_label: str) -> dict:
    b = s.buyer or {}
    return {
        "name": b.get("name", COMPANY["name"]),
        "tax_label": tax_label,
        "tax_id": b.get("tax_id", COMPANY["tax_id"]),
        "lines": b.get("lines", BUYER_LINES),
    }


def _created(s: Spec) -> str:
    return datetime(s.issue.year, s.issue.month, s.issue.day, 12, 0).isoformat() + "-05:00"


def _period(s: Spec, style: str, sep: str) -> str:
    if not s.period:
        return ""
    return f"{fdate(s.period[0], style)}{sep}{fdate(s.period[1], style)}"


def build(s: Spec) -> tuple[str, dict, dict]:
    """Returns (template, context, gold_facts)."""
    return FORMS[s.form](s)


def _common(s: Spec, seller: dict, lang: str) -> dict:
    return {
        "lang": lang,
        "created": _created(s),
        "seller": seller,
        "stamps": s.stamps,
        "marker": FICTIONAL_ES if lang == "es" else FICTIONAL_EN,
        "buyer_marker": FICTIONAL_ES if lang == "es" else FICTIONAL_EN,
        "footer": "Documento ficticio de demostración · Alinka"
        if lang == "es"
        else "Fictitious demo document · Alinka",
        "footer_note": "Todos los nombres, identificadores y cuentas son ficticios."
        if lang == "es"
        else "All names, identifiers and accounts are fictitious.",
        "notes": list(s.notes),
    }


def _facts(s, seller, tax_id, number, currency, total, due, **extra) -> dict:
    facts = {
        "beneficiary_name": seller["name"],
        "beneficiary_tax_id": tax_id,
        "invoice_number": number,
        "currency": currency,
        "total": total,
        "due_date": due,
    }
    facts.update({k: v for k, v in extra.items() if v is not None})
    return facts


# --- Colombia -------------------------------------------------------------------


def co_factura(s: Spec) -> tuple[str, dict, dict]:
    """Factura electrónica de venta: NIT, CUFE, QR, authorization line, IVA 19% included."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "es-CO"
    total = sum(li.amount_minor for li in s.lines)
    # Lines carry the agreed gross; the form splits out IVA 19% rounded to the peso.
    nets = [round(li.amount_minor / 1.19 / 100) * 100 for li in s.lines]
    net = round(total / 1.19 / 100) * 100
    nets[-1] += net - sum(nets)
    tax = total - net
    code = cufe(s.fiscal_seed or f"{seller['tax_id']}:{s.number}")
    ctx = _common(s, {**seller, "tax_label": "NIT"}, "es")
    seller_lines = [*seller["lines"], "Responsable de IVA · Régimen ordinario"]
    ctx.update(
        title=f"Factura electrónica de venta {s.number}",
        accent="#0b5d63",
        seller={**ctx["seller"], "lines": seller_lines},
        doc_label=s.kind or "Factura electrónica de venta",
        number_label="N.º",
        number=s.number,
        head_kv=[
            ("Fecha de emisión", fdate(s.issue, "dmy")),
            ("Fecha de vencimiento", fdate(s.due, "dmy")),
            ("Moneda", cur),
            ("Forma de pago", "Crédito 30 días"),
        ],
        buyer_label="Adquiriente",
        buyer=_buyer(s, "Tax ID (EIN)"),
        info_label="Período facturado",
        info_kv=[("Período", _period(s, "dmy", " al "))] if s.period else [],
        line_heads=["#", "Descripción", "Cant.", "Unidad", "Vr. unitario", "Vr. total"],
        lines=[
            [
                str(i),
                li.desc,
                li.qty,
                li.unit,
                money(n, loc),
                money(n, loc),
            ]
            for i, (li, n) in enumerate(zip(s.lines, nets, strict=True), 1)
        ],
        totals=[("Subtotal", money(net, loc)), ("IVA 19%", money(tax, loc))],
        total_label=f"Total a pagar ({cur})",
        total_display=f"$ {money(total, loc)}",
        words_label="Valor en letras",
        words=s.words or amount_words_es(total, cur),
        tax_note=None,
        qr=qr_svg(f"{VERIFY}/fe?cufe={code[:32]}"),
        fiscal_kv=[
            ("CUFE", code),
            (
                "Autorización",
                f"Resolución de facturación DEMO-{digits(seller['tax_id'], 8)} (ficticia) "
                f"del 01/01/2026, rango {s.number.rsplit('-', 1)[0]}-0001 a 5000",
            ),
            ("Cuenta para pago", seller["account"] if s.print_account else "—"),
        ],
    )
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=fdate(s.issue, "dmy"),
        subtotal=money(net, loc),
        tax_total=money(tax, loc),
        fiscal_id=code,
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "factura.html.j2", ctx, facts


def co_cobro(s: Spec) -> tuple[str, dict, dict]:
    """Cuenta de cobro from a persona natural, with the no-IVA declaration."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "es-CO"
    total = sum(li.amount_minor for li in s.lines)
    sym = "USD $" if cur == "USD" else "$"
    city = seller["lines"][0].split(", ")[1] if seller["lines"] else "Bogotá D.C."
    ctx = _common(s, {**seller, "tax_label": "C.C."}, "es")
    ctx.update(
        title=f"Cuenta de cobro {s.number}",
        accent="#333333",
        city_date=f"{city}, {fdate(s.issue, 'long_es')}",
        number=s.number,
        buyer=_buyer(s, "EIN"),
        total_display=f"{sym} {money(total, loc)} {cur}",
        words=s.words or amount_words_es(total, cur),
        concept=s.concept,
        line_heads=["#", "Descripción", "Cant.", "Valor"],
        lines=[
            [str(i), li.desc, f"{li.qty} {li.unit}", money(li.amount_minor, loc)]
            for i, li in enumerate(s.lines, 1)
        ],
        head_kv=[
            ("Período", _period(s, "dmy", " al ")),
            ("Fecha de emisión", fdate(s.issue, "dmy")),
            ("Fecha límite de pago", fdate(s.due, "dmy")),
            ("Moneda", cur),
            ("Consignar a", seller["account"] if s.print_account else "—"),
        ],
    )
    ctx["head_kv"] = [kv for kv in ctx["head_kv"] if kv[1]]
    ctx["notes"] = [
        "Declaro que no soy responsable de IVA, que no estoy obligado a expedir factura "
        "electrónica y que los ingresos aquí cobrados provienen de la prestación de servicios "
        "personales.",
        *ctx["notes"],
    ]
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=fdate(s.issue, "dmy"),
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "cuenta_cobro.html.j2", ctx, facts


# --- Mexico ---------------------------------------------------------------------


def mx_cfdi(s: Spec) -> tuple[str, dict, dict]:
    """Printed CFDI 4.0: RFC, folio fiscal UUID, régimen, uso G03, export with IVA 0%."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "es-MX"
    total = sum(li.amount_minor for li in s.lines)
    uid = cfdi_uuid(s.fiscal_seed or f"{seller['tax_id']}:{s.number}")
    stamp_at = f"{s.issue.isoformat()}T{s.received.strftime('%H:%M')}:12"
    ctx = _common(s, {**seller, "tax_label": "RFC"}, "es")
    ctx.update(
        title=f"CFDI {s.number}",
        accent="#7a1f3d",
        seller={
            **ctx["seller"],
            "lines": [*seller["lines"], "Régimen fiscal: 601 General de Ley Personas Morales"],
        },
        doc_label="Factura · CFDI 4.0 (representación impresa)",
        number_label="Serie y folio",
        number=s.number,
        head_kv=[
            ("Fecha de emisión", stamp_at),
            ("Tipo de comprobante", "I - Ingreso"),
            ("Exportación", "02 - Definitiva"),
            ("Moneda", cur),
            ("Fecha límite de pago", fdate(s.due, "dmy")),
        ],
        buyer_label="Receptor",
        buyer=_buyer(s, "Núm. reg. id. trib."),
        info_label="Datos del comprobante",
        info_kv=[
            ("RFC receptor", "XEXX010101000 (residente en el extranjero)"),
            ("Uso CFDI", "G03 - Gastos en general"),
            ("Forma de pago", "03 - Transferencia electrónica"),
            ("Método de pago", "PUE - Pago en una sola exhibición"),
            *([("Periodo", _period(s, "dmy", " al "))] if s.period else []),
        ],
        line_heads=["Clave", "Descripción", "Cant.", "Unidad", "Valor unitario", "Importe"],
        lines=[
            [
                "81111500",
                li.desc,
                li.qty,
                li.unit,
                money(li.amount_minor, loc),
                money(li.amount_minor, loc),
            ]
            for li in s.lines
        ],
        totals=[
            ("Subtotal", money(total, loc)),
            ("IVA trasladado 0% (exportación)", money(0, loc)),
        ],
        total_label=f"Total ({cur})",
        total_display=f"$ {money(total, loc)}",
        words_label="Importe con letra",
        words=s.words or amount_words_es(total, cur),
        tax_note="Servicio exportado: IVA a tasa 0%.",
        qr=qr_svg(f"{VERIFY}/cfdi?id={uid}&tt={total / 100:.2f}"),
        fiscal_kv=[
            ("Folio fiscal (UUID)", uid),
            ("Fecha de certificación", stamp_at),
            ("No. de serie del CSD", f"DEMO{digits(seller['tax_id'], 16)}"),
            ("Sello digital del CFDI", sello(f"cfdi:{uid}")),
            ("Sello del certificador (ficticio)", sello(f"pac:{uid}", 96)),
            ("Cuenta para pago", seller["account"] if s.print_account else "—"),
        ],
    )
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=stamp_at,
        subtotal=money(total, loc),
        tax_total=money(0, loc),
        fiscal_id=uid,
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "factura.html.j2", ctx, facts


# --- United States --------------------------------------------------------------


def us_invoice(s: Spec) -> tuple[str, dict, dict]:
    """US vendor invoice: EIN, Net 30, remit-to details, no VAT."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "en-US"
    total = sum(li.amount_minor for li in s.lines)
    ctx = _common(s, {**seller, "tax_label": TAX_LABEL_EN.get(seller["country"], "EIN")}, "en")
    ctx.update(
        title=f"Invoice {s.number}",
        accent="#1f4e8c",
        doc_label=s.kind or "Invoice",
        number_label="Invoice #",
        number=s.number,
        head_kv=[
            ("Invoice date", fdate(s.issue, "long_en")),
            ("Due date", fdate(s.due, "long_en")),
            ("Terms", "Net 30"),
            ("Currency", cur),
            *([("Service period", _period(s, "long_en", " – "))] if s.period else []),
        ],
        buyer=_buyer(s, "EIN"),
        info_kv=[
            ("Payee", seller["name"]),
            ("Account", seller["account"] if s.print_account else "On file"),
            ("Reference", s.number),
        ],
        line_heads=["Item", "Description", "Qty", "Unit", "Rate", "Amount"],
        lines=[
            [
                str(i),
                li.desc,
                li.qty,
                li.unit,
                money(round(li.amount_minor / float(li.qty)), loc),
                money(li.amount_minor, loc),
            ]
            for i, li in enumerate(s.lines, 1)
        ],
        totals=[("Subtotal", money(total, loc)), ("Sales tax", "0.00")],
        total_label=f"Balance due ({cur})",
        total_display=f"${money(total, loc)}",
        words_label="Amount in words",
        words=s.words or amount_words_en(total, cur),
        tax_note="Services delivered to a business customer; no sales tax applies."
        if seller["country"] == "US"
        else "Export of services to a US business customer; no VAT or sales tax charged.",
        qr=None,
        fiscal_kv=[],
    )
    ctx["notes"] = [
        f"Please reference invoice {s.number} with your payment. Questions: {seller['lines'][-1]}",
        *ctx["notes"],
    ]
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "long_en"),
        issue_date=fdate(s.issue, "long_en"),
        subtotal=money(total, loc),
        tax_total="0.00",
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "invoice_us.html.j2", ctx, facts


# --- Brazil -----------------------------------------------------------------------


def br_nfse(s: Spec) -> tuple[str, dict, dict]:
    """NFS-e for an exported service: CNPJ, 44-digit chave de acesso, ISS not levied."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "pt-BR"
    total = sum(li.amount_minor for li in s.lines)
    key = chave(s.fiscal_seed or f"{seller['tax_id']}:{s.number}")
    ctx = _common(s, {**seller, "tax_label": "CNPJ"}, "en")
    ctx.update(
        title=f"NFS-e {s.number}",
        accent="#2d6a2e",
        seller={**ctx["seller"], "lines": [*seller["lines"], "Inscrição municipal DEMO-0441"]},
        doc_label="NFS-e · Nota Fiscal de Serviço Eletrônica · Service invoice (fictícia)",
        number_label="Número / Number",
        number=s.number,
        head_kv=[
            ("Emissão / Issue date", fdate(s.issue, "dmy")),
            ("Vencimento / Due date", fdate(s.due, "dmy")),
            ("Moeda / Currency", cur),
            ("Competência / Period", _period(s, "dmy", " a ")),
        ],
        buyer_label="Tomador do serviço / Customer (exterior)",
        buyer=_buyer(s, "Tax ID (EIN)"),
        info_label="Serviço / Service",
        info_kv=[
            ("Código do serviço", "DEMO 23.01 · Design e comunicação visual"),
            ("País do resultado", "Estados Unidos"),
        ],
        line_heads=["#", "Discriminação / Description", "Qtd.", "Unid.", "Valor unit.", "Valor"],
        lines=[
            [
                str(i),
                li.desc,
                li.qty,
                li.unit,
                money(round(li.amount_minor / float(li.qty)), loc),
                money(li.amount_minor, loc),
            ]
            for i, li in enumerate(s.lines, 1)
        ],
        totals=[
            ("Valor dos serviços / Services", money(total, loc)),
            ("ISS / Service tax (0%)", money(0, loc)),
        ],
        total_label=f"Valor líquido / Net amount ({cur})",
        total_display=f"R$ {money(total, loc)}",
        words_label="Amount in words",
        words=s.words or amount_words_en(total, cur),
        tax_note="Não incidência de ISS: exportação de serviços. "
        "ISS not levied: services exported to a customer abroad.",
        qr=qr_svg(f"{VERIFY}/nfse?chave={key}"),
        fiscal_kv=[
            ("Chave de acesso", key),
            ("Código de verificação", digits(f"verif:{key}", 8)),
            ("Dados bancários / Bank", seller["account"] if s.print_account else "—"),
        ],
    )
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=fdate(s.issue, "dmy"),
        subtotal=money(total, loc),
        tax_total=money(0, loc),
        fiscal_id=key,
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "factura.html.j2", ctx, facts


# --- Argentina ----------------------------------------------------------------------


def ar_fe(s: Spec) -> tuple[str, dict, dict]:
    """Factura E (export of services): CUIT, punto de venta, 14-digit CAE and its expiry."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "es-AR"
    total = sum(li.amount_minor for li in s.lines)
    code = cae(s.fiscal_seed or f"{seller['tax_id']}:{s.number}")
    ctx = _common(s, {**seller, "tax_label": "CUIT"}, "es")
    ctx.update(
        title=f"Factura E {s.number}",
        accent="#2b4c7e",
        seller={**ctx["seller"], "lines": [*seller["lines"], "Responsable Monotributo"]},
        doc_label="Factura E · Cód. 19 (exportación de servicios)",
        number_label="Comp. N.º",
        number=s.number,
        head_kv=[
            ("Fecha de emisión", fdate(s.issue, "dmy")),
            ("Vencimiento del pago", fdate(s.due, "dmy")),
            ("Moneda", f"{cur} (dólar estadounidense)"),
            ("Período facturado", _period(s, "dmy", " al ")),
        ],
        buyer_label="Cliente del exterior",
        buyer=_buyer(s, "ID impositivo (EIN)"),
        info_label="Operación",
        info_kv=[
            ("País de destino", "Estados Unidos"),
            ("Condición de venta", "Transferencia bancaria"),
            ("Concepto", "Servicios"),
        ],
        line_heads=["#", "Descripción", "Cant.", "Unidad", "Precio unit.", "Subtotal"],
        lines=[
            [
                str(i),
                li.desc,
                li.qty,
                li.unit,
                money(round(li.amount_minor / float(li.qty)), loc),
                money(li.amount_minor, loc),
            ]
            for i, li in enumerate(s.lines, 1)
        ],
        totals=[("Subtotal", money(total, loc)), ("IVA", "No gravado (exportación)")],
        total_label=f"Importe total ({cur})",
        total_display=f"U$S {money(total, loc)}",
        words_label="Importe en letras",
        words=s.words or amount_words_es(total, cur),
        tax_note="Exportación de servicios: operación no gravada con IVA.",
        qr=qr_svg(f"{VERIFY}/fe-ar?cae={code}"),
        fiscal_kv=[
            ("CAE N.º", code),
            ("Fecha de vto. de CAE", fdate(s.issue + timedelta(days=10), "dmy")),
            ("Cuenta para pago", seller["account"] if s.print_account else "—"),
        ],
    )
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=fdate(s.issue, "dmy"),
        subtotal=money(total, loc),
        fiscal_id=code,
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "factura.html.j2", ctx, facts


# --- Spain --------------------------------------------------------------------------


def es_factura(s: Spec) -> tuple[str, dict, dict]:
    """Spanish factura to a US client: NIF, art. 69 LIVA wording, IBAN, VERI*FACTU-style QR."""
    seller = _seller(s)
    cur = s.currency or seller["currency"]
    loc = "es-ES"
    total = sum(li.amount_minor for li in s.lines)
    ctx = _common(s, {**seller, "tax_label": "NIF"}, "es")
    ctx.update(
        title=f"Factura {s.number}",
        accent="#5b3a8c",
        doc_label=s.kind or "Factura",
        number_label="N.º",
        number=s.number,
        head_kv=[
            ("Fecha de expedición", fdate(s.issue, "dmy")),
            ("Fecha de vencimiento", fdate(s.due, "dmy")),
            ("Moneda", cur),
            ("Forma de pago", "Transferencia a 30 días"),
        ],
        buyer_label="Destinatario",
        buyer=_buyer(s, "Tax ID (EIN)"),
        info_label="Servicio",
        info_kv=[("Fecha de la operación", _period(s, "dmy", " al "))] if s.period else [],
        line_heads=["#", "Concepto", "Cant.", "Unidad", "Precio", "Base imponible"],
        lines=[
            [
                str(i),
                li.desc,
                li.qty,
                li.unit,
                money(round(li.amount_minor / float(li.qty)), loc),
                money(li.amount_minor, loc),
            ]
            for i, li in enumerate(s.lines, 1)
        ],
        totals=[("Base imponible", money(total, loc)), ("IVA (no sujeto)", money(0, loc))],
        total_label=f"Total factura ({cur})",
        total_display=f"{money(total, loc)} {'€' if cur == 'EUR' else cur}",
        words_label="Importe en letra",
        words=s.words or amount_words_es(total, cur),
        tax_note="Operación no sujeta a IVA (art. 69 LIVA): servicio prestado a un empresario "
        "establecido en Estados Unidos.",
        qr=qr_svg(
            f"{VERIFY}/verifactu?nif={seller['tax_id']}&num={s.number}"
            f"&fecha={fdate(s.issue, 'dmy')}&importe={total / 100:.2f}"
        ),
        fiscal_kv=[
            ("QR tributario", "VERI*FACTU (ficticio): factura verificable en la sede demo"),
            ("Huella del registro", sello(f"verifactu:{seller['tax_id']}:{s.number}", 64)),
            ("Pago por transferencia", seller["account"] if s.print_account else "—"),
        ],
    )
    facts = _facts(
        s,
        seller,
        seller["tax_id"],
        s.number,
        cur,
        money(total, loc),
        fdate(s.due, "dmy"),
        issue_date=fdate(s.issue, "dmy"),
        subtotal=money(total, loc),
        tax_total=money(0, loc),
        amount_in_words=ctx["words"],
        bank_account=seller["account"] if s.print_account else None,
    )
    return "factura.html.j2", ctx, facts


FORMS = {
    "co_factura": co_factura,
    "co_cobro": co_cobro,
    "mx_cfdi": mx_cfdi,
    "us_invoice": us_invoice,
    "br_nfse": br_nfse,
    "ar_fe": ar_fe,
    "es_factura": es_factura,
}
