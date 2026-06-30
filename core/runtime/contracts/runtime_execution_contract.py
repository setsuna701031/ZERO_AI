from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RUNTIME_EXECUTION_SCHEMA = "zero.runtime.execution.v1"

RUNTIME_EXECUTION_FIELDS = (
    "execution_id",
    "session_id",
    "runtime_session_id",
    "task_id",
    "step_id",
    "step_type",
    "execution_mode",
    "execution_authority",
    "authority_context",
    "runtime_identity",
)

RUNTIME_EXECUTION_REQUIRED_FIELDS = (
    "execution_id",
    "session_id",
    "runtime_session_id",
    "task_id",
)

RUNTIME_EXECUTION_MODES = (
    "execute",
    "replay",
    "audit",
    "repair_replay",
)


def normalize_runtime_execution_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in RUNTIME_EXECUTION_MODES:
        return text
    return "execute"


def validate_runtime_execution_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "schema": RUNTIME_EXECUTION_SCHEMA,
            "reason": "runtime_execution_not_mapping",
            "missing_fields": list(RUNTIME_EXECUTION_REQUIRED_FIELDS),
        }

    missing_fields = [
        field
        for field in RUNTIME_EXECUTION_REQUIRED_FIELDS
        if not str(value.get(field) or "").strip()
    ]
    if missing_fields:
        return {
            "ok": False,
            "schema": RUNTIME_EXECUTION_SCHEMA,
            "reason": "runtime_execution_missing_required_fields",
            "missing_fields": missing_fields,
        }

    mapping_fields = [
        field
        for field in ("execution_authority", "authority_context", "runtime_identity")
        if field in value and value.get(field) is not None and not isinstance(value.get(field), Mapping)
    ]
    if mapping_fields:
        return {
            "ok": False,
            "schema": RUNTIME_EXECUTION_SCHEMA,
            "reason": "runtime_execution_invalid_mapping_fields",
            "invalid_fields": mapping_fields,
        }

    return {
        "ok": True,
        "schema": RUNTIME_EXECUTION_SCHEMA,
        "reason": "runtime_execution_shape_valid",
        "normalized_execution_mode": normalize_runtime_execution_mode(value.get("execution_mode")),
    }


def runtime_execution_contract_summary() -> dict[str, Any]:
    return {
        "schema": RUNTIME_EXECUTION_SCHEMA,
        "fields": list(RUNTIME_EXECUTION_FIELDS),
        "required_fields": list(RUNTIME_EXECUTION_REQUIRED_FIELDS),
        "execution_modes": list(RUNTIME_EXECUTION_MODES),
    }
