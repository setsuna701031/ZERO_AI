from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


CONTROLLED_LOOP_PLAN_EXECUTOR_SCHEMA = "zero.runtime.controlled_loop_plan_executor.v1"

LOOP_PLAN_EXECUTION_STATUSES = ("ONE_TICK_SELECTED", "BLOCKED")

REQUIRED_AUTHORITY_FIELDS = (
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _authority_value(authority: dict[str, Any], field: str) -> Any:
    return authority.get(field)


def _missing_authority(authority: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(authority, field)
    ]


def _find_intent(loop_plan: dict[str, Any], selected_tick_intent_id: str | None) -> dict[str, Any]:
    for intent in _as_list(loop_plan.get("tick_intents")):
        record = _as_mapping(intent)
        if record.get("intent_id") == selected_tick_intent_id:
            return record
    return {}


def _execution_record_id(
    *,
    runtime_id: str | None,
    source_loop_plan_id: str | None,
    selected_tick_intent_id: str | None,
    execution_status: str,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_loop_plan_id": source_loop_plan_id,
            "selected_tick_intent_id": selected_tick_intent_id,
            "execution_status": execution_status,
            "blocked_reason": blocked_reason,
        }
    )
    return f"controlled-loop-plan-execution::{runtime_id or 'missing-runtime'}::{fragment}"


def build_controlled_loop_plan_execution_record(
    controlled_runtime_loop_plan: dict[str, Any] | None,
    *,
    selected_tick_intent_id: str | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = _as_mapping(controlled_runtime_loop_plan)
    authority_record = _as_mapping(authority)
    missing_authority = _missing_authority(authority_record)
    intents = _as_list(plan.get("tick_intents"))
    selected_intent = _find_intent(plan, selected_tick_intent_id)

    if plan.get("plan_status") != "planned":
        execution_status = "BLOCKED"
        blocked_reason = "loop_plan_not_planned"
    elif not intents:
        execution_status = "BLOCKED"
        blocked_reason = "empty_plan"
    elif missing_authority:
        execution_status = "BLOCKED"
        blocked_reason = "missing_authority:" + ",".join(missing_authority)
    elif not selected_tick_intent_id or not selected_intent:
        execution_status = "BLOCKED"
        blocked_reason = "invalid_tick_intent_id"
    else:
        execution_status = "ONE_TICK_SELECTED"
        blocked_reason = "none"

    dispatch_allowed = execution_status == "ONE_TICK_SELECTED"
    execution_record_id = _execution_record_id(
        runtime_id=plan.get("runtime_id"),
        source_loop_plan_id=plan.get("plan_id"),
        selected_tick_intent_id=selected_tick_intent_id,
        execution_status=execution_status,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": CONTROLLED_LOOP_PLAN_EXECUTOR_SCHEMA,
        "execution_record_id": execution_record_id,
        "runtime_id": plan.get("runtime_id"),
        "source_loop_plan_id": plan.get("plan_id"),
        "selected_tick_intent_id": selected_tick_intent_id,
        "selected_tick_intent": selected_intent if dispatch_allowed else {},
        "execution_status": execution_status,
        "dispatch_allowed": dispatch_allowed,
        "executor_called": False,
        "scheduler_called": False,
        "loop_continued": False,
        "blocked_reason": blocked_reason,
        "execution_lease_id": _authority_value(authority_record, "execution_lease_id"),
        "capability_grant_id": _authority_value(authority_record, "capability_grant_id"),
        "executor_binding_id": _authority_value(authority_record, "executor_binding_id"),
        "missing_authority": missing_authority,
        "one_tick_intent_only": True,
        "actual_executor_called": False,
        "direct_executor_call_performed": False,
        "direct_scheduler_call_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_loop_plan_executor_audit_projection(
    execution_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(execution_record)
    return {
        "projection": "controlled_loop_plan_executor_audit",
        "projection_only": True,
        "execution_record_id": record.get("execution_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_loop_plan_id": record.get("source_loop_plan_id"),
        "selected_tick_intent_id": record.get("selected_tick_intent_id"),
        "execution_status": record.get("execution_status", "BLOCKED"),
        "dispatch_allowed": record.get("dispatch_allowed") is True,
        "executor_called": False,
        "scheduler_called": False,
        "loop_continued": False,
        "blocked_reason": record.get("blocked_reason", "not_evaluated"),
        "one_tick_intent_only": True,
        "direct_executor_call_performed": False,
        "direct_scheduler_call_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_loop_plan_executor_audit_record(
    controlled_runtime_loop_plan: dict[str, Any] | None,
    *,
    selected_tick_intent_id: str | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_controlled_loop_plan_execution_record(
        controlled_runtime_loop_plan,
        selected_tick_intent_id=selected_tick_intent_id,
        authority=authority,
    )
    return {
        "audit_schema": CONTROLLED_LOOP_PLAN_EXECUTOR_SCHEMA + ".audit",
        "decision": "reserved_controlled_loop_plan_executor_one_tick_only",
        "controlled_loop_plan_execution_record": record,
        "audit_projection": build_controlled_loop_plan_executor_audit_projection(
            record
        ),
        "executor_called": False,
        "scheduler_called": False,
        "loop_continued": False,
        "direct_executor_call_performed": False,
        "direct_scheduler_call_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
    }


def build_controlled_loop_plan_executor_milestone_seal(
    controlled_runtime_loop_plan: dict[str, Any] | None,
    *,
    selected_tick_intent_id: str | None = None,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_controlled_loop_plan_executor_audit_record(
        controlled_runtime_loop_plan,
        selected_tick_intent_id=selected_tick_intent_id,
        authority=authority,
    )
    record = _as_mapping(audit.get("controlled_loop_plan_execution_record"))
    return {
        "seal": "controlled_loop_plan_executor_bundle",
        "schema": CONTROLLED_LOOP_PLAN_EXECUTOR_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_LOOP_PLAN_ONE_TICK_SELECTION_ONLY",
        "execution_record_id": record.get("execution_record_id"),
        "execution_status": record.get("execution_status"),
        "dispatch_allowed": record.get("dispatch_allowed") is True,
        "executor_called": False,
        "scheduler_called": False,
        "loop_continued": False,
        "one_tick_intent_only": True,
        "direct_executor_call_performed": False,
        "direct_scheduler_call_performed": False,
        "infinite_loop_allowed": False,
        "loop_executed": False,
        "thread_created": False,
        "daemon_started": False,
        "automatic_retry_performed": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "CONTROLLED_LOOP_PLAN_EXECUTOR_SCHEMA",
    "LOOP_PLAN_EXECUTION_STATUSES",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_controlled_loop_plan_execution_record",
    "build_controlled_loop_plan_executor_audit_projection",
    "build_controlled_loop_plan_executor_audit_record",
    "build_controlled_loop_plan_executor_milestone_seal",
]
