"""The email and chat channels: the same invoice a form prints, sent as a message.

An email carries the invoice in its plain-text and HTML parts; a chat is a WhatsApp-style
transcript where the sender types out a cuenta de cobro. Both print the form's strings
unchanged, so the gold facts a form returns hold for every channel.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from common import ENV, write_chat, write_eml

PAYER_AP = "ap@ceiba-demo.invalid"
PAYER_CHAT = "Cuentas por pagar · Ceiba Demo"


def _sender(ctx: dict) -> str:
    seller = ctx["seller"]
    mail = next((x for x in seller["lines"] if "@" in x), "facturas@proveedor.invalid")
    return f'"{seller["name"]}" <{mail}>'


def email(out: Path, spec, ctx: dict) -> None:
    """A multipart email whose two parts print the same invoice."""
    es = ctx["lang"] == "es"
    subject = spec.subject or (
        f"{ctx['doc_label']} {ctx['number']} · {ctx['seller']['name']}"
        if es
        else f"Invoice {ctx['number']} from {ctx['seller']['name']}"
    )
    intro = spec.message or (
        "Buen día. Adjuntamos en este correo los datos del comprobante."
        if es
        else "Hello, please find your invoice details below."
    )
    view = {**ctx, "intro": intro}
    write_eml(
        out,
        sender=_sender(ctx),
        to=f'"{ctx["buyer"]["name"]}" <{PAYER_AP}>',
        subject=subject,
        sent=spec.received - timedelta(minutes=3),
        text=ENV.get_template("email.txt").render(**view),
        html=ENV.get_template("email.html.j2").render(**view),
        msg_id=f"{spec.id}.{ctx['number']}",
    )


def chat(out: Path, spec, ctx: dict) -> None:
    """A cuenta de cobro typed out in a WhatsApp chat, then acknowledged by the payer."""
    who = ctx["seller"]["name"]
    t = spec.received - timedelta(minutes=2)
    lines = [
        (t, who, spec.message or "Hola, buenos días. Les comparto mi cuenta de cobro."),
        (
            t,
            who,
            f"CUENTA DE COBRO N.º {ctx['number']} | {ctx['buyer']['name']} {ctx['buyer_marker']}, "
            f"{ctx['buyer']['tax_label']} {ctx['buyer']['tax_id']} | DEBE A: {who} "
            f"{ctx['marker']}, {ctx['seller']['tax_label']} {ctx['seller']['tax_id']}",
        ),
        (t, who, f"LA SUMA DE: {ctx['total_display']} | {ctx['words']}"),
        (t + timedelta(minutes=1), who, f"Por concepto de: {ctx['concept']}"),
        (
            t + timedelta(minutes=1),
            who,
            " | ".join(f"{k}: {v}" for k, v in ctx["head_kv"]),
        ),
        (t + timedelta(minutes=1), who, ctx["notes"][0]),
        (spec.received + timedelta(minutes=9), PAYER_CHAT, "Recibido, gracias. Queda en revisión."),
    ]
    write_chat(out, lines)
