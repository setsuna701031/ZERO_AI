from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA = (
    "zero.runtime.controlled_loop_activation.v1"
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


def build_controlled_loop_tick_request(execution_request: Any) -> dict[str, Any]:
    request = _mapping(execution_request)
    lineage = _mapping(request.get("lineage"))
    goal_id = _text(request.get("goal_id"))
    work_package_id = _text(request.get("work_package_id"))
    runtime_session_id = _text(request.get("runtime_session_id"))
    queue_entry_id = _text(request.get("queue_entry_id"))
    worker_claim_id = _text(request.get("worker_claim_id"))
    cycle_binding_id = _text(request.get("cycle_binding_id"))
    execution_request_id = _text(request.get("execution_request_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
    }

    if not request:
        denial = "missing_execution_request"
        created = False
    elif request.get("execution_request_admitted") is not True:
        denial = request.get("denial_reason") or "execution_request_not_admitted"
        created = False
    elif request.get("execution_status") == "rejected":
        denial = "rejected_execution_request"
        created = False
    elif request.get("execution_status") != "ready":
        denial = "execution_request_not_ready"
        created = False
    elif not execution_request_id:
        denial = "missing_execution_request_id"
        created = False
    elif (
        not goal_id
        or not work_package_id
        or not runtime_session_id
        or not queue_entry_id
        or not worker_claim_id
        or not cycle_binding_id
    ):
        denial = "missing_tick_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    tick_id = (
        _stable_id(
            "runtime-controlled-loop-tick",
            goal_id,
            runtime_session_id,
            execution_request_id,
            "1",
        )
        if created
        else ""
    )
    tick_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
    }

    return {
        "schema": RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA + ".request",
        "tick_request_created": created,
        "tick_id": tick_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_status": "not_started" if created else "blocked",
        "loop_status": "not_started" if created else "blocked",
        "tick_number": 1 if created else 0,
        "lineage": tick_lineage,
        "autonomous_cycle_state": {
            "prepared": created,
            "tick_number": 1 if created else 0,
            "goal_id": goal_id,
            "runtime_session_id": runtime_session_id,
            "execution_request_id": execution_request_id,
            "cycle_binding_id": cycle_binding_id,
            "control": "controlled",
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


def evaluate_controlled_loop_tick_admission(
    tick_request: Any,
    *,
    existing_ticks: Any = None,
) -> dict[str, Any]:
    request = _mapping(tick_request)
    existing = [_mapping(item) for item in _list(existing_ticks)]

    if not request:
        denial = "missing_tick_request"
        admitted = False
    elif request.get("tick_request_created") is not True:
        denial = request.get("denial_reason") or "tick_request_not_created"
        admitted = False
    elif any(
        item.get("execution_request_id") == request.get("execution_request_id")
        or item.get("runtime_session_id") == request.get("runtime_session_id")
        or item.get("tick_id") == request.get("tick_id")
        for item in existing
    ):
        denial = "duplicate_tick"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA,
        "tick_admitted": admitted,
        "tick_id": request.get("tick_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_status": "tick_created" if admitted else "blocked",
        "loop_status": "tick_created" if admitted else "blocked",
        "tick_number": int(request.get("tick_number") or 0),
        "lineage": _mapping(request.get("lineage")),
        "autonomous_cycle_state": _mapping(request.get("autonomous_cycle_state")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


def activate_controlled_loop_tick(
    execution_request: Any,
    *,
    existing_ticks: Any = None,
) -> dict[str, Any]:
    tick_request = build_controlled_loop_tick_request(execution_request)
    record = evaluate_controlled_loop_tick_admission(
        tick_request,
        existing_ticks=existing_ticks,
    )
    ticks = [_mapping(item) for item in _list(existing_ticks)]
    if record["tick_admitted"]:
        ticks.append(record)

    return {
        "schema": RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA + ".submit",
        "ok": record["tick_admitted"],
        "tick_request": tick_request,
        "controlled_loop_tick": record,
        "tick_status": record["tick_status"],
        "loop_status": record["loop_status"],
        "tick_created": record["tick_admitted"],
        "ticks": ticks,
        "tick_count": len(ticks),
        "tick_id": record["tick_id"],
        "goal_id": record["goal_id"],
        "work_package_id": record["work_package_id"],
        "runtime_session_id": record["runtime_session_id"],
        "queue_entry_id": record["queue_entry_id"],
        "worker_claim_id": record["worker_claim_id"],
        "cycle_binding_id": record["cycle_binding_id"],
        "execution_request_id": record["execution_request_id"],
        "denial_reason": record["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


def build_controlled_loop_state(controlled_loop_ticks: Any) -> dict[str, Any]:
    ticks = [_mapping(item) for item in _list(controlled_loop_ticks)]
    created_ticks = [item for item in ticks if item.get("tick_status") == "tick_created"]
    return {
        "schema": RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA + ".state",
        "loop_status": "tick_created" if created_ticks else "not_started",
        "tick_status": "tick_created" if created_ticks else "not_started",
        "tick_count": len(ticks),
        "created_count": len(created_ticks),
        "created_runtime_session_ids": [
            item.get("runtime_session_id") or "" for item in created_ticks
        ],
        "created_execution_request_ids": [
            item.get("execution_request_id") or "" for item in created_ticks
        ],
        "ticks": ticks,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "loop_started": False,
        "progress_memory_written": False,
    }


__all__ = [
    "RUNTIME_CONTROLLED_LOOP_ACTIVATION_SCHEMA",
    "build_controlled_loop_tick_request",
    "evaluate_controlled_loop_tick_admission",
    "activate_controlled_loop_tick",
    "build_controlled_loop_state",
]
