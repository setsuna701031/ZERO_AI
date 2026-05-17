from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def extract_effective_status_and_answer(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
) -> Tuple[str, Any]:
    candidates: List[Dict[str, Any]] = []

    if isinstance(runner_result, dict):
        candidates.append(runner_result)
    if isinstance(refreshed_task, dict):
        candidates.append(refreshed_task)
    if isinstance(original_task, dict):
        candidates.append(original_task)

    status = ""
    final_answer: Any = ""

    for source in candidates:
        source_status = str(source.get("status") or "").strip().lower()
        if source_status:
            status = source_status
            break

    for source in candidates:
        if "final_answer" in source:
            value = source.get("final_answer")
            if value not in (None, ""):
                final_answer = value
                break

    return status, final_answer


def _extract_dispatch_failure_error(
    runner_result: Optional[Dict[str, Any]],
    final_answer: Any = "",
    *,
    default: str = "task failed",
) -> str:
    result = runner_result if isinstance(runner_result, dict) else {}
    return str(result.get("error") or final_answer or default)


def _extract_dispatch_blocked_reason(
    runner_result: Optional[Dict[str, Any]],
    final_answer: Any = "",
) -> str:
    result = runner_result if isinstance(runner_result, dict) else {}
    return str(result.get("blocked_reason") or result.get("error") or final_answer or "")


def build_finalize_decision(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
    *,
    status_blocked: str,
    status_finished: str,
    status_failed: str,
) -> Dict[str, Any]:
    result = runner_result if isinstance(runner_result, dict) else {}
    effective_status, effective_final_answer = extract_effective_status_and_answer(
        original_task=original_task,
        refreshed_task=refreshed_task,
        runner_result=result,
    )

    status = str(effective_status or "").strip().lower()
    normalized_finished = str(status_finished or "").strip().lower()
    normalized_failed = str(status_failed or "").strip().lower()
    normalized_blocked = str(status_blocked or "").strip().lower()

    finished_statuses = {"done", "finished", normalized_finished, "success", "completed"}
    failed_statuses = {"failed", normalized_failed, "error"}
    queued_statuses = {"queued", "retry", "ready", "running"}
    blocked_statuses = {normalized_blocked} if normalized_blocked else set()

    action = "release"
    fail_error = ""
    blocked_reason = ""
    queue_error = _extract_dispatch_failure_error(
        result,
        "",
        default="",
    )

    if status in finished_statuses:
        action = "finish"
    elif status in failed_statuses:
        action = "fail"
        fail_error = _extract_dispatch_failure_error(
            result,
            effective_final_answer,
            default="task failed",
        )
    elif status in blocked_statuses:
        action = "block"
        blocked_reason = _extract_dispatch_blocked_reason(
            result,
            effective_final_answer,
        )
    elif status in queued_statuses:
        action = "requeue_if_ready"

    return {
        "action": action,
        "status": status,
        "final_answer": effective_final_answer,
        "fail_error": fail_error,
        "blocked_reason": blocked_reason,
        "queue_error": queue_error,
        "ok": bool(result.get("ok", True)),
    }


def apply_finalize_decision(
    scheduler: Any,
    *,
    task_id: str,
    scheduled_task: Any,
    decision: Dict[str, Any],
) -> None:
    action = decision.get("action")
    effective_final_answer = decision.get("final_answer")

    if action == "finish":
        scheduler.dispatcher.complete_task(task_id=task_id, result=effective_final_answer)
        scheduler._mark_repo_task_finished(task_id=task_id, result=effective_final_answer)
        return

    if action == "fail":
        fail_error = str(decision.get("fail_error") or "task failed")
        scheduler.dispatcher.fail_task(
            task_id=task_id,
            error=fail_error,
            requeue_on_retry=False,
        )
        scheduler._mark_repo_task_failed(task_id=task_id, error=fail_error)
        return

    if action == "block":
        scheduler.worker_pool.release_by_task(task_id)
        scheduler._sync_blocked_state(
            task_id=task_id,
            blocked_reason=str(decision.get("blocked_reason") or ""),
        )
        return

    if action == "requeue_if_ready":
        scheduler.worker_pool.release_by_task(task_id)
        if scheduler._can_requeue_task(task_id):
            scheduler.scheduler_queue.requeue(task_id=task_id, priority=scheduled_task.priority)
            scheduler._mark_repo_task_queued(
                task_id=task_id,
                error=str(decision.get("queue_error") or ""),
            )
        return

    scheduler.worker_pool.release_by_task(task_id)
