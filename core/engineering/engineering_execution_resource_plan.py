from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, stable_record, validate_preparation_artifact


SCHEMA = "zero.engineering.execution_resource_plan.v1"
ID_KEY = "execution_resource_plan_id"
PREFIX = "engineering-execution-resource-plan-"
FIELDS = {"execution_environment_requirements_id", "resource_requirements", "unavailable_resources", "resource_outcome"}


def build_engineering_execution_resource_plan(
    environment: Mapping[str, Any], intent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supplied = dict(intent or {})
    raw = sorted(set(supplied.get("resource_requirements", [])))
    available = set(supplied.get("available_resources", raw))
    items = [
        stable_record(
            {"description": item, "status": "available" if item in available else "unavailable"},
            "execution_resource_requirement_id",
            "engineering-execution-resource-requirement-",
        )
        for item in raw
    ]
    unavailable = [item["execution_resource_requirement_id"] for item in items if item["status"] == "unavailable"]
    outcome = "satisfied" if environment.get("status") == "satisfied" and not unavailable else "not_satisfied"
    return preparation_artifact(
        SCHEMA,
        outcome,
        {
            "execution_environment_requirements_id": environment.get("execution_environment_requirements_id"),
            "resource_requirements": items,
            "unavailable_resources": unavailable,
            "resource_outcome": outcome,
        },
        ID_KEY,
        PREFIX,
    )


def validate_engineering_execution_resource_plan(value: Any) -> ValidationResult:
    return validate_preparation_artifact(value, schema=SCHEMA, statuses={"satisfied", "not_satisfied", "blocked", "invalid"}, id_key=ID_KEY, prefix=PREFIX, fields=FIELDS)


__all__ = ["build_engineering_execution_resource_plan", "validate_engineering_execution_resource_plan"]
