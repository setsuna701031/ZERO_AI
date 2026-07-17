from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA = (
    "zero.runtime.autonomous_cycle_execution_bridge.v1"
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: str) -> str:
    joined = "|".join(_text(part) for part in parts)
    fragment = sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{fragment}"


def build_cycle_execution_request(cycle_binding_record: Any) -> dict[str, Any]:
    binding = _mapping(cycle_binding_record)
    lineage = _mapping(binding.get("lineage"))
    goal_id = _text(binding.get("goal_id"))
    work_package_id = _text(binding.get("work_package_id"))
    runtime_session_id = _text(binding.get("runtime_session_id"))
    queue_entry_id = _text(binding.get("queue_entry_id"))
    worker_claim_id = _text(binding.get("worker_claim_id"))
    cycle_binding_id = _text(binding.get("cycle_binding_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
    }

    if not binding:
        denial = "missing_cycle_binding"
        created = False
    elif binding.get("cycle_binding_admitted") is not True:
        denial = binding.get("denial_reason") or "cycle_binding_not_admitted"
        created = False
    elif binding.get("cycle_status") != "bound":
        denial = "cycle_not_bound"
        created = False
    elif not cycle_binding_id:
        denial = "missing_cycle_binding_id"
        created = False
    elif (
        not goal_id
        or not work_package_id
        or not runtime_session_id
        or not queue_entry_id
        or not worker_claim_id
    ):
        denial = "missing_execution_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    request_id = (
        _stable_id(
            "runtime-cycle-execution-request",
            goal_id,
            runtime_session_id,
            queue_entry_id,
            worker_claim_id,
            cycle_binding_id,
        )
        if created
        else ""
    )
    request_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
    }

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA + ".request",
        "execution_request_created": created,
        "execution_request_id": request_id,
        "execution_status": "not_ready" if created else "rejected",
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "lineage": request_lineage,
        "controlled_loop_input": {
            "prepared": created,
            "goal_id": goal_id,
            "runtime_session_id": runtime_session_id,
            "queue_entry_id": queue_entry_id,
            "worker_claim_id": worker_claim_id,
            "cycle_binding_id": cycle_binding_id,
            "execution_request_id": request_id,
            "loop_control": "controlled",
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


def evaluate_cycle_execution_admission(
    cycle_execution_request: Any,
    *,
    existing_requests: Any = None,
) -> dict[str, Any]:
    request = _mapping(cycle_execution_request)
    existing = [_mapping(item) for item in _list(existing_requests)]

    if not request:
        denial = "missing_execution_request"
        admitted = False
    elif request.get("execution_request_created") is not True:
        denial = request.get("denial_reason") or "execution_request_not_created"
        admitted = False
    elif any(
        item.get("cycle_binding_id") == request.get("cycle_binding_id")
        or item.get("runtime_session_id") == request.get("runtime_session_id")
        or item.get("execution_request_id") == request.get("execution_request_id")
        for item in existing
    ):
        denial = "duplicate_execution_request"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA,
        "execution_request_admitted": admitted,
        "execution_status": "ready" if admitted else "rejected",
        "execution_request_id": request.get("execution_request_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "lineage": _mapping(request.get("lineage")),
        "controlled_loop_input": _mapping(request.get("controlled_loop_input")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


def bridge_cycle_binding_to_execution_request(
    cycle_binding_record: Any,
    *,
    existing_requests: Any = None,
) -> dict[str, Any]:
    request = build_cycle_execution_request(cycle_binding_record)
    admission = evaluate_cycle_execution_admission(
        request,
        existing_requests=existing_requests,
    )
    requests = [_mapping(item) for item in _list(existing_requests)]
    if admission["execution_request_admitted"]:
        requests.append(admission)

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA + ".submit",
        "ok": admission["execution_request_admitted"],
        "cycle_execution_request": request,
        "execution_request": admission,
        "execution_status": admission["execution_status"],
        "execution_ready": admission["execution_request_admitted"],
        "execution_requests": requests,
        "execution_request_count": len(requests),
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "queue_entry_id": admission["queue_entry_id"],
        "worker_claim_id": admission["worker_claim_id"],
        "cycle_binding_id": admission["cycle_binding_id"],
        "denial_reason": admission["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


def build_execution_request_state(execution_requests: Any) -> dict[str, Any]:
    requests = [_mapping(item) for item in _list(execution_requests)]
    ready_requests = [
        item for item in requests if item.get("execution_status") == "ready"
    ]
    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA + ".state",
        "execution_status": "ready" if ready_requests else "not_ready",
        "ready_count": len(ready_requests),
        "request_count": len(requests),
        "ready_runtime_session_ids": [
            item.get("runtime_session_id") or "" for item in ready_requests
        ],
        "ready_cycle_binding_ids": [
            item.get("cycle_binding_id") or "" for item in ready_requests
        ],
        "requests": requests,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_CYCLE_EXECUTION_BRIDGE_SCHEMA",
    "build_cycle_execution_request",
    "evaluate_cycle_execution_admission",
    "bridge_cycle_binding_to_execution_request",
    "build_execution_request_state",
]
