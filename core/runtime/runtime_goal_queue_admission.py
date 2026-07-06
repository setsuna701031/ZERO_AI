from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA = "zero.runtime.goal_queue_admission.v1"


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


def build_session_queue_entry(launch_result: Any) -> dict[str, Any]:
    launch = _mapping(launch_result)
    goal_id = _text(launch.get("goal_id"))
    work_package_id = _text(launch.get("work_package_id"))
    runtime_session_id = _text(launch.get("runtime_session_id"))

    if not launch:
        denial = "missing_launch_result"
        created = False
    elif launch.get("launch_admitted") is not True:
        denial = launch.get("denial_reason") or "launch_not_admitted"
        created = False
    elif not runtime_session_id:
        denial = "missing_runtime_session_id"
        created = False
    elif not work_package_id:
        denial = "missing_work_package_id"
        created = False
    elif not goal_id:
        denial = "missing_goal_id"
        created = False
    else:
        denial = ""
        created = True

    queue_entry_id = (
        _stable_id("runtime-queue-entry", goal_id, work_package_id, runtime_session_id)
        if created
        else ""
    )
    return {
        "schema": RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA + ".entry",
        "queue_entry_created": created,
        "queue_entry_id": queue_entry_id,
        "queue_status": "queued" if created else "denied",
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "lineage": {
            "goal_id": goal_id,
            "work_package_id": work_package_id,
            "runtime_session_id": runtime_session_id,
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def evaluate_goal_queue_admission(
    queue_entry: Any,
    *,
    existing_queue: Any = None,
) -> dict[str, Any]:
    entry = _mapping(queue_entry)
    existing = [_mapping(item) for item in _list(existing_queue)]

    if not entry:
        denial = "missing_queue_entry"
        admitted = False
    elif entry.get("queue_entry_created") is not True:
        denial = entry.get("denial_reason") or "queue_entry_not_created"
        admitted = False
    elif any(
        item.get("runtime_session_id") == entry.get("runtime_session_id")
        or item.get("queue_entry_id") == entry.get("queue_entry_id")
        for item in existing
    ):
        denial = "duplicate_runtime_session"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA,
        "queue_admitted": admitted,
        "queue_entry_id": entry.get("queue_entry_id") or "",
        "queue_status": "queued" if admitted else "denied",
        "goal_id": entry.get("goal_id") or "",
        "work_package_id": entry.get("work_package_id") or "",
        "runtime_session_id": entry.get("runtime_session_id") or "",
        "lineage": _mapping(entry.get("lineage")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def submit_goal_session_to_queue(
    launch_result: Any,
    *,
    existing_queue: Any = None,
) -> dict[str, Any]:
    entry = build_session_queue_entry(launch_result)
    admission = evaluate_goal_queue_admission(entry, existing_queue=existing_queue)
    queue = [_mapping(item) for item in _list(existing_queue)]
    if admission["queue_admitted"]:
        queue.append(entry)

    return {
        "schema": RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA + ".submit",
        "ok": admission["queue_admitted"],
        "queue_entry": entry,
        "queue_admission": admission,
        "queue_status": admission["queue_status"],
        "queued": admission["queue_admitted"],
        "queue_depth": len(queue),
        "queue_entries": queue,
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "denial_reason": admission["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def build_queue_state(queue_entries: Any) -> dict[str, Any]:
    entries = [_mapping(item) for item in _list(queue_entries)]
    return {
        "schema": RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA + ".state",
        "queue_depth": len(entries),
        "claimed_count": len(
            [item for item in entries if item.get("queue_status") == "claimed"]
        ),
        "queued_runtime_session_ids": [
            item.get("runtime_session_id") or "" for item in entries
        ],
        "queued_work_package_ids": [
            item.get("work_package_id") or "" for item in entries
        ],
        "claimed_runtime_session_ids": [
            item.get("runtime_session_id") or ""
            for item in entries
            if item.get("queue_status") == "claimed"
        ],
        "entries": entries,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


__all__ = [
    "RUNTIME_GOAL_QUEUE_ADMISSION_SCHEMA",
    "build_session_queue_entry",
    "evaluate_goal_queue_admission",
    "submit_goal_session_to_queue",
    "build_queue_state",
]
