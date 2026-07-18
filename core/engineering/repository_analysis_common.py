from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from core.engineering.engineering_intake_common import identified, identity_valid

EXCLUDED_DIRECTORIES = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist",
    ".cache", "cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", "vendor",
})
MAX_ENTRIES = 5000
MAX_HASH_BYTES = 4 * 1024 * 1024
MAX_PREVIEW_BYTES = 16 * 1024
MAX_DEPENDENCY_FILES = 1000
MAX_DEPENDENCY_FILE_BYTES = 512 * 1024


@dataclass(frozen=True)
class AdmittedRepositoryRoot:
    artifact: dict[str, Any]
    root: Path | None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]


def boundary(*, completed: bool = False) -> dict[str, bool]:
    return {
        "sealed": True, "read_only": True, "repository_analysis_completed": completed,
        "repository_modified": False, "planning_started": False,
        "proposal_created": False, "coding_started": False, "execution_started": False,
        "mutation_allowed": False, "approval_granted": False,
        "authorization_granted": False, "runtime_activation": False,
        "authority_granted": False, "scope_expansion": False,
    }


def artifact(schema: str, status: str, payload: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    return identified({"schema": schema, "status": status, **deepcopy(dict(payload)), "boundary": boundary()}, id_key, prefix)


def validate_artifact(value: Any, *, schema: str, statuses: set[str], id_key: str,
                      prefix: str, fields: set[str], completed: bool = False) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    required = {"schema", "status", id_key, "fingerprint", "boundary", *fields}
    errors = [f"missing:{key}" for key in sorted(required - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != schema or value.get("status") not in statuses:
        errors.append("invalid_contract")
    if value.get("boundary") != boundary(completed=completed):
        errors.append("unsafe_boundary")
    try:
        if not identity_valid(value, id_key, prefix):
            errors.append("identity_mismatch")
    except (TypeError, ValueError):
        errors.append("identity_mismatch")
    if _contains_absolute_or_forbidden(value):
        errors.append("forbidden_content")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def relative_path_valid(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and ":" not in path.parts[0]


def _contains_absolute_or_forbidden(value: Any, key: str = "") -> bool:
    if isinstance(value, Mapping):
        return any(_contains_absolute_or_forbidden(v, str(k)) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_absolute_or_forbidden(v, key) for v in value)
    if isinstance(value, str):
        if key in {"observation", "warning", "warnings", "reason", "reasons"} and ("Traceback" in value or "File \"" in value):
            return True
        if key.endswith("path") or key.endswith("paths") or key == "source_relative_path":
            return bool(value) and not relative_path_valid(value)
    return False


def linked(source: Mapping[str, Any], name: str, id_key: str) -> dict[str, Any]:
    return {f"source_{name}_id": source.get(id_key), f"source_{name}_fingerprint": source.get("fingerprint")}


def sources_match(value: Mapping[str, Any], source: Mapping[str, Any], name: str, id_key: str) -> bool:
    return value.get(f"source_{name}_id") == source.get(id_key) and value.get(f"source_{name}_fingerprint") == source.get("fingerprint")


__all__ = ["AdmittedRepositoryRoot", "EXCLUDED_DIRECTORIES", "MAX_DEPENDENCY_FILES",
           "MAX_DEPENDENCY_FILE_BYTES", "MAX_ENTRIES", "MAX_HASH_BYTES", "MAX_PREVIEW_BYTES",
           "ValidationResult", "artifact", "boundary", "linked", "relative_path_valid",
           "sources_match", "validate_artifact"]
