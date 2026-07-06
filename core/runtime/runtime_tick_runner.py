from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_TICK_RUNNER_SCHEMA = "zero.runtime.tick_runner.v1"

RUNTIME_TICK_STATUSES = (
    "ALLOW_SINGLE_TICK",
    "ENTER_RECOVERY_GATE",
    "PAUSED",
    "CLOSED",
    "STOPPED",
    "BLOCKED",
)

CYCLE_ACTION_TO_TICK_STATUS = {
    "REQUEST_NEXT_TICK": "ALLOW_SINGLE_TICK",
    "REQUEST_RECOVERY_FLOW": "ENTER_RECOVERY_GATE",
    "PAUSE_RUNTIME": "PAUSED",
    "CLOSE_RUNTIME": "CLOSED",
    "STOP_RUNTIME": "STOPPED",
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _tick_id(
    *,
    runtime_id: str | None,
    cycle_id: str | None,
    requested_action: str | None,
    tick_status: str,
    dispatched: bool,
    completed: bool,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "cycle_id": cycle_id,
            "requested_action": requested_action,
            "tick_status": tick_status,
            "dispatched": dispatched,
            "completed": completed,
            "blocked_reason": blocked_reason,
        }
    )
    return f"runtime-tick-result::{runtime_id or 'missing-runtime'}::{fragment}"


def _evaluate_cycle_request(cycle_request: dict[str, Any]) -> tuple[str, bool, bool, str]:
    if not cycle_request:
        return "BLOCKED", False, False, "missing_cycle_request"
    if not cycle_request.get("cycle_id"):
        return "BLOCKED", False, False, "missing_cycle_id"
    if cycle_request.get("authorization_required") is not True:
        return "BLOCKED", False, False, "cycle_request_missing_authorization_requirement"

    requested_action = cycle_request.get("requested_action")
    tick_status = CYCLE_ACTION_TO_TICK_STATUS.get(str(requested_action))
    if tick_status is None:
        return "BLOCKED", False, False, "unsupported_cycle_action"

    dispatched = tick_status == "ALLOW_SINGLE_TICK"
    completed = tick_status in {"CLOSED", "STOPPED"}
    return tick_status, dispatched, completed, "none"


def build_runtime_tick_result(
    runtime_cycle_request: dict[str, Any] | None,
) -> dict[str, Any]:
    request = _as_mapping(runtime_cycle_request)
    tick_status, dispatched, completed, blocked_reason = _evaluate_cycle_request(
        request
    )
    tick_id = _tick_id(
        runtime_id=request.get("runtime_id"),
        cycle_id=request.get("cycle_id"),
        requested_action=request.get("requested_action"),
        tick_status=tick_status,
        dispatched=dispatched,
        completed=completed,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": RUNTIME_TICK_RUNNER_SCHEMA,
        "tick_id": tick_id,
        "runtime_id": request.get("runtime_id"),
        "source_cycle_id": request.get("cycle_id"),
        "tick_status": tick_status,
        "requested_action": request.get("requested_action"),
        "dispatched": dispatched,
        "completed": completed,
        "blocked_reason": blocked_reason,
        "single_tick_only": True,
        "dispatch_intent_only": dispatched,
        "executor_called": False,
        "executor_run_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "controller_bypassed": False,
        "loop_started": False,
        "background_thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_daemon_started": False,
    }


def build_runtime_tick_runner_audit_projection(
    runtime_tick_result: dict[str, Any] | None,
) -> dict[str, Any]:
    result = _as_mapping(runtime_tick_result)
    return {
        "projection": "runtime_tick_runner_audit",
        "projection_only": True,
        "tick_id": result.get("tick_id"),
        "runtime_id": result.get("runtime_id"),
        "source_cycle_id": result.get("source_cycle_id"),
        "tick_status": result.get("tick_status"),
        "requested_action": result.get("requested_action"),
        "dispatched": result.get("dispatched") is True,
        "completed": result.get("completed") is True,
        "blocked_reason": result.get("blocked_reason", "not_evaluated"),
        "single_tick_only": True,
        "dispatch_intent_only": result.get("dispatch_intent_only") is True,
        "executor_called": False,
        "executor_run_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "controller_bypassed": False,
        "loop_started": False,
        "background_thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_daemon_started": False,
    }


def build_runtime_tick_runner_audit_record(
    runtime_cycle_request: dict[str, Any] | None,
) -> dict[str, Any]:
    result = build_runtime_tick_result(runtime_cycle_request)
    return {
        "audit_schema": RUNTIME_TICK_RUNNER_SCHEMA + ".audit",
        "decision": "reserved_runtime_tick_runner_single_tick_only",
        "runtime_tick_result": result,
        "audit_projection": build_runtime_tick_runner_audit_projection(result),
        "executor_called": False,
        "executor_run_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "controller_bypassed": False,
        "loop_started": False,
        "background_thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_daemon_started": False,
    }


def build_runtime_tick_runner_milestone_seal(
    runtime_cycle_request: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_runtime_tick_runner_audit_record(runtime_cycle_request)
    result = _as_mapping(audit.get("runtime_tick_result"))
    return {
        "seal": "runtime_tick_runner_bundle",
        "schema": RUNTIME_TICK_RUNNER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_BOUNDED_RUNTIME_TICK_RESULTS_ONLY",
        "tick_id": result.get("tick_id"),
        "source_cycle_id": result.get("source_cycle_id"),
        "tick_status": result.get("tick_status"),
        "single_tick_only": True,
        "dispatch_intent_only": result.get("dispatch_intent_only") is True,
        "executor_called": False,
        "executor_run_performed": False,
        "scheduler_imported": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "controller_bypassed": False,
        "loop_started": False,
        "background_thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_daemon_started": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_TICK_RUNNER_SCHEMA",
    "RUNTIME_TICK_STATUSES",
    "CYCLE_ACTION_TO_TICK_STATUS",
    "build_runtime_tick_result",
    "build_runtime_tick_runner_audit_projection",
    "build_runtime_tick_runner_audit_record",
    "build_runtime_tick_runner_milestone_seal",
]
