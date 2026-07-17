from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RUNTIME_IDENTITY_SCHEMA = "zero.runtime.identity.v1"

RUNTIME_IDENTITY_FIELDS = (
    "session_id",
    "runtime_session_id",
    "root_goal_id",
    "source_goal_id",
    "goal_id",
    "goal_lineage_id",
    "branch_type",
    "branch_id",
)

RUNTIME_IDENTITY_REQUIRED_FIELDS = (
    "session_id",
    "runtime_session_id",
)

RUNTIME_IDENTITY_OPTIONAL_FIELDS = tuple(
    field for field in RUNTIME_IDENTITY_FIELDS if field not in RUNTIME_IDENTITY_REQUIRED_FIELDS
)


def runtime_identity_field_set() -> set[str]:
    return set(RUNTIME_IDENTITY_FIELDS)


def runtime_identity_required_field_set() -> set[str]:
    return set(RUNTIME_IDENTITY_REQUIRED_FIELDS)


def missing_runtime_identity_fields(value: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in RUNTIME_IDENTITY_REQUIRED_FIELDS
        if not str(value.get(field) or "").strip()
    ]


def validate_runtime_identity_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "schema": RUNTIME_IDENTITY_SCHEMA,
            "reason": "runtime_identity_not_mapping",
            "missing_fields": list(RUNTIME_IDENTITY_REQUIRED_FIELDS),
        }

    missing_fields = missing_runtime_identity_fields(value)
    if missing_fields:
        return {
            "ok": False,
            "schema": RUNTIME_IDENTITY_SCHEMA,
            "reason": "runtime_identity_missing_required_fields",
            "missing_fields": missing_fields,
        }

    invalid_fields = [
        field
        for field in RUNTIME_IDENTITY_FIELDS
        if field in value and value.get(field) is not None and not isinstance(value.get(field), str)
    ]
    if invalid_fields:
        return {
            "ok": False,
            "schema": RUNTIME_IDENTITY_SCHEMA,
            "reason": "runtime_identity_invalid_string_fields",
            "invalid_fields": invalid_fields,
        }

    return {
        "ok": True,
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "reason": "runtime_identity_shape_valid",
    }


def runtime_identity_contract_summary() -> dict[str, Any]:
    return {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "fields": list(RUNTIME_IDENTITY_FIELDS),
        "required_fields": list(RUNTIME_IDENTITY_REQUIRED_FIELDS),
        "optional_fields": list(RUNTIME_IDENTITY_OPTIONAL_FIELDS),
    }
