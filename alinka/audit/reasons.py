"""Spanish reasons. Every reason names its rule in words and the values it used."""

from __future__ import annotations

from alinka.types import DECISION_ES, RULE_NAMES_ES, Decision, Outcome, RuleId, RuleResult


def reason_es(
    decision: Decision,
    determining: RuleId | None,
    results: tuple[RuleResult, ...],
    approver: str | None = None,
) -> str:
    label = DECISION_ES[decision]
    if decision == Decision.PAY:
        if approver:
            return f"{label}: aprobada por {approver}; R03, R05, R07 y R08 verificadas de nuevo."
        return f"{label}: cumple las 16 reglas."
    fired = [r for r in results if r.outcome != Outcome.PASS]
    parts = [f"{RULE_NAMES_ES[r.rule].lower()} ({r.rule})" for r in fired]
    return f"{label}: " + "; ".join(parts) + "."
