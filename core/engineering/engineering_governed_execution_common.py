from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

FORBIDDEN_KEYS = frozenset({"command", "shell_command", "patch", "diff", "source_content", "replacement_content", "executor", "scheduler", "approval_token", "authorization_token", "execution_token"})
AUTHORITY_INTAKE = {"approval_authority": "granted", "authorization_authority": "granted", "execution_authority": "not_granted", "mutation_authority": "not_granted"}


def contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(k).lower() in FORBIDDEN_KEYS or contains_forbidden(v) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_forbidden(v) for v in value)
    return False


def governed_boundary(kind: str, *, closed: bool = False) -> dict[str, Any]:
    return {"sealed": True, "read_only": True, "artifact_kind": kind, "repository_modified": False, "runtime_invoked": False, "executor_invoked": False, "mutation_performed": False, "closed": closed}


def artifact(schema: str, status: str, payload: Mapping[str, Any], id_key: str, prefix: str, kind: str, *, closed: bool = False) -> dict[str, Any]:
    return identified({"schema": schema, "status": status, **deepcopy(dict(payload)), "boundary": governed_boundary(kind, closed=closed)}, id_key, prefix)


def validate_artifact(value: Any, *, schema: str, statuses: set[str], id_key: str, prefix: str, kind: str, fields: set[str], closed: bool = False) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    required = {"schema", "status", id_key, "fingerprint", "boundary", *fields}
    errors = [f"missing:{k}" for k in sorted(required - set(value))] + [f"unexpected:{k}" for k in sorted(set(value) - required)]
    if value.get("schema") != schema or value.get("status") not in statuses: errors.append("invalid_contract")
    if value.get("boundary") != governed_boundary(kind, closed=closed): errors.append("unsafe_boundary")
    if contains_forbidden(value): errors.append("forbidden_payload")
    try:
        if not identity_valid(value, id_key, prefix): errors.append("identity_mismatch")
    except (TypeError, ValueError): errors.append("identity_mismatch")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def preparation_valid(value: Any) -> bool:
    if not isinstance(value, Mapping): return False
    return (value.get("schema") == "zero.engineering.execution_preparation_closure.v1" and value.get("status") == "closed_ready" and value.get("preparation_decision") == "ready_for_governed_execution" and value.get("approval_authority_declaration") == "granted" and value.get("authorization_authority_declaration") == "granted" and value.get("execution_authority_declaration") == "not_granted" and value.get("mutation_authority_declaration") == "not_granted" and not contains_forbidden(value))


def contained(child: Any, parent: Any) -> bool:
    if isinstance(parent, Mapping) and isinstance(child, Mapping): return all(k in parent and contained(v, parent[k]) for k, v in child.items())
    if isinstance(parent, list) and isinstance(child, list): return all(v in parent for v in child)
    return child == parent


def link(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    return {f"{name}_id": value.get(f"{name}_id"), f"{name}_fingerprint": value.get("fingerprint")}

__all__ = ["AUTHORITY_INTAKE", "ValidationResult", "artifact", "canonical_json", "contained", "contains_forbidden", "fingerprint", "governed_boundary", "identified", "link", "preparation_valid", "validate_artifact"]
