from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, validate_preparation_artifact


SCHEMA = "zero.engineering.execution_eligibility.v1"
ID_KEY = "execution_eligibility_id"
PREFIX = "engineering-execution-eligibility-"
FIELDS = {"execution_preparation_intake_id", "checks", "blocking_conditions", "evidence_gaps", "eligibility"}


def build_engineering_execution_eligibility(
    intake: Mapping[str, Any], intent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supplied = dict(intent or {})
    gaps = sorted(set(supplied.get("evidence_gaps", [])))
    blocks = sorted(set(supplied.get("eligibility_blocks", [])))
    declarations = intake.get("authority_declarations", {})
    checks = {
        "intake_accepted": intake.get("status") == "accepted",
        "approval_granted": declarations.get("approval_authority") == "granted",
        "authorization_granted": declarations.get("authorization_authority") == "granted",
        "execution_not_granted": declarations.get("execution_authority") == "not_granted",
        "mutation_not_granted": declarations.get("mutation_authority") == "not_granted",
        "evidence_sufficient": not gaps,
    }
    eligible = all(checks.values()) and not blocks
    outcome = "eligible" if eligible else ("insufficient_evidence" if gaps else "not_eligible")
    payload = {
        "execution_preparation_intake_id": intake.get("execution_preparation_intake_id"),
        "checks": checks,
        "blocking_conditions": blocks,
        "evidence_gaps": gaps,
        "eligibility": outcome,
    }
    return preparation_artifact(SCHEMA, outcome, payload, ID_KEY, PREFIX)


def validate_engineering_execution_eligibility(value: Any) -> ValidationResult:
    return validate_preparation_artifact(
        value,
        schema=SCHEMA,
        statuses={"eligible", "not_eligible", "blocked", "invalid", "insufficient_evidence"},
        id_key=ID_KEY,
        prefix=PREFIX,
        fields=FIELDS,
    )


__all__ = ["build_engineering_execution_eligibility", "validate_engineering_execution_eligibility"]
