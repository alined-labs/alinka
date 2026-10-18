"""One Spanish sentence per message_key, citing the values the rule used."""

from __future__ import annotations

import re
from datetime import date

from alinka.types import RULE_NAMES_ES, RuleResult, Scalar

MONTHS = (
    "ene.",
    "feb.",
    "mar.",
    "abr.",
    "may.",
    "jun.",
    "jul.",
    "ago.",
    "sept.",
    "oct.",
    "nov.",
    "dic.",
)
STATUS_ES = {
    "paid": "ya se pagó",
    "approved": "ya se aprobó",
    "pending": "ya está pendiente de aprobación",
}

TEMPLATES: dict[str, str] = {
    "R01.ok": "beneficiario autorizado: {name}",
    "R01.not_listed": "beneficiario no autorizado: {name} ({tax_id}) no está en la lista",
    "R01.lookalike": "posible suplantación: {name} ({tax_id}) se parece en un {similarity_pct} a {listed_name} ({listed_tax_id}), que está en la lista",
    "R01.tax_id_other_name": "posible suplantación: la identificación {tax_id} es de {listed_name}, pero el documento dice {name}",
    "R01.mixed_scripts": "posible suplantación: el nombre {name} mezcla alfabetos ({scripts})",
    "R02.ok": "moneda {currency} según el perfil del beneficiario",
    "R02.not_applicable": "moneda {currency}; sin beneficiario de la lista para comparar",
    "R02.currency_mismatch": "la moneda {currency} no es la del perfil de {beneficiary} ({expected}, {country})",
    "R02.currency_unknown": "no se pudo leer la moneda ({printed})",
    "R02.no_fx": "no hay tasa oficial de {currency} de los últimos {max_age_days} días",
    "R03.ok": "sin duplicados",
    "R03.duplicate_number": "factura duplicada: {invoice_number} de {beneficiary} {status_es} el {earlier_date} por {earlier_amount} ({earlier_invoice})",
    "R03.duplicate_fiscal_id": "factura duplicada: su identificador fiscal ya aparece en {earlier_invoice}, que {status_es} el {earlier_date} por {earlier_amount}",
    "R03.duplicate_document": "factura duplicada: el mismo documento ya llegó como {earlier_invoice} y {status_es} el {earlier_date}",
    "R03.duplicate_amount_period": "posible cobro doble: {beneficiary} ya cobró {earlier_amount} en el mismo periodo ({earlier_invoice}, {earlier_date})",
    "R04.ok": "{amount} dentro de lo pactado ({rate}, contrato {contract})",
    "R04.not_applicable": "sin contrato que comparar",
    "R04.amount_unknown": "no se pudo leer el monto para compararlo con lo pactado",
    "R04.over_rate": "no coincide con lo pactado: {amount} supera la tarifa de {rate} más {tolerance_pct}% de tolerancia (contrato {contract})",
    "R04.off_scope": "no coincide con lo pactado: «{service}» no corresponde al alcance del contrato {contract} ({scope})",
    "R04.scope_unreadable": "no se pudo leer el servicio cobrado para compararlo con el contrato {contract}",
    "R05.ok": "{usd} dentro del tope por pago de {cap}",
    "R05.amount_unknown": "no se pudo calcular el monto en USD para el tope por pago",
    "R05.over_cap": "{usd} supera el tope por pago de {cap}; el agente nunca supera un tope",
    "R06.ok": "{usd} bajo el umbral de aprobación de {threshold}",
    "R06.amount_unknown": "no se pudo calcular el monto en USD para el umbral de aprobación",
    "R06.over_threshold": "{usd} supera el umbral de aprobación de {threshold}",
    "R06.near_threshold": "{usd} queda a menos de {band_pct}% del umbral de aprobación de {threshold}",
    "R07.ok": "tope mensual: {spent} gastados más {usd} no superan {cap}",
    "R07.amount_unknown": "no se pudo calcular el monto en USD para el tope mensual",
    "R07.over_monthly_cap": "tope mensual: {spent} ya aprobados este mes más {usd} superan {cap}",
    "R08.ok": "saldo y presupuesto alcanzan para {usd}",
    "R08.amount_unknown": "no se pudo calcular el monto en USD para el saldo y el presupuesto",
    "R08.balance": "saldo insuficiente: quedan {balance} y la factura es de {usd}",
    "R08.budget": "presupuesto insuficiente: a {cost_center} le quedan {budget_left} de {budget} en octubre y la factura es de {usd}",
    "R09.ok": "fecha de pago {due_date} dentro del plazo",
    "R09.due_unparseable": "no se pudo leer la fecha de pago ({printed})",
    "R09.past_grace": "fecha de pago vencida: {due_date} es {days_past} días antes del {as_of} (máximo {grace_days})",
    "R10.ok": "lectura confiable (riesgo {risk})",
    "R10.extraction_error": "error técnico al leer el documento: {error}",
    "R10.missing": "lectura no confiable: faltan campos críticos ({fields})",
    "R10.low_confidence": "lectura no confiable: campos sin evidencia o con baja confianza ({fields})",
    "R10.disagreement": "lectura no confiable: las dos lecturas no coinciden en {fields}",
    "R10.totals": "lectura no confiable: los totales no cuadran con el documento",
    "R10.risk": "lectura no confiable: riesgo del verificador {risk}, máximo {risk_max}",
    "R11.ok": "sin contenido oculto",
    "R11.hidden_content": "texto oculto{page_es}: {detail}",
    "R11.unicode_controls": "caracteres de control Unicode escondidos en el texto: {detail}",
    "R11.html_text_mismatch": "el HTML del correo muestra algo distinto a su texto plano",
    "R11.instructions": "el documento contiene instrucciones dirigidas a un sistema: {detail}",
    "R11.reader_instructions": "el lector reportó instrucciones dirigidas a un sistema: {detail}",
    "R12.ok": "sin cuentas bancarias distintas a la de la lista",
    "R12.not_applicable": "sin cuenta bancaria que comparar",
    "R12.account_differs": "cuenta bancaria distinta a la registrada para {beneficiary}: el documento pide pagar a «{printed}»; se pagaría solo a la cuenta de la lista",
    "R13.ok": "fraccionamiento: {window_total} en {window_days} días, bajo {threshold}",
    "R13.amount_unknown": "no se pudo calcular el monto en USD para revisar fraccionamiento",
    "R13.single": "fraccionamiento: {usd} en una sola factura supera {threshold}",
    "R13.split": "posible fraccionamiento: con {other_invoices} suma {window_total} en {window_days} días, más de {threshold}",
    "R14.ok": "frecuencia del contrato respetada ({period})",
    "R14.not_applicable": "sin contrato para revisar la frecuencia",
    "R14.frequency": "frecuencia: ya hay una factura del periodo {period} ({earlier_invoice}) y el contrato {contract} es {frequency_es}",
    "R14.outside_validity": "el servicio ({period_start} a {period_end}) está fuera de la vigencia del contrato {contract} ({valid_from} a {valid_to})",
    "R15.ok": "monto en letras igual a {digits}",
    "R15.not_printed": "sin monto en letras",
    "R15.unparseable": "no se pudo interpretar el monto en letras «{words}»",
    "R15.differs": "el monto en letras ({words_amount}) no coincide con el monto en números ({digits})",
    "R16.ok": "documento pagable: {doc_type} a nombre de {buyer}",
    "R16.doc_type": "documento no pagable: es «{doc_type}», no una factura ni una cuenta de cobro",
    "R16.stamp": "documento no pagable: tiene el sello {stamp}",
    "R16.buyer": "documento no pagable: está a nombre de {buyer}, no de {payer}",
    "R16.non_positive": "documento no pagable: el total es {total}",
    "R16.future_issue": "documento no pagable: emitido el {issue_date}, después del {as_of}",
    "R16.unreadable": "no se pudo confirmar el tipo de documento ni el comprador",
}
FREQUENCY_ES = {
    "monthly": "mensual",
    "biweekly": "quincenal",
    "weekly": "semanal",
    "per_delivery": "por entrega",
}


def fecha(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


class _Values(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "—"


def _text(v: Scalar) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return fecha(v)
    return str(v)


def render(r: RuleResult) -> str:
    """The sentence for one result; unknown keys fall back to the rule's name in words."""
    values = _Values({k: _text(v) for k, v in r.values.items()})
    if isinstance(sim := r.values.get("similarity"), float):
        values["similarity_pct"] = f"{round(sim * 100)}%"
    if (status := r.values.get("earlier_status")) in STATUS_ES:
        values["status_es"] = STATUS_ES[str(status)]
    if (freq := r.values.get("frequency")) in FREQUENCY_ES:
        values["frequency_es"] = FREQUENCY_ES[str(freq)]
    page = re.match(r"\s*p(?:age|ágina)?\s*(\d+)", str(r.values.get("detail", "")), re.I)
    values["page_es"] = f" en la página {page.group(1)}" if page else ""
    template = TEMPLATES.get(r.message_key)
    if template is None:
        error = f": {values['error']}" if "error" in r.values else ""
        return f"{RULE_NAMES_ES[r.rule].lower()} no se pudo verificar{error}"
    return template.format_map(values)
