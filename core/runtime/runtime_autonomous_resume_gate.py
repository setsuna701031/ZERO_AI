from __future__ import annotations

from typing import Any

from core.runtime.runtime_autonomous_checkpoint import (
    validate_runtime_loop_checkpoint_record,
)


RUNTIME_AUTONOMOUS_RESUME_GATE_SCHEMA = "zero.runtime.autonomous_resume_gate.v1"


def evaluate_crash_recovery_resume_gate(
    checkpoint_record: Any,
    *,
    current_tick_index: int,
    renewal_authorized: bool = False,
) -> dict[str, Any]:
    validation = validate_runtime_loop_checkpoint_record(checkpoint_record)
    expiry = int(validation.get("lease_expiry_tick") or 0)
    current_tick = max(0, int(current_tick_index or 0))
    lease_expired = current_tick >= expiry

    if not checkpoint_record:
        denial = "checkpoint_missing"
        authorized = False
    elif not validation["checkpoint_valid"]:
        denial = "checkpoint_invalid"
        authorized = False
    elif validation["stopped"]:
        denial = "runtime_stopped"
        authorized = False
    elif validation["paused"]:
        denial = "runtime_paused"
        authorized = False
    elif lease_expired and renewal_authorized is not True:
        denial = "lease_expired_renewal_not_authorized"
        authorized = False
    else:
        denial = ""
        authorized = True

    return {
        "schema": RUNTIME_AUTONOMOUS_RESUME_GATE_SCHEMA,
        "resume_authorized": authorized,
        "resume_checkpoint_valid": validation["checkpoint_valid"],
        "checkpoint_id": validation.get("checkpoint_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "active_cursor": validation.get("active_cursor"),
        "current_tick_index": current_tick,
        "checkpoint_tick_index": validation.get("current_tick_index"),
        "last_completed_work_id": validation.get("last_completed_work_id"),
        "lease_id": validation.get("lease_id"),
        "lease_expiry_tick": expiry,
        "lease_expiry": expiry,
        "lease_expired": lease_expired,
        "lease_renewal_required": lease_expired,
        "lease_renewal_authorized": renewal_authorized is True,
        "paused": validation.get("paused"),
        "stopped": validation.get("stopped"),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_RESUME_GATE_SCHEMA",
    "evaluate_crash_recovery_resume_gate",
]
