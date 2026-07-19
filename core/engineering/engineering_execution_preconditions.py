from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, stable_record, validate_preparation_artifact


SCHEMA = "zero.engineering.execution_preconditions.v1"
ID_KEY = "execution_preconditions_id"
PREFIX = "engineering-execution-preconditions-"
FIELDS = {"execution_preparation_intake_id", "execution_eligibility_id", "preconditions", "unmet_preconditions", "precondition_outcome"}


def build_engineering_execution_preconditions(
    intake: Mapping[str, Any], eligibility: Mapping[str, Any], intent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supplied = dict(intent or {})
    raw = sorted(set(supplied.get("preconditions", intake.get("constraints", []))))
    met = set(supplied.get("met_preconditions", raw))
    items = [
        stable_record(
            {"description": item, "status": "met" if item in met else "unmet"},
            "execution_precondition_id",
            "engineering-execution-precondition-",
        )
        for item in raw
    ]
    unmet = [item["execution_precondition_id"] for item in items if item["status"] == "unmet"]
    outcome = "satisfied" if eligibility.get("status") == "eligible" and not unmet else "not_satisfied"
    payload = {
        "execution_preparation_intake_id": intake.get("execution_preparation_intake_id"),
        "execution_eligibility_id": eligibility.get("execution_eligibility_id"),
        "preconditions": items,
        "unmet_preconditions": unmet,
        "precondition_outcome": outcome,
    }
    return preparation_artifact(SCHEMA, outcome, payload, ID_KEY, PREFIX)


def validate_engineering_execution_preconditions(value: Any) -> ValidationResult:
    return validate_preparation_artifact(value, schema=SCHEMA, statuses={"satisfied", "not_satisfied", "blocked", "invalid"}, id_key=ID_KEY, prefix=PREFIX, fields=FIELDS)


__all__ = ["build_engineering_execution_preconditions", "validate_engineering_execution_preconditions"]
