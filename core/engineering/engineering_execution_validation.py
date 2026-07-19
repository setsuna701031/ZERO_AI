from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, validate_preparation_artifact
from core.engineering.engineering_execution_preparation_intake import validate_engineering_execution_preparation_intake


SCHEMA = "zero.engineering.execution_validation.v1"
ID_KEY = "execution_validation_id"
PREFIX = "engineering-execution-validation-"
FIELDS = {"execution_preparation_intake_id", "execution_eligibility_id", "execution_preconditions_id", "execution_environment_requirements_id", "execution_resource_plan_id", "checks", "errors", "warnings", "validation_outcome"}


def validate_engineering_execution_preparation(
    intake: Mapping[str, Any],
    eligibility: Mapping[str, Any],
    preconditions: Mapping[str, Any],
    environment: Mapping[str, Any],
    resources: Mapping[str, Any],
) -> dict[str, Any]:
    boundary = intake.get("boundary", {})
    checks = {
        "intake_contract": validate_engineering_execution_preparation_intake(intake).valid,
        "eligibility_confirmed": eligibility.get("status") == "eligible",
        "preconditions_satisfied": preconditions.get("status") == "satisfied",
        "environment_satisfied": environment.get("status") == "satisfied",
        "resources_satisfied": resources.get("status") == "satisfied",
        "approval_granted": boundary.get("approval_authority") == "granted",
        "authorization_granted": boundary.get("authorization_authority") == "granted",
        "execution_not_granted": boundary.get("execution_authority") == "not_granted",
        "mutation_not_granted": boundary.get("mutation_authority") == "not_granted",
    }
    errors = sorted(key for key, passed in checks.items() if not passed)
    outcome = "validated" if not errors else "invalid"
    return preparation_artifact(
        SCHEMA,
        outcome,
        {
            "execution_preparation_intake_id": intake.get("execution_preparation_intake_id"),
            "execution_eligibility_id": eligibility.get("execution_eligibility_id"),
            "execution_preconditions_id": preconditions.get("execution_preconditions_id"),
            "execution_environment_requirements_id": environment.get("execution_environment_requirements_id"),
            "execution_resource_plan_id": resources.get("execution_resource_plan_id"),
            "checks": [{"name": key, "passed": passed} for key, passed in sorted(checks.items())],
            "errors": errors,
            "warnings": [],
            "validation_outcome": outcome,
        },
        ID_KEY,
        PREFIX,
    )


def validate_engineering_execution_validation(value: Any) -> ValidationResult:
    return validate_preparation_artifact(value, schema=SCHEMA, statuses={"validated", "blocked", "invalid"}, id_key=ID_KEY, prefix=PREFIX, fields=FIELDS)


__all__ = ["validate_engineering_execution_preparation", "validate_engineering_execution_validation"]
