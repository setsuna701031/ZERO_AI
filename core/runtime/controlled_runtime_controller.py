from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


CONTROLLED_RUNTIME_CONTROLLER_SCHEMA = "zero.runtime.controlled_runtime_controller.v1"

CONTROLLED_RUNTIME_ACTIONS = (
    "REQUEST_NEXT_TICK",
    "REQUEST_RECOVERY_FLOW",
    "PAUSE_RUNTIME",
    "CLOSE_RUNTIME",
    "STOP_RUNTIME",
)

RESUME_ACTION_TO_CYCLE_ACTION = {
    "CONTINUE_EXECUTION": "REQUEST_NEXT_TICK",
    "ENTER_RECOVERY": "REQUEST_RECOVERY_FLOW",
    "WAIT_FOR_INPUT": "PAUSE_RUNTIME",
    "MARK_COMPLETE": "CLOSE_RUNTIME",
    "BLOCKED": "STOP_RUNTIME",
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _cycle_id(
    *,
    runtime_id: str | None,
    decision_id: str | None,
    requested_action: str,
    next_step_reference: dict[str, Any],
    authorization_required: bool,
    execution_requested: bool,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "decision_id": decision_id,
            "requested_action": requested_action,
            "next_step_reference": next_step_reference,
            "authorization_required": authorization_required,
            "execution_requested": execution_requested,
        }
    )
    return f"runtime-cycle-request::{runtime_id or 'missing-runtime'}::{fragment}"


def _requested_action(resume_action: str | None) -> str:
    return RESUME_ACTION_TO_CYCLE_ACTION.get(str(resume_action), "PAUSE_RUNTIME")


def build_runtime_cycle_request(
    runtime_resume_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    decision = _as_mapping(runtime_resume_decision)
    requested_action = _requested_action(decision.get("action"))
    next_step_reference = _as_mapping(decision.get("next_step"))
    authorization_required = True
    execution_requested = requested_action == "REQUEST_NEXT_TICK"
    cycle_id = _cycle_id(
        runtime_id=decision.get("runtime_id"),
        decision_id=decision.get("decision_id"),
        requested_action=requested_action,
        next_step_reference=next_step_reference,
        authorization_required=authorization_required,
        execution_requested=execution_requested,
    )

    return {
        "schema": CONTROLLED_RUNTIME_CONTROLLER_SCHEMA,
        "cycle_id": cycle_id,
        "runtime_id": decision.get("runtime_id"),
        "source_decision_id": decision.get("decision_id"),
        "requested_action": requested_action,
        "next_step_reference": next_step_reference,
        "authorization_required": authorization_required,
        "execution_requested": execution_requested,
        "record_only": True,
        "cycle_request_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "while_loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def build_controlled_runtime_controller_audit_projection(
    runtime_cycle_request: dict[str, Any] | None,
) -> dict[str, Any]:
    request = _as_mapping(runtime_cycle_request)
    return {
        "projection": "controlled_runtime_controller_audit",
        "projection_only": True,
        "cycle_id": request.get("cycle_id"),
        "runtime_id": request.get("runtime_id"),
        "source_decision_id": request.get("source_decision_id"),
        "requested_action": request.get("requested_action"),
        "next_step_reference": _as_mapping(request.get("next_step_reference")),
        "authorization_required": request.get("authorization_required") is True,
        "execution_requested": request.get("execution_requested") is True,
        "cycle_request_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "while_loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def build_controlled_runtime_controller_audit_record(
    runtime_resume_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    request = build_runtime_cycle_request(runtime_resume_decision)
    return {
        "audit_schema": CONTROLLED_RUNTIME_CONTROLLER_SCHEMA + ".audit",
        "decision": "reserved_controlled_runtime_controller_cycle_request_only",
        "runtime_cycle_request": request,
        "audit_projection": build_controlled_runtime_controller_audit_projection(
            request
        ),
        "step_executed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "while_loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def build_controlled_runtime_controller_milestone_seal(
    runtime_resume_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_controlled_runtime_controller_audit_record(
        runtime_resume_decision
    )
    request = _as_mapping(audit.get("runtime_cycle_request"))
    return {
        "seal": "controlled_runtime_controller_bundle",
        "schema": CONTROLLED_RUNTIME_CONTROLLER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_RUNTIME_CYCLE_REQUESTS_ONLY",
        "cycle_id": request.get("cycle_id"),
        "requested_action": request.get("requested_action"),
        "authorization_required": request.get("authorization_required") is True,
        "execution_requested": request.get("execution_requested") is True,
        "cycle_request_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "progress_memory_mutated": False,
        "while_loop_started": False,
        "thread_created": False,
        "automatic_retry_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "CONTROLLED_RUNTIME_CONTROLLER_SCHEMA",
    "CONTROLLED_RUNTIME_ACTIONS",
    "RESUME_ACTION_TO_CYCLE_ACTION",
    "build_runtime_cycle_request",
    "build_controlled_runtime_controller_audit_projection",
    "build_controlled_runtime_controller_audit_record",
    "build_controlled_runtime_controller_milestone_seal",
]
