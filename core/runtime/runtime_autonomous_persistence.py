from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_autonomous_checkpoint import (
    RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA,
    validate_runtime_loop_checkpoint_record,
)


RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA = "zero.runtime.autonomous_persistence.v1"


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def persist_runtime_autonomous_session(
    storage_path: str | Path,
    checkpoint_record: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_loop_checkpoint_record(checkpoint_record)
    path = _path(storage_path)

    if not validation["checkpoint_valid"]:
        return {
            "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
            "persisted": False,
            "loaded": False,
            "storage_path": str(path),
            "checkpoint": None,
            "denial_reason": validation["denial_reason"],
            "runtime_session_id": validation.get("runtime_session_id"),
            "active_cursor": validation.get("active_cursor"),
            "current_tick_index": validation.get("current_tick_index"),
            "last_completed_work_id": validation.get("last_completed_work_id"),
            "lease_id": validation.get("lease_id"),
            "lease_expiry_tick": validation.get("lease_expiry_tick"),
            "lease_expiry": validation.get("lease_expiry"),
            "paused": validation.get("paused"),
            "stopped": validation.get("stopped"),
            "runtime_state_mutated": False,
            "cursor_advanced": False,
            "work_started": False,
        }

    payload = {
        "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
        "checkpoint_schema": RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA,
        "checkpoint": checkpoint_record,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    temp_path.replace(path)

    return {
        "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
        "persisted": True,
        "loaded": False,
        "storage_path": str(path),
        "checkpoint": checkpoint_record,
        "denial_reason": "",
        "runtime_session_id": validation["runtime_session_id"],
        "active_cursor": validation["active_cursor"],
        "current_tick_index": validation["current_tick_index"],
        "last_completed_work_id": validation["last_completed_work_id"],
        "lease_id": validation["lease_id"],
        "lease_expiry_tick": validation["lease_expiry_tick"],
        "lease_expiry": validation["lease_expiry"],
        "paused": validation["paused"],
        "stopped": validation["stopped"],
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


def load_runtime_autonomous_session(storage_path: str | Path) -> dict[str, Any]:
    path = _path(storage_path)
    if not path.exists():
        return {
            "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
            "persisted": False,
            "loaded": False,
            "storage_path": str(path),
            "checkpoint": None,
            "denial_reason": "checkpoint_missing",
            "runtime_state_mutated": False,
            "cursor_advanced": False,
            "work_started": False,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
            "persisted": True,
            "loaded": False,
            "storage_path": str(path),
            "checkpoint": None,
            "denial_reason": "checkpoint_unreadable",
            "runtime_state_mutated": False,
            "cursor_advanced": False,
            "work_started": False,
        }

    checkpoint = payload.get("checkpoint") if isinstance(payload, dict) else None
    validation = validate_runtime_loop_checkpoint_record(checkpoint)
    return {
        "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA,
        "persisted": True,
        "loaded": validation["checkpoint_valid"],
        "storage_path": str(path),
        "checkpoint": checkpoint if validation["checkpoint_valid"] else None,
        "denial_reason": "" if validation["checkpoint_valid"] else validation["denial_reason"],
        "runtime_session_id": validation.get("runtime_session_id"),
        "active_cursor": validation.get("active_cursor"),
        "current_tick_index": validation.get("current_tick_index"),
        "last_completed_work_id": validation.get("last_completed_work_id"),
        "lease_id": validation.get("lease_id"),
        "lease_expiry_tick": validation.get("lease_expiry_tick"),
        "lease_expiry": validation.get("lease_expiry"),
        "paused": validation.get("paused"),
        "stopped": validation.get("stopped"),
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


def build_long_running_runtime_survival_seal(
    persistence_record: dict[str, Any],
    resume_gate_record: dict[str, Any],
    lease_renewal_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    renewal = lease_renewal_record or {}
    survived = (
        persistence_record.get("persisted") is True
        and resume_gate_record.get("resume_authorized") is True
    )
    return {
        "schema": RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA + ".survival_seal",
        "seal": "runtime_autonomous_persistence_survival",
        "closed": True,
        "survival_authorized": survived,
        "runtime_session_id": persistence_record.get("runtime_session_id"),
        "active_cursor": persistence_record.get("active_cursor"),
        "current_tick_index": persistence_record.get("current_tick_index"),
        "last_completed_work_id": persistence_record.get("last_completed_work_id"),
        "lease_id": persistence_record.get("lease_id") or renewal.get("lease_id"),
        "lease_expiry_tick": persistence_record.get("lease_expiry_tick")
        or renewal.get("lease_expiry_tick"),
        "lease_expiry": persistence_record.get("lease_expiry") or renewal.get("lease_expiry"),
        "paused": persistence_record.get("paused"),
        "stopped": persistence_record.get("stopped"),
        "denial_reason": "" if survived else resume_gate_record.get("denial_reason", ""),
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_PERSISTENCE_SCHEMA",
    "persist_runtime_autonomous_session",
    "load_runtime_autonomous_session",
    "build_long_running_runtime_survival_seal",
]
