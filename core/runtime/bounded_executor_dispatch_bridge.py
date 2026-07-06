from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


BOUNDED_EXECUTOR_DISPATCH_BRIDGE_SCHEMA = (
    "zero.runtime.bounded_executor_dispatch_bridge.v1"
)

BOUNDED_EXECUTOR_DISPATCH_STATUSES = ("dispatch_requested", "blocked")

REQUIRED_AUTHORITY_FIELDS = (
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _authority_value(tick_result: dict[str, Any], field: str) -> Any:
    authority = _as_mapping(tick_result.get("authority"))
    return tick_result.get(field) or authority.get(field)


def _missing_authority(tick_result: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(tick_result, field)
    ]


def _dispatch_request_id(
    *,
    runtime_id: str | None,
    tick_id: str | None,
    requested_action: str | None,
    dispatch_status: str,
    execution_requested: bool,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "tick_id": tick_id,
            "requested_action": requested_action,
            "dispatch_status": dispatch_status,
            "execution_requested": execution_requested,
            "blocked_reason": blocked_reason,
        }
    )
    return f"bounded-executor-dispatch::{runtime_id or 'missing-runtime'}::{fragment}"


def build_bounded_executor_dispatch_request(
    runtime_tick_result: dict[str, Any] | None,
) -> dict[str, Any]:
    tick = _as_mapping(runtime_tick_result)
    missing = _missing_authority(tick)
    allowed_tick = tick.get("tick_status") == "ALLOW_SINGLE_TICK"
    source_tick_id = tick.get("tick_id")

    if not source_tick_id:
        dispatch_status = "blocked"
        execution_requested = False
        blocked_reason = "missing_tick_result"
    elif not allowed_tick:
        dispatch_status = "blocked"
        execution_requested = False
        blocked_reason = "tick_status_not_dispatchable"
    elif missing:
        dispatch_status = "blocked"
        execution_requested = False
        blocked_reason = "missing_authority:" + ",".join(missing)
    else:
        dispatch_status = "dispatch_requested"
        execution_requested = True
        blocked_reason = "none"

    request_id = _dispatch_request_id(
        runtime_id=tick.get("runtime_id"),
        tick_id=source_tick_id,
        requested_action=tick.get("requested_action"),
        dispatch_status=dispatch_status,
        execution_requested=execution_requested,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": BOUNDED_EXECUTOR_DISPATCH_BRIDGE_SCHEMA,
        "dispatch_request_id": request_id,
        "runtime_id": tick.get("runtime_id"),
        "source_tick_id": source_tick_id,
        "source_cycle_id": tick.get("source_cycle_id"),
        "tick_status": tick.get("tick_status"),
        "requested_action": tick.get("requested_action"),
        "dispatch_status": dispatch_status,
        "execution_lease_id": _authority_value(tick, "execution_lease_id"),
        "capability_grant_id": _authority_value(tick, "capability_grant_id"),
        "executor_binding_id": _authority_value(tick, "executor_binding_id"),
        "execution_requested": execution_requested,
        "actual_executor_called": False,
        "blocked_reason": blocked_reason,
        "missing_authority": missing,
        "dispatch_intent_only": True,
        "single_dispatch_request_only": True,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "direct_executor_call_performed": False,
        "loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
    }


def build_bounded_executor_dispatch_bridge_audit_projection(
    dispatch_request: dict[str, Any] | None,
) -> dict[str, Any]:
    request = _as_mapping(dispatch_request)
    return {
        "projection": "bounded_executor_dispatch_bridge_audit",
        "projection_only": True,
        "dispatch_request_id": request.get("dispatch_request_id"),
        "runtime_id": request.get("runtime_id"),
        "source_tick_id": request.get("source_tick_id"),
        "source_cycle_id": request.get("source_cycle_id"),
        "tick_status": request.get("tick_status"),
        "requested_action": request.get("requested_action"),
        "dispatch_status": request.get("dispatch_status", "blocked"),
        "execution_requested": request.get("execution_requested") is True,
        "actual_executor_called": False,
        "blocked_reason": request.get("blocked_reason", "not_evaluated"),
        "missing_authority": deepcopy(request.get("missing_authority", [])),
        "dispatch_intent_only": True,
        "single_dispatch_request_only": True,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "direct_executor_call_performed": False,
        "loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
    }


def build_bounded_executor_dispatch_bridge_audit_record(
    runtime_tick_result: dict[str, Any] | None,
) -> dict[str, Any]:
    request = build_bounded_executor_dispatch_request(runtime_tick_result)
    return {
        "audit_schema": BOUNDED_EXECUTOR_DISPATCH_BRIDGE_SCHEMA + ".audit",
        "decision": "reserved_bounded_executor_dispatch_request_only",
        "bounded_executor_dispatch_request": request,
        "audit_projection": build_bounded_executor_dispatch_bridge_audit_projection(
            request
        ),
        "actual_executor_called": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "direct_executor_call_performed": False,
        "loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
    }


def build_bounded_executor_dispatch_bridge_milestone_seal(
    runtime_tick_result: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_bounded_executor_dispatch_bridge_audit_record(
        runtime_tick_result
    )
    request = _as_mapping(audit.get("bounded_executor_dispatch_request"))
    return {
        "seal": "bounded_executor_dispatch_bridge_bundle",
        "schema": BOUNDED_EXECUTOR_DISPATCH_BRIDGE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_BOUNDED_EXECUTOR_DISPATCH_REQUESTS_ONLY",
        "dispatch_request_id": request.get("dispatch_request_id"),
        "dispatch_status": request.get("dispatch_status"),
        "execution_requested": request.get("execution_requested") is True,
        "actual_executor_called": False,
        "dispatch_intent_only": True,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "direct_executor_call_performed": False,
        "loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "BOUNDED_EXECUTOR_DISPATCH_BRIDGE_SCHEMA",
    "BOUNDED_EXECUTOR_DISPATCH_STATUSES",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_bounded_executor_dispatch_request",
    "build_bounded_executor_dispatch_bridge_audit_projection",
    "build_bounded_executor_dispatch_bridge_audit_record",
    "build_bounded_executor_dispatch_bridge_milestone_seal",
]
