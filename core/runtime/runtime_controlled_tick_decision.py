from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA = "zero.runtime.controlled_tick_decision.v1"


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


def build_controlled_tick_decision_request(
    controlled_loop_tick: Any,
) -> dict[str, Any]:
    tick = _mapping(controlled_loop_tick)
    lineage = _mapping(tick.get("lineage"))
    goal_id = _text(tick.get("goal_id"))
    work_package_id = _text(tick.get("work_package_id"))
    runtime_session_id = _text(tick.get("runtime_session_id"))
    queue_entry_id = _text(tick.get("queue_entry_id"))
    worker_claim_id = _text(tick.get("worker_claim_id"))
    cycle_binding_id = _text(tick.get("cycle_binding_id"))
    execution_request_id = _text(tick.get("execution_request_id"))
    tick_id = _text(tick.get("tick_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
    }

    if not tick:
        denial = "missing_controlled_loop_tick"
        created = False
    elif tick.get("tick_admitted") is not True:
        denial = tick.get("denial_reason") or "controlled_loop_tick_not_admitted"
        created = False
    elif tick.get("tick_status") != "tick_created":
        denial = "controlled_loop_tick_not_created"
        created = False
    elif tick.get("loop_status") != "tick_created":
        denial = "controlled_loop_not_created"
        created = False
    elif not tick_id:
        denial = "missing_tick_id"
        created = False
    elif (
        not goal_id
        or not work_package_id
        or not runtime_session_id
        or not queue_entry_id
        or not worker_claim_id
        or not cycle_binding_id
        or not execution_request_id
    ):
        denial = "missing_decision_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    decision_id = (
        _stable_id(
            "runtime-controlled-tick-decision",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
        )
        if created
        else ""
    )
    decision_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
    }

    return {
        "schema": RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA + ".request",
        "decision_request_created": created,
        "decision_id": decision_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_status": "not_ready" if created else "rejected",
        "lineage": decision_lineage,
        "reason": "controlled_tick_ready_for_decision" if created else denial,
        "state_metadata": {
            "tick_status": tick.get("tick_status") or "",
            "loop_status": tick.get("loop_status") or "",
            "tick_number": int(tick.get("tick_number") or 0),
            "record_only": True,
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def evaluate_controlled_tick_decision_admission(
    decision_request: Any,
    *,
    existing_decisions: Any = None,
) -> dict[str, Any]:
    request = _mapping(decision_request)
    existing = [_mapping(item) for item in _list(existing_decisions)]

    if not request:
        denial = "missing_decision_request"
        admitted = False
    elif request.get("decision_request_created") is not True:
        denial = request.get("denial_reason") or "decision_request_not_created"
        admitted = False
    elif any(
        item.get("tick_id") == request.get("tick_id")
        or item.get("execution_request_id") == request.get("execution_request_id")
        or item.get("decision_id") == request.get("decision_id")
        for item in existing
    ):
        denial = "duplicate_tick_decision"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA,
        "decision_admitted": admitted,
        "decision_id": request.get("decision_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_id": request.get("tick_id") or "",
        "decision_status": "decision_ready" if admitted else "rejected",
        "lineage": _mapping(request.get("lineage")),
        "reason": "controlled_tick_decision_ready" if admitted else denial,
        "state_metadata": _mapping(request.get("state_metadata")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def decide_controlled_tick(
    controlled_loop_tick: Any,
    *,
    existing_decisions: Any = None,
) -> dict[str, Any]:
    decision_request = build_controlled_tick_decision_request(controlled_loop_tick)
    decision = evaluate_controlled_tick_decision_admission(
        decision_request,
        existing_decisions=existing_decisions,
    )
    decisions = [_mapping(item) for item in _list(existing_decisions)]
    if decision["decision_admitted"]:
        decisions.append(decision)

    return {
        "schema": RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA + ".submit",
        "ok": decision["decision_admitted"],
        "decision_request": decision_request,
        "controlled_tick_decision": decision,
        "decision_status": decision["decision_status"],
        "decision_ready": decision["decision_admitted"],
        "decisions": decisions,
        "decision_count": len(decisions),
        "decision_id": decision["decision_id"],
        "goal_id": decision["goal_id"],
        "work_package_id": decision["work_package_id"],
        "runtime_session_id": decision["runtime_session_id"],
        "queue_entry_id": decision["queue_entry_id"],
        "worker_claim_id": decision["worker_claim_id"],
        "cycle_binding_id": decision["cycle_binding_id"],
        "execution_request_id": decision["execution_request_id"],
        "tick_id": decision["tick_id"],
        "reason": decision["reason"],
        "state_metadata": decision["state_metadata"],
        "denial_reason": decision["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def build_controlled_tick_decision_state(decisions: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(decisions)]
    ready = [item for item in records if item.get("decision_status") == "decision_ready"]
    return {
        "schema": RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA + ".state",
        "decision_status": "decision_ready" if ready else "not_ready",
        "ready_count": len(ready),
        "decision_count": len(records),
        "ready_tick_ids": [item.get("tick_id") or "" for item in ready],
        "ready_execution_request_ids": [
            item.get("execution_request_id") or "" for item in ready
        ],
        "decisions": records,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


__all__ = [
    "RUNTIME_CONTROLLED_TICK_DECISION_SCHEMA",
    "build_controlled_tick_decision_request",
    "evaluate_controlled_tick_decision_admission",
    "decide_controlled_tick",
    "build_controlled_tick_decision_state",
]
