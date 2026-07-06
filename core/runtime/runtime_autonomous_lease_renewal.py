from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_autonomous_checkpoint import (
    validate_runtime_loop_checkpoint_record,
)


RUNTIME_AUTONOMOUS_LEASE_RENEWAL_SCHEMA = "zero.runtime.autonomous_lease_renewal.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def evaluate_runtime_lease_renewal_cycle_gate(
    checkpoint_record: Any,
    renewal_request: Any,
    *,
    current_tick_index: int,
) -> dict[str, Any]:
    validation = validate_runtime_loop_checkpoint_record(checkpoint_record)
    request = _mapping(renewal_request)
    current_tick = max(0, int(current_tick_index or 0))
    ttl = _positive_int(request.get("ttl_ticks") or request.get("ttl"))
    emergency_stop = request.get("emergency_stop") is True
    runtime_active = validation.get("runtime_state") == "active"
    authorized_request = request.get("renewal_authorized") is True

    if not checkpoint_record:
        denial = "checkpoint_missing"
        authorized = False
    elif not validation["checkpoint_valid"]:
        denial = "checkpoint_invalid"
        authorized = False
    elif not request:
        denial = "missing_renewal_request"
        authorized = False
    elif not runtime_active:
        denial = "runtime_not_active"
        authorized = False
    elif emergency_stop:
        denial = "emergency_stop_active"
        authorized = False
    elif not authorized_request:
        denial = "renewal_not_authorized"
        authorized = False
    elif ttl <= 0:
        denial = "non_positive_renewal_ttl"
        authorized = False
    else:
        denial = ""
        authorized = True

    lease_id = str(request.get("lease_id") or validation.get("lease_id") or "").strip()
    renewed_checkpoint = None
    if authorized:
        renewed_checkpoint = deepcopy(checkpoint_record)
        renewed_checkpoint["lease_id"] = lease_id
        renewed_checkpoint["lease_expiry_tick"] = current_tick + ttl
        renewed_checkpoint["lease_expiry"] = current_tick + ttl

    return {
        "schema": RUNTIME_AUTONOMOUS_LEASE_RENEWAL_SCHEMA,
        "lease_renewal_authorized": authorized,
        "checkpoint_id": validation.get("checkpoint_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "runtime_active": runtime_active,
        "emergency_stop": emergency_stop,
        "lease_id": lease_id,
        "previous_lease_expiry_tick": validation.get("lease_expiry_tick"),
        "previous_lease_expiry": validation.get("lease_expiry"),
        "lease_expiry_tick": current_tick + ttl if authorized else validation.get("lease_expiry_tick"),
        "lease_expiry": current_tick + ttl if authorized else validation.get("lease_expiry"),
        "ttl_ticks": ttl,
        "renewed_checkpoint": renewed_checkpoint,
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_LEASE_RENEWAL_SCHEMA",
    "evaluate_runtime_lease_renewal_cycle_gate",
]
