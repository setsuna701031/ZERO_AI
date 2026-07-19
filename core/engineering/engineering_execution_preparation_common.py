from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult


FORBIDDEN_KEYS = frozenset(
    {
        "command",
        "diff",
        "execution_token",
        "mutation_adapter",
        "patch",
        "replacement_content",
        "shell_command",
        "source_content",
    }
)


def execution_preparation_boundary(*, closed: bool = False) -> dict[str, Any]:
    return {
        "sealed": True,
        "read_only": True,
        "execution_preparation_artifact": True,
        "execution_preparation_closed": closed,
        "repository_modified": False,
        "patch_generated": False,
        "diff_generated": False,
        "execution_started": False,
        "approval_authority": "granted",
        "authorization_authority": "granted",
        "execution_authority": "not_granted",
        "mutation_authority": "not_granted",
    }


def contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in FORBIDDEN_KEYS or contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_forbidden(item) for item in value)
    return False


def preparation_artifact(
    schema: str,
    status: str,
    payload: Mapping[str, Any],
    id_key: str,
    prefix: str,
    *,
    closed: bool = False,
) -> dict[str, Any]:
    return identified(
        {
            "schema": schema,
            "status": status,
            **deepcopy(dict(payload)),
            "boundary": execution_preparation_boundary(closed=closed),
        },
        id_key,
        prefix,
    )


def validate_preparation_artifact(
    value: Any,
    *,
    schema: str,
    statuses: set[str],
    id_key: str,
    prefix: str,
    fields: set[str],
    closed: bool = False,
) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    required = {"schema", "status", id_key, "fingerprint", "boundary", *fields}
    errors = [f"missing:{key}" for key in sorted(required - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != schema or value.get("status") not in statuses:
        errors.append("invalid_contract")
    if value.get("boundary") != execution_preparation_boundary(closed=closed):
        errors.append("unsafe_boundary")
    if contains_forbidden(value):
        errors.append("forbidden_payload")
    try:
        if not identity_valid(value, id_key, prefix):
            errors.append("identity_mismatch")
    except (TypeError, ValueError):
        errors.append("identity_mismatch")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def stable_record(payload: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    return identified(deepcopy(dict(payload)), id_key, prefix)


def validate_authorization_closure(value: Any) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    if value.get("schema") != "zero.engineering.authorization_closure.v1" or value.get("status") != "closed_authorized":
        errors.append("authorization_closure_not_authorized")
    try:
        if not identity_valid(value, "authorization_closure_id", "engineering-authorization-closure-"):
            errors.append("authorization_closure_identity_mismatch")
    except (TypeError, ValueError):
        errors.append("authorization_closure_identity_mismatch")
    boundary = value.get("boundary", {})
    expected = {
        "approval_authority": "granted",
        "authorization_authority": "granted",
        "execution_authority": "not_granted",
        "mutation_authority": "not_granted",
    }
    if any(boundary.get(key) != expected_value for key, expected_value in expected.items()):
        errors.append("authorization_boundary_mismatch")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


__all__ = [
    "ValidationResult",
    "canonical_json",
    "contains_forbidden",
    "execution_preparation_boundary",
    "fingerprint",
    "preparation_artifact",
    "stable_record",
    "validate_authorization_closure",
    "validate_preparation_artifact",
]
