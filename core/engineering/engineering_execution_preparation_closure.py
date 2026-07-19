from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import ValidationResult, preparation_artifact, validate_preparation_artifact


SCHEMA = "zero.engineering.execution_preparation_closure.v1"
ID_KEY = "execution_preparation_closure_id"
PREFIX = "engineering-execution-preparation-closure-"
FIELDS = {
    "authorization_closure_id",
    "execution_preparation_intake_id",
    "execution_eligibility_id",
    "execution_preconditions_id",
    "execution_environment_requirements_id",
    "execution_resource_plan_id",
    "execution_validation_id",
    "repository_identity",
    "analyzed_revision",
    "preparation_decision",
    "approval_authority_declaration",
    "authorization_authority_declaration",
    "execution_authority_declaration",
    "mutation_authority_declaration",
    "governance_declaration",
    "next_boundary_declaration",
}


def build_engineering_execution_preparation_closure(
    intake: Mapping[str, Any],
    eligibility: Mapping[str, Any],
    preconditions: Mapping[str, Any],
    environment: Mapping[str, Any],
    resources: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    ready = validation.get("status") == "validated"
    status = "closed_ready" if ready else "invalid"
    payload = {
        "authorization_closure_id": intake.get("authorization_closure_id"),
        "execution_preparation_intake_id": intake.get("execution_preparation_intake_id"),
        "execution_eligibility_id": eligibility.get("execution_eligibility_id"),
        "execution_preconditions_id": preconditions.get("execution_preconditions_id"),
        "execution_environment_requirements_id": environment.get("execution_environment_requirements_id"),
        "execution_resource_plan_id": resources.get("execution_resource_plan_id"),
        "execution_validation_id": validation.get("execution_validation_id"),
        "repository_identity": intake.get("repository_identity"),
        "analyzed_revision": intake.get("analyzed_revision"),
        "preparation_decision": "ready_for_governed_execution" if ready else "not_ready",
        "approval_authority_declaration": "granted",
        "authorization_authority_declaration": "granted",
        "execution_authority_declaration": "not_granted",
        "mutation_authority_declaration": "not_granted",
        "governance_declaration": {
            "preparation_is_execution": False,
            "repository_mutation_allowed": False,
            "execution_allowed": False,
        },
        "next_boundary_declaration": {
            "state": "ready_for_governed_execution" if ready else "not_ready",
            "execution_authority": "not_granted",
            "mutation_authority": "not_granted",
        },
    }
    return preparation_artifact(SCHEMA, status, payload, ID_KEY, PREFIX, closed=True)


def validate_engineering_execution_preparation_closure(value: Any) -> ValidationResult:
    return validate_preparation_artifact(value, schema=SCHEMA, statuses={"closed_ready", "blocked", "invalid", "insufficient_evidence"}, id_key=ID_KEY, prefix=PREFIX, fields=FIELDS, closed=True)


__all__ = ["build_engineering_execution_preparation_closure", "validate_engineering_execution_preparation_closure"]
