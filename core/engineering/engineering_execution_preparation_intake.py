from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_execution_preparation_common import (
    ValidationResult,
    preparation_artifact,
    validate_authorization_closure,
    validate_preparation_artifact,
)


SCHEMA = "zero.engineering.execution_preparation_intake.v1"
ID_KEY = "execution_preparation_intake_id"
PREFIX = "engineering-execution-preparation-intake-"
FIELDS = {
    "authorization_closure_id",
    "authorization_closure_fingerprint",
    "approval_closure_id",
    "proposal_review_closure_id",
    "repository_identity",
    "analyzed_revision",
    "preparation_objective",
    "evidence_references",
    "constraints",
    "authority_declarations",
}
AUTHORITY = {
    "approval_authority": "granted",
    "authorization_authority": "granted",
    "execution_authority": "not_granted",
    "mutation_authority": "not_granted",
}


def build_engineering_execution_preparation_intake(
    closure: Mapping[str, Any], intent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supplied = dict(intent or {})
    authority_valid = not any(
        supplied.get(key) not in (None, expected) for key, expected in AUTHORITY.items()
    )
    accepted = validate_authorization_closure(closure).valid and authority_valid
    payload = {
        "authorization_closure_id": closure.get("authorization_closure_id"),
        "authorization_closure_fingerprint": closure.get("fingerprint"),
        "approval_closure_id": closure.get("approval_closure_id"),
        "proposal_review_closure_id": closure.get("proposal_review_closure_id"),
        "repository_identity": closure.get("repository_identity"),
        "analyzed_revision": closure.get("analyzed_revision"),
        "preparation_objective": supplied.get("preparation_objective", "prepare governed engineering execution"),
        "evidence_references": sorted(set(supplied.get("evidence_references", []))),
        "constraints": sorted(set(supplied.get("constraints", []))),
        "authority_declarations": dict(AUTHORITY),
    }
    return preparation_artifact(SCHEMA, "accepted" if accepted else "invalid", payload, ID_KEY, PREFIX)


def validate_engineering_execution_preparation_intake(value: Any) -> ValidationResult:
    return validate_preparation_artifact(
        value,
        schema=SCHEMA,
        statuses={"accepted", "blocked", "invalid", "insufficient_evidence"},
        id_key=ID_KEY,
        prefix=PREFIX,
        fields=FIELDS,
    )


__all__ = ["AUTHORITY", "build_engineering_execution_preparation_intake", "validate_engineering_execution_preparation_intake"]
