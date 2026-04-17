from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


def rebuild_ready_queue(
    scheduler: Any,
    terminal_statuses: Set[str],
) -> List[str]:
    tasks = scheduler._list_repo_tasks()
    if not isinstance(tasks, list):
        return []

    synced_ids: List[str] = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        task = scheduler._hydrate_task_from_workspace(task)
        task_id = scheduler._extract_task_id(task)
        if not task_id:
            continue

        status = str(task.get("status") or "").strip().lower()
        if status in terminal_statuses:
            scheduler.worker_pool.release_by_task(task_id)
            continue

        if scheduler._enqueue_repo_task_if_ready(task):
            synced_ids.append(task_id)

    return synced_ids


def enqueue_repo_task_if_ready(
    scheduler: Any,
    task: Dict[str, Any],
    overwrite: bool,
    terminal_statuses: Set[str],
    ready_statuses: Set[str],
    status_blocked: str,
) -> bool:
    task = scheduler._hydrate_task_from_workspace(task)

    task_id = scheduler._extract_task_id(task)
    if not task_id:
        return False

    if scheduler.worker_pool.get_running_task(task_id) is not None:
        return False

    status = str(task.get("status") or "").strip().lower()
    if status in terminal_statuses:
        return False

    if scheduler._queue_contains_task(task_id) and not overwrite:
        return False

    deps_ready, blocked_reason = scheduler._task_dependencies_satisfied(task)
    if not deps_ready:
        scheduler._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)
        return False

    if status == status_blocked or str(task.get("blocked_reason") or "").strip():
        scheduler._sync_unblocked_state(task_id=task_id)

    refreshed_task = scheduler._get_task_from_repo(task_id)
    if isinstance(refreshed_task, dict):
        task = refreshed_task

    status = str(task.get("status") or "").strip().lower()
    if status not in ready_statuses:
        return False

    scheduled_task = scheduler._repo_task_to_scheduled_task(task)
    return scheduler.scheduler_queue.enqueue(scheduled_task, overwrite=overwrite)


def task_dependencies_satisfied(
    scheduler: Any,
    task: Dict[str, Any],
) -> Tuple[bool, str]:
    task = scheduler._hydrate_task_from_workspace(task)
    depends_on = task.get("depends_on", [])

    if depends_on is None:
        return True, ""

    if not isinstance(depends_on, list):
        return False, "invalid depends_on"

    normalized_deps = scheduler._normalize_depends_on(depends_on)
    if isinstance(normalized_deps, dict):
        normalized_deps = normalized_deps.get("depends_on", [])
    if not isinstance(normalized_deps, list):
        normalized_deps = []

    task_id = scheduler._extract_task_id(task)
    if task_id and task_id in normalized_deps:
        return False, f"self dependency: {task_id}"

    if not normalized_deps:
        return True, ""

    for dep_id in normalized_deps:
        dep_task = scheduler._get_task_from_repo(dep_id)
        if not isinstance(dep_task, dict):
            return False, f"dependency not found: {dep_id}"

        dep_status = str(dep_task.get("status") or "").strip().lower()
        if dep_status not in {"finished", "done", "success", "completed"}:
            return False, f"waiting dependency: {dep_id}"

    return True, ""


def unblock_tasks_if_dependencies_done(
    scheduler: Any,
    scheduler_build: str,
    status_blocked: str,
) -> None:
    tasks = scheduler._list_repo_tasks()
    if not isinstance(tasks, list):
        return

    for task in tasks:
        if not isinstance(task, dict):
            continue

        task = scheduler._hydrate_task_from_workspace(task)
        task_id = scheduler._extract_task_id(task)
        if not task_id:
            continue

        status = str(task.get("status") or "").strip().lower()
        if status != status_blocked:
            continue

        deps_ready, blocked_reason = scheduler._task_dependencies_satisfied(task)
        if not deps_ready:
            scheduler._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)
            continue

        task["status"] = "queued"
        task["blocked_reason"] = ""
        task["history"] = scheduler._append_history(task.get("history"), "queued")
        task["scheduler_build"] = scheduler_build
        scheduler._persist_task_payload(task_id=task_id, task=task)
        scheduler._enqueue_repo_task_if_ready(task, overwrite=True)

        trace = scheduler._load_trace_for_task(task)
        scheduler._trace_status(
            trace=trace,
            task=task,
            status="queued",
            tick=getattr(scheduler, "current_tick", 0),
            final_answer="",
            extra={"action": "unblocked_by_dependencies"},
        )
        scheduler._save_trace_for_task(task=task, trace=trace)
