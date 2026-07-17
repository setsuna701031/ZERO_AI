from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_QUEUE_WORKER_PICKUP_SCHEMA = "zero.runtime.queue_worker_pickup.v1"


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


def adapt_queue_entry_to_work_claim(queue_entry: Any) -> dict[str, Any]:
    entry = _mapping(queue_entry)
    lineage = _mapping(entry.get("lineage"))
    goal_id = _text(entry.get("goal_id"))
    work_package_id = _text(entry.get("work_package_id"))
    runtime_session_id = _text(entry.get("runtime_session_id"))
    queue_entry_id = _text(entry.get("queue_entry_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
    }

    if not entry:
        denial = "missing_queue_entry"
        created = False
    elif entry.get("queue_entry_created") is not True:
        denial = "queue_entry_not_admitted"
        created = False
    elif entry.get("queue_status") != "queued":
        denial = "queue_entry_not_queued"
        created = False
    elif not queue_entry_id:
        denial = "missing_queue_entry_id"
        created = False
    elif not goal_id or not work_package_id or not runtime_session_id:
        denial = "missing_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    return {
        "schema": RUNTIME_QUEUE_WORKER_PICKUP_SCHEMA + ".claim",
        "work_claim_created": created,
        "work_claim_id": _stable_id(
            "runtime-work-claim",
            goal_id,
            work_package_id,
            runtime_session_id,
            queue_entry_id,
        )
        if created
        else "",
        "queue_entry_id": queue_entry_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "lineage": {
            "goal_id": goal_id,
            "work_package_id": work_package_id,
            "runtime_session_id": runtime_session_id,
            "queue_entry_id": queue_entry_id,
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
    }


def evaluate_worker_pickup_admission(
    work_claim: Any,
    *,
    existing_claims: Any = None,
) -> dict[str, Any]:
    claim = _mapping(work_claim)
    existing = [_mapping(item) for item in _list(existing_claims)]

    if not claim:
        denial = "missing_work_claim"
        admitted = False
    elif claim.get("work_claim_created") is not True:
        denial = claim.get("denial_reason") or "work_claim_not_created"
        admitted = False
    elif any(
        item.get("queue_entry_id") == claim.get("queue_entry_id")
        or item.get("runtime_session_id") == claim.get("runtime_session_id")
        for item in existing
    ):
        denial = "duplicate_worker_claim"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_QUEUE_WORKER_PICKUP_SCHEMA,
        "worker_pickup_admitted": admitted,
        "worker_pickup_status": "claimed" if admitted else "denied",
        "work_claim_id": claim.get("work_claim_id") or "",
        "worker_claim_id": claim.get("work_claim_id") or "",
        "queue_entry_id": claim.get("queue_entry_id") or "",
        "goal_id": claim.get("goal_id") or "",
        "work_package_id": claim.get("work_package_id") or "",
        "runtime_session_id": claim.get("runtime_session_id") or "",
        "lineage": _mapping(claim.get("lineage")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
    }


def submit_queue_entry_for_worker_pickup(
    queue_entry: Any,
    *,
    existing_claims: Any = None,
) -> dict[str, Any]:
    claim = adapt_queue_entry_to_work_claim(queue_entry)
    admission = evaluate_worker_pickup_admission(claim, existing_claims=existing_claims)
    claims = [_mapping(item) for item in _list(existing_claims)]
    updated_entry = _mapping(queue_entry)
    if admission["worker_pickup_admitted"]:
        claims.append(claim)
        updated_entry["queue_status"] = "claimed"
        updated_entry["worker_pickup_status"] = "claimed"
        updated_entry["work_claim_id"] = claim["work_claim_id"]
        updated_entry["worker_claim_id"] = claim["work_claim_id"]

    return {
        "schema": RUNTIME_QUEUE_WORKER_PICKUP_SCHEMA + ".submit",
        "ok": admission["worker_pickup_admitted"],
        "worker_pickup_record": admission,
        "work_claim": claim,
        "queue_entry": updated_entry,
        "worker_pickup_status": admission["worker_pickup_status"],
        "claimed": admission["worker_pickup_admitted"],
        "claims": claims,
        "claim_count": len(claims),
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "queue_entry_id": admission["queue_entry_id"],
        "denial_reason": admission["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "cursor_mutated": False,
    }


__all__ = [
    "RUNTIME_QUEUE_WORKER_PICKUP_SCHEMA",
    "adapt_queue_entry_to_work_claim",
    "evaluate_worker_pickup_admission",
    "submit_queue_entry_for_worker_pickup",
]
