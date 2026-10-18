"""Spanish reasons. Every sentence names its rule in words and cites the values it used.

Order: security alerts first, then the decision with its determining rule, then every other
rule that fired. `headline` is the first sentence, for cards.
"""

from __future__ import annotations

from alinka.audit.templates import render
from alinka.rules import norm_text
from alinka.types import (
    DECISION_ES,
    RECHECK_ON_APPROVAL,
    RULE_NAMES_ES,
    Decision,
    DecisionRecord,
    HumanAction,
    Outcome,
    RuleId,
    RuleResult,
)

# Words that already name the rule in a sentence; otherwise its name is put in front.
NAME_STEMS: dict[str, tuple[str, ...]] = {
    "R01": ("beneficiario", "suplantacion"), "R02": ("moneda y pais",), "R03": ("duplicad", "cobro doble"),
    "R04": ("pactado",), "R05": ("tope por pago",), "R06": ("umbral de aprobacion",),
    "R07": ("tope mensual",), "R08": ("saldo", "presupuesto"), "R09": ("fecha de pago",),
    "R10": ("lectura", "error tecnico"), "R11": ("contenido oculto",), "R12": ("cuenta bancaria",),
    "R13": ("fraccionamiento",), "R14": ("frecuencia",), "R15": ("monto en letras",),
    "R16": ("documento pagable", "documento no pagable"),
}  # fmt: skip


def names_rule(r: RuleResult, text: str) -> bool:
    plain = norm_text(text)
    return any(stem in plain for stem in NAME_STEMS[r.rule])


def sentence(r: RuleResult) -> str:
    """'2.350,00 USD supera el umbral de aprobación de 2.000 USD (R06)'."""
    text = render(r)
    if not names_rule(r, text):
        text = f"{RULE_NAMES_ES[r.rule].lower()}: {text}"
    return f"{text} ({r.rule})"


def alert_es(r: RuleResult) -> str:
    return f"Alerta de seguridad ({r.rule}): {sentence(r).removesuffix(f' ({r.rule})')}."


def reason_parts(
    decision: Decision,
    determining: RuleId | None,
    results: tuple[RuleResult, ...],
    human: HumanAction | None = None,
) -> list[str]:
    label = DECISION_ES[decision]
    by_rule = {r.rule: r for r in results}
    fired = [r for r in results if r.outcome != Outcome.PASS]
    parts = [alert_es(r) for r in fired if r.security]
    if human is not None and human.action == "reject":
        main = by_rule.get(determining) if determining else None
        why = f"; estaba pendiente por {sentence(main)}" if main else ""
        return [f"{label}: rechazada por {human.approver}{why}.", *parts]
    if decision == Decision.PAY:
        if human is not None:
            checks = "; ".join(sentence(by_rule[r]) for r in RECHECK_ON_APPROVAL if r in by_rule)
            return [
                *parts,
                f"{label}: aprobada por {human.approver}. Verificado de nuevo: {checks}.",
            ]
        cited = "; ".join(sentence(by_rule[r]) for r in ("R05", "R06") if r in by_rule)
        return [f"{label}: cumple las 16 reglas; {cited}."]
    main = by_rule.get(determining) if determining else None
    if main is None:
        parts.append(f"{label}: requiere revisión.")
    elif main.security:
        name = RULE_NAMES_ES[main.rule].lower()
        parts.append(f"{label} por la alerta de seguridad de {name} ({main.rule}).")
    else:
        parts.append(f"{label}: {sentence(main)}.")
    rest = [r for r in fired if r is not main and not r.security]
    if rest:
        parts.append("También: " + "; ".join(sentence(r) for r in rest) + ".")
    return parts


def reason_es(
    decision: Decision,
    determining: RuleId | None,
    results: tuple[RuleResult, ...],
    human: HumanAction | None = None,
) -> str:
    return " ".join(reason_parts(decision, determining, results, human))


def headline(record: DecisionRecord) -> str:
    """The card's one line: the first sentence, cut by structure rather than at a period."""
    return reason_parts(record.decision, record.determining_rule, record.results, record.human)[0]
