from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA = "zero.runtime.autonomous_cycle_binding.v1"


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


def adapt_worker_pickup_to_cycle_request(worker_pickup_record: Any) -> dict[str, Any]:
    pickup = _mapping(worker_pickup_record)
    lineage = _mapping(pickup.get("lineage"))
    goal_id = _text(pickup.get("goal_id"))
    work_package_id = _text(pickup.get("work_package_id"))
    runtime_session_id = _text(pickup.get("runtime_session_id"))
    queue_entry_id = _text(pickup.get("queue_entry_id"))
    claim_id = _text(pickup.get("worker_claim_id") or pickup.get("work_claim_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
    }

    if not pickup:
        denial = "missing_worker_pickup_record"
        created = False
    elif pickup.get("worker_pickup_admitted") is not True:
        denial = pickup.get("denial_reason") or "worker_pickup_not_claimed"
        created = False
    elif pickup.get("worker_pickup_status") != "claimed":
        denial = "worker_pickup_not_claimed"
        created = False
    elif not claim_id:
        denial = "missing_worker_claim_id"
        created = False
    elif not goal_id or not work_package_id or not runtime_session_id or not queue_entry_id:
        denial = "missing_cycle_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA + ".request",
        "cycle_request_created": created,
        "cycle_request_id": _stable_id(
            "runtime-cycle-request",
            goal_id,
            work_package_id,
            runtime_session_id,
            queue_entry_id,
            claim_id,
        )
        if created
        else "",
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": claim_id,
        "lineage": {
            "goal_id": goal_id,
            "work_package_id": work_package_id,
            "runtime_session_id": runtime_session_id,
            "queue_entry_id": queue_entry_id,
            "worker_claim_id": claim_id,
        },
        "cycle_status": "not_bound" if created else "denied",
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "loop_started": False,
    }


def evaluate_autonomous_cycle_admission(
    cycle_request: Any,
    *,
    existing_bindings: Any = None,
) -> dict[str, Any]:
    request = _mapping(cycle_request)
    existing = [_mapping(item) for item in _list(existing_bindings)]

    if not request:
        denial = "missing_cycle_request"
        admitted = False
    elif request.get("cycle_request_created") is not True:
        denial = request.get("denial_reason") or "cycle_request_not_created"
        admitted = False
    elif any(
        item.get("worker_claim_id") == request.get("worker_claim_id")
        or item.get("runtime_session_id") == request.get("runtime_session_id")
        for item in existing
    ):
        denial = "duplicate_cycle_binding"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA,
        "cycle_binding_admitted": admitted,
        "cycle_status": "bound" if admitted else "denied",
        "cycle_binding_id": _stable_id(
            "runtime-cycle-binding",
            request.get("cycle_request_id"),
            request.get("worker_claim_id"),
        )
        if admitted
        else "",
        "cycle_request_id": request.get("cycle_request_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "lineage": _mapping(request.get("lineage")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "loop_started": False,
    }


def bind_worker_pickup_to_cycle(
    worker_pickup_record: Any,
    *,
    existing_bindings: Any = None,
) -> dict[str, Any]:
    request = adapt_worker_pickup_to_cycle_request(worker_pickup_record)
    admission = evaluate_autonomous_cycle_admission(
        request,
        existing_bindings=existing_bindings,
    )
    bindings = [_mapping(item) for item in _list(existing_bindings)]
    if admission["cycle_binding_admitted"]:
        bindings.append(admission)

    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA + ".submit",
        "ok": admission["cycle_binding_admitted"],
        "cycle_request": request,
        "cycle_binding": admission,
        "cycle_status": admission["cycle_status"],
        "bound": admission["cycle_binding_admitted"],
        "bindings": bindings,
        "binding_count": len(bindings),
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "queue_entry_id": admission["queue_entry_id"],
        "worker_claim_id": admission["worker_claim_id"],
        "denial_reason": admission["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "loop_started": False,
    }


def build_cycle_context_state(cycle_bindings: Any) -> dict[str, Any]:
    bindings = [_mapping(item) for item in _list(cycle_bindings)]
    return {
        "schema": RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA + ".state",
        "cycle_status": "bound" if bindings else "not_bound",
        "bound_count": len(bindings),
        "bound_runtime_session_ids": [
            item.get("runtime_session_id") or "" for item in bindings
        ],
        "bindings": bindings,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
        "loop_started": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_CYCLE_BINDING_SCHEMA",
    "adapt_worker_pickup_to_cycle_request",
    "evaluate_autonomous_cycle_admission",
    "bind_worker_pickup_to_cycle",
    "build_cycle_context_state",
]
