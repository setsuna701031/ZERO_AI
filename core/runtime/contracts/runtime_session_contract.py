from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RUNTIME_SESSION_SCHEMA = "zero.runtime.session.v1"

RUNTIME_SESSION_FIELDS = (
    "session_id",
    "runtime_session_id",
    "status",
    "created_at",
    "updated_at",
    "resume_session_id",
    "package_id",
    "execution_id",
)

RUNTIME_SESSION_REQUIRED_FIELDS = (
    "session_id",
    "runtime_session_id",
    "status",
)

RUNTIME_SESSION_TERMINAL_STATUSES = (
    "finished",
    "failed",
    "cancelled",
    "blocked",
)

RUNTIME_SESSION_ACTIVE_STATUSES = (
    "queued",
    "running",
    "retrying",
    "recovering",
)

RUNTIME_SESSION_KNOWN_STATUSES = RUNTIME_SESSION_ACTIVE_STATUSES + RUNTIME_SESSION_TERMINAL_STATUSES


def normalize_runtime_session_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "success": "finished",
        "complete": "finished",
        "completed": "finished",
        "error": "failed",
        "failure": "failed",
        "in_progress": "running",
        "pending": "queued",
    }
    return aliases.get(text, text)


def is_runtime_session_terminal_status(value: Any) -> bool:
    return normalize_runtime_session_status(value) in RUNTIME_SESSION_TERMINAL_STATUSES


def is_runtime_session_active_status(value: Any) -> bool:
    return normalize_runtime_session_status(value) in RUNTIME_SESSION_ACTIVE_STATUSES


def validate_runtime_session_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "schema": RUNTIME_SESSION_SCHEMA,
            "reason": "runtime_session_not_mapping",
            "missing_fields": list(RUNTIME_SESSION_REQUIRED_FIELDS),
        }

    missing_fields = [
        field
        for field in RUNTIME_SESSION_REQUIRED_FIELDS
        if not str(value.get(field) or "").strip()
    ]
    if missing_fields:
        return {
            "ok": False,
            "schema": RUNTIME_SESSION_SCHEMA,
            "reason": "runtime_session_missing_required_fields",
            "missing_fields": missing_fields,
        }

    status = normalize_runtime_session_status(value.get("status"))
    if status not in RUNTIME_SESSION_KNOWN_STATUSES:
        return {
            "ok": False,
            "schema": RUNTIME_SESSION_SCHEMA,
            "reason": "runtime_session_unknown_status",
            "status": status,
        }

    return {
        "ok": True,
        "schema": RUNTIME_SESSION_SCHEMA,
        "reason": "runtime_session_shape_valid",
        "normalized_status": status,
        "terminal": is_runtime_session_terminal_status(status),
    }


def runtime_session_contract_summary() -> dict[str, Any]:
    return {
        "schema": RUNTIME_SESSION_SCHEMA,
        "fields": list(RUNTIME_SESSION_FIELDS),
        "required_fields": list(RUNTIME_SESSION_REQUIRED_FIELDS),
        "active_statuses": list(RUNTIME_SESSION_ACTIVE_STATUSES),
        "terminal_statuses": list(RUNTIME_SESSION_TERMINAL_STATUSES),
        "known_statuses": list(RUNTIME_SESSION_KNOWN_STATUSES),
    }
