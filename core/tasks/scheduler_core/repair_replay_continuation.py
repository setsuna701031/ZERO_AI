from __future__ import annotations

import copy
from typing import Any, Callable, Dict

from core.tasks.scheduler_core.retrying_repair_replay_state import replay_enqueue_decision


PersistTaskPayload = Callable[..., Any]


def normalize_queued_repair_continuation(task: Dict[str, Any]) -> Dict[str, Any]:
    task.update(
        {
            "status": "queued",
            "next_action": "run_next_tick",
        }
    )
    return task


def package_already_injected_continuation(
    *,
    task: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "action": "repair_steps_already_injected",
        "status": "queued",
        "task_id": task_id,
        "task": copy.deepcopy(task),
    }


def build_already_injected_replay_continuation(
    *,
    task: Dict[str, Any],
    task_id: str,
    already_injected: Dict[str, Any],
    persist_task_payload: PersistTaskPayload,
) -> Dict[str, Any]:
    normalize_queued_repair_continuation(task)
    persist_task_payload(task_id=task_id, task=task)
    enqueue_decision = replay_enqueue_decision(str(already_injected.get("action") or ""))
    return {
        "result": package_already_injected_continuation(task=task, task_id=task_id),
        "enqueue_decision": enqueue_decision,
        "enqueue_task": task,
    }


def build_injected_replay_continuation(transaction: Dict[str, Any]) -> Dict[str, Any]:
    result = transaction.get("result") if isinstance(transaction, dict) else None
    if not isinstance(result, dict):
        result = {}

    enqueue_action = str(transaction.get("enqueue_action") or "") if isinstance(transaction, dict) else ""
    enqueue_decision = replay_enqueue_decision(enqueue_action)
    enqueue_task = result.get("task") if isinstance(result.get("task"), dict) else None
    return {
        "result": result,
        "enqueue_decision": enqueue_decision,
        "enqueue_task": enqueue_task,
    }
