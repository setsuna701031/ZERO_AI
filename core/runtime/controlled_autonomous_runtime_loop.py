from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


CONTROLLED_AUTONOMOUS_RUNTIME_LOOP_SCHEMA = (
    "zero.runtime.controlled_autonomous_runtime_loop.v1"
)

LOOP_PLAN_STATUSES = ("planned", "blocked", "stopped")

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


def _authority_value(
    dispatch_request: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    return dispatch_request.get(field) or authority.get(field)


def _missing_authority(
    dispatch_request: dict[str, Any],
    authority: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(dispatch_request, authority, field)
    ]


def _valid_max_ticks(max_ticks: Any) -> bool:
    return isinstance(max_ticks, int) and not isinstance(max_ticks, bool) and max_ticks > 0


def _plan_id(
    *,
    runtime_id: str | None,
    dispatch_request_id: str | None,
    max_ticks: Any,
    plan_status: str,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "dispatch_request_id": dispatch_request_id,
            "max_ticks": max_ticks,
            "plan_status": plan_status,
            "blocked_reason": blocked_reason,
        }
    )
    return f"controlled-runtime-loop-plan::{runtime_id or 'missing-runtime'}::{fragment}"


def _tick_intents(
    *,
    plan_id: str,
    dispatch_request: dict[str, Any],
    max_ticks: int,
) -> list[dict[str, Any]]:
    return [
        {
            "intent_id": f"{plan_id}::tick-intent::{index + 1}",
            "tick_number": index + 1,
            "source_dispatch_request_id": dispatch_request.get("dispatch_request_id"),
            "requested_action": "ALLOW_SINGLE_TICK",
            "execution_requested": True,
            "actual_executor_called": False,
            "stop_if_status": ["blocked", "recovery", "complete"],
        }
        for index in range(max_ticks)
    ]


def build_controlled_runtime_loop_plan(
    bounded_executor_dispatch_request: dict[str, Any] | None,
    *,
    max_ticks: int | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dispatch = _as_mapping(bounded_executor_dispatch_request)
    authority_record = _as_mapping(authority)
    missing = _missing_authority(dispatch, authority_record)

    if not _valid_max_ticks(max_ticks):
        plan_status = "blocked"
        blocked_reason = "max_ticks_required"
        planned_tick_count = 0
    elif not dispatch.get("dispatch_request_id"):
        plan_status = "blocked"
        blocked_reason = "missing_dispatch_request"
        planned_tick_count = 0
    elif dispatch.get("dispatch_status") != "dispatch_requested":
        plan_status = "stopped"
        blocked_reason = dispatch.get("blocked_reason") or "dispatch_not_requested"
        planned_tick_count = 0
    elif missing:
        plan_status = "blocked"
        blocked_reason = "missing_authority:" + ",".join(missing)
        planned_tick_count = 0
    else:
        plan_status = "planned"
        blocked_reason = "none"
        planned_tick_count = int(max_ticks)

    plan_id = _plan_id(
        runtime_id=dispatch.get("runtime_id"),
        dispatch_request_id=dispatch.get("dispatch_request_id"),
        max_ticks=max_ticks,
        plan_status=plan_status,
        blocked_reason=blocked_reason,
    )
    intents = (
        _tick_intents(
            plan_id=plan_id,
            dispatch_request=dispatch,
            max_ticks=planned_tick_count,
        )
        if plan_status == "planned"
        else []
    )

    return {
        "schema": CONTROLLED_AUTONOMOUS_RUNTIME_LOOP_SCHEMA,
        "plan_id": plan_id,
        "runtime_id": dispatch.get("runtime_id"),
        "source_dispatch_request_id": dispatch.get("dispatch_request_id"),
        "plan_status": plan_status,
        "max_ticks": max_ticks,
        "planned_tick_count": planned_tick_count,
        "tick_intents": intents,
        "blocked_reason": blocked_reason,
        "stop_conditions": ["blocked", "recovery", "complete"],
        "execution_lease_id": _authority_value(
            dispatch, authority_record, "execution_lease_id"
        ),
        "capability_grant_id": _authority_value(
            dispatch, authority_record, "capability_grant_id"
        ),
        "executor_binding_id": _authority_value(
            dispatch, authority_record, "executor_binding_id"
        ),
        "missing_authority": missing,
        "ordered_tick_intents_only": True,
        "actual_executor_called": False,
        "direct_executor_call_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_runtime_loop_audit_projection(
    loop_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = _as_mapping(loop_plan)
    return {
        "projection": "controlled_autonomous_runtime_loop_audit",
        "projection_only": True,
        "plan_id": plan.get("plan_id"),
        "runtime_id": plan.get("runtime_id"),
        "source_dispatch_request_id": plan.get("source_dispatch_request_id"),
        "plan_status": plan.get("plan_status", "blocked"),
        "max_ticks": plan.get("max_ticks"),
        "planned_tick_count": plan.get("planned_tick_count", 0),
        "blocked_reason": plan.get("blocked_reason", "not_evaluated"),
        "ordered_tick_intents_only": True,
        "actual_executor_called": False,
        "direct_executor_call_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_runtime_loop_audit_record(
    bounded_executor_dispatch_request: dict[str, Any] | None,
    *,
    max_ticks: int | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = build_controlled_runtime_loop_plan(
        bounded_executor_dispatch_request,
        max_ticks=max_ticks,
        authority=authority,
    )
    return {
        "audit_schema": CONTROLLED_AUTONOMOUS_RUNTIME_LOOP_SCHEMA + ".audit",
        "decision": "reserved_controlled_autonomous_runtime_loop_plan_only",
        "controlled_runtime_loop_plan": plan,
        "audit_projection": build_controlled_runtime_loop_audit_projection(plan),
        "actual_executor_called": False,
        "direct_executor_call_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_runtime_loop_milestone_seal(
    bounded_executor_dispatch_request: dict[str, Any] | None,
    *,
    max_ticks: int | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_controlled_runtime_loop_audit_record(
        bounded_executor_dispatch_request,
        max_ticks=max_ticks,
        authority=authority,
    )
    plan = _as_mapping(audit.get("controlled_runtime_loop_plan"))
    return {
        "seal": "controlled_autonomous_runtime_loop_bundle",
        "schema": CONTROLLED_AUTONOMOUS_RUNTIME_LOOP_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_BOUNDED_AUTONOMOUS_LOOP_PLANS_ONLY",
        "plan_id": plan.get("plan_id"),
        "plan_status": plan.get("plan_status"),
        "planned_tick_count": plan.get("planned_tick_count"),
        "ordered_tick_intents_only": True,
        "actual_executor_called": False,
        "direct_executor_call_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "CONTROLLED_AUTONOMOUS_RUNTIME_LOOP_SCHEMA",
    "LOOP_PLAN_STATUSES",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_controlled_runtime_loop_plan",
    "build_controlled_runtime_loop_audit_projection",
    "build_controlled_runtime_loop_audit_record",
    "build_controlled_runtime_loop_milestone_seal",
]
