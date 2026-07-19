from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, stable_record, validate_preparation_artifact


SCHEMA = "zero.engineering.execution_environment_requirements.v1"
ID_KEY = "execution_environment_requirements_id"
PREFIX = "engineering-execution-environment-requirements-"
FIELDS = {"execution_preconditions_id", "requirements", "unresolved_requirements", "environment_outcome"}


def build_engineering_execution_environment_requirements(
    preconditions: Mapping[str, Any], intent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supplied = dict(intent or {})
    raw = sorted(set(supplied.get("environment_requirements", [])))
    available = set(supplied.get("available_environment_requirements", raw))
    items = [
        stable_record(
            {"description": item, "status": "available" if item in available else "unavailable"},
            "execution_environment_requirement_id",
            "engineering-execution-environment-requirement-",
        )
        for item in raw
    ]
    unresolved = [item["execution_environment_requirement_id"] for item in items if item["status"] == "unavailable"]
    outcome = "satisfied" if preconditions.get("status") == "satisfied" and not unresolved else "not_satisfied"
    return preparation_artifact(
        SCHEMA,
        outcome,
        {
            "execution_preconditions_id": preconditions.get("execution_preconditions_id"),
            "requirements": items,
            "unresolved_requirements": unresolved,
            "environment_outcome": outcome,
        },
        ID_KEY,
        PREFIX,
    )


def validate_engineering_execution_environment_requirements(value: Any) -> ValidationResult:
    return validate_preparation_artifact(value, schema=SCHEMA, statuses={"satisfied", "not_satisfied", "blocked", "invalid"}, id_key=ID_KEY, prefix=PREFIX, fields=FIELDS)


__all__ = ["build_engineering_execution_environment_requirements", "validate_engineering_execution_environment_requirements"]
