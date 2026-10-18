"""Spanish reasons. Security alerts first, then the determining rule, then the rest fired."""

from __future__ import annotations

from alinka.audit.templates import render
from alinka.types import DECISION_ES, RULE_NAMES_ES, Decision, Outcome, RuleId, RuleResult


def alert_es(r: RuleResult) -> str:
    return f"Alerta de seguridad ({r.rule}): {render(r)}."


def reason_es(
    decision: Decision,
    determining: RuleId | None,
    results: tuple[RuleResult, ...],
    approver: str | None = None,
) -> str:
    label = DECISION_ES[decision]
    fired = [r for r in results if r.outcome != Outcome.PASS]
    alerts = [alert_es(r) for r in fired if r.security]
    if decision == Decision.PAY:
        if approver:
            return " ".join(
                [*alerts, f"{label}: aprobada por {approver}; tope por pago, tope mensual, "
                 "saldo y duplicados verificados de nuevo (R03, R05, R07, R08)."]
            )  # fmt: skip
        return f"{label}: cumple las 16 reglas."
    main = next((r for r in fired if r.rule == determining), None)
    parts = list(alerts)
    if main is not None and not main.security:
        parts.append(f"{label}: {render(main)} ({main.rule}).")
    else:
        name = RULE_NAMES_ES[determining].lower() if determining else "requiere revisión"
        parts.append(f"{label}: {name} ({determining}).")
    rest = [r for r in fired if r is not main and not r.security]
    if rest:
        also = "; ".join(f"{RULE_NAMES_ES[r.rule].lower()} ({r.rule})" for r in rest)
        parts.append(f"También: {also}.")
    return " ".join(parts)
