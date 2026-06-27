from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.task_runtime import project_runtime_status


def _is_successful_nonblocking_step_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    if value.get("ok") is not True:
        return False

    if bool(value.get("blocked", False)):
        return False

    if bool(value.get("failed", False)):
        return False

    error_type = str(value.get("error_type") or "").strip()
    error_text = str(value.get("error") or value.get("last_error") or "").strip()
    if error_type or error_text:
        return False

    return True


def _has_remaining_steps(payload: Dict[str, Any]) -> bool:
    try:
        current_step_index = int(payload.get("current_step_index", 0) or 0)
    except Exception:
        current_step_index = 0

    try:
        steps_total = int(payload.get("steps_total", 0) or 0)
    except Exception:
        steps_total = 0

    steps = payload.get("steps")
    if steps_total <= 0 and isinstance(steps, list):
        steps_total = len(steps)

    return steps_total > 0 and current_step_index < steps_total


def _advisory_transition_reason(reason: Any) -> bool:
    text = str(reason or "").strip().lower()
    if not text:
        return True

    advisory_tokens = (
        "allowed transition observed",
        "hard enforcement not enabled",
        "observe_only",
        "observe only",
    )
    return any(token in text for token in advisory_tokens)


def _should_downgrade_advisory_blocked_status(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    status = str(payload.get("status") or "").strip().lower()
    if status != "blocked":
        return False

    blocked_reason = str(payload.get("blocked_reason") or "").strip()
    last_error = str(payload.get("last_error") or payload.get("failure_message") or "").strip()

    blockers = payload.get("blockers")
    active_blocker_count = int(payload.get("active_blocker_count", 0) or 0)
    has_structured_blockers = (
        (isinstance(blockers, list) and bool(blockers))
        or active_blocker_count > 0
    )
    if has_structured_blockers:
        return False

    if last_error:
        return False

    last_step_result = payload.get("last_step_result")
    if last_step_result is None and isinstance(payload.get("step_results"), list) and payload["step_results"]:
        try:
            last_step_result = payload["step_results"][-1]
        except Exception:
            last_step_result = None

    if not _is_successful_nonblocking_step_result(last_step_result):
        return False

    if not _has_remaining_steps(payload):
        return False

    return _advisory_transition_reason(blocked_reason)


def _downgrade_advisory_blocked_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    if not _should_downgrade_advisory_blocked_status(payload):
        return payload

    downgraded = copy.deepcopy(payload)
    downgraded["status"] = "queued"
    downgraded["blocked_reason"] = ""
    downgraded["waiting_reason"] = ""
    downgraded["terminal_reason"] = ""
    downgraded["next_action"] = ""
    downgraded["agent_action"] = ""
    downgraded["active_blocker_count"] = 0
    downgraded["blockers"] = []
    downgraded["last_error"] = ""
    downgraded["failure_message"] = ""
    downgraded["history"] = _append_status_to_history(
        downgraded.get("history"),
        "queued",
    )
    downgraded["advisory_blocked_status_downgraded"] = True
    downgraded["advisory_blocked_status_reason"] = "successful step with remaining work cannot be blocked by observe-only transition evidence"
    return downgraded


def _append_status_to_history(history: Any, status: str) -> List[Any]:
    entries = copy.deepcopy(history) if isinstance(history, list) else []
    if not entries or str(entries[-1] or "").strip().lower() != str(status or "").strip().lower():
        entries.append(status)
    return entries


def sync_blocked_state(scheduler: Any, task_id: str, blocked_reason: str) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    final_reason = str(blocked_reason or task.get("blocked_reason") or "").strip()

    if _should_downgrade_advisory_blocked_status(
        {
            **copy.deepcopy(task),
            "status": "blocked",
            "blocked_reason": final_reason,
        }
    ):
        task = _downgrade_advisory_blocked_status(
            {
                **copy.deepcopy(task),
                "status": "blocked",
                "blocked_reason": final_reason,
            }
        )
        scheduler._persist_task_payload(task_id=task_id, task=task)
        trace = scheduler._load_trace_for_task(task)
        scheduler._trace_status(
            trace=trace,
            task=task,
            status="queued",
            tick=getattr(scheduler, "current_tick", 0),
            final_answer=str(task.get("final_answer") or ""),
            extra={
                "action": "downgrade_advisory_blocked_state",
                "blocked_reason": final_reason,
            },
        )
        scheduler._save_trace_for_task(task=task, trace=trace)
        scheduler.worker_pool.release_by_task(task_id)
        return

    changed = False

    if current_status != scheduler.STATUS_BLOCKED:
        project_runtime_status(task, scheduler.STATUS_BLOCKED, owner="core/tasks/scheduler_core/repo_blocked_state.py")
        task["history"] = scheduler._append_history(task.get("history"), scheduler.STATUS_BLOCKED)
        changed = True

    if str(task.get("blocked_reason") or "") != final_reason:
        task["blocked_reason"] = final_reason
        changed = True

    if str(task.get("last_error") or "") != "":
        task["last_error"] = ""
        changed = True

    if str(task.get("failure_message") or "") != "":
        task["failure_message"] = ""
        changed = True

    build = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")
    if str(task.get("scheduler_build") or "") != build:
        task["scheduler_build"] = build
        changed = True

    sync_fn = getattr(scheduler, "_sync_blocked_state", None)
    if callable(sync_fn):
        sync_fn(task_id=task_id, blocked_reason=final_reason)

    if changed:
        scheduler._persist_task_payload(task_id=task_id, task=task)

    trace = scheduler._load_trace_for_task(task)
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=scheduler.STATUS_BLOCKED,
        tick=getattr(scheduler, "current_tick", 0),
        final_answer="",
        extra={
            "action": "sync_blocked_state",
            "blocked_reason": final_reason,
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    scheduler.worker_pool.release_by_task(task_id)


def sync_unblocked_state(scheduler: Any, task_id: str) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    changed = False

    if current_status == scheduler.STATUS_BLOCKED:
        project_runtime_status(task, "queued", owner="core/tasks/scheduler_core/repo_blocked_state.py")
        task["history"] = scheduler._append_history(task.get("history"), "queued")
        current_status = "queued"
        changed = True

    if str(task.get("blocked_reason") or "") != "":
        task["blocked_reason"] = ""
        changed = True

    if current_status in {"queued", "ready", "retry", scheduler.STATUS_QUEUED}:
        if str(task.get("last_error") or "") != "":
            task["last_error"] = ""
            changed = True
        if str(task.get("failure_message") or "") != "":
            task["failure_message"] = ""
            changed = True

    build = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")
    if str(task.get("scheduler_build") or "") != build:
        task["scheduler_build"] = build
        changed = True

    if changed:
        scheduler._persist_task_payload(task_id=task_id, task=task)
