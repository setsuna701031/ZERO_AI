from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.task_runtime import project_runtime_status
from core.tasks.scheduler_core.repo_observability import build_failure_observability_event


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


def list_repo_tasks(scheduler: Any) -> List[Dict[str, Any]]:
    repo = getattr(scheduler, "task_repo", None)
    list_tasks_fn = getattr(repo, "list_tasks", None)
    if not callable(list_tasks_fn):
        return []

    try:
        loaded = list_tasks_fn()
    except Exception:
        return []

    if not isinstance(loaded, list):
        return []

    hydrate_fn = getattr(scheduler, "_hydrate_task_from_workspace", None)
    tasks: List[Dict[str, Any]] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        if callable(hydrate_fn):
            try:
                hydrated = hydrate_fn(item)
            except Exception:
                hydrated = item
            if isinstance(hydrated, dict):
                tasks.append(hydrated)
        else:
            tasks.append(copy.deepcopy(item))
    return tasks


def get_task_from_repo(scheduler: Any, task_id: str) -> Optional[Dict[str, Any]]:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None

    repo = getattr(scheduler, "task_repo", None)
    hydrate_fn = getattr(scheduler, "_hydrate_task_from_workspace", None)

    for method_name in ("get_task", "get", "load_task", "find_task"):
        method = getattr(repo, method_name, None)
        if not callable(method):
            continue
        try:
            value = method(normalized_task_id)
        except Exception:
            continue
        if not isinstance(value, dict):
            continue
        if callable(hydrate_fn):
            try:
                hydrated = hydrate_fn(value)
            except Exception:
                hydrated = value
            return hydrated if isinstance(hydrated, dict) else value
        return copy.deepcopy(value)

    extract_task_id = getattr(scheduler, "_extract_task_id", None)
    for task in list_repo_tasks(scheduler):
        if not isinstance(task, dict):
            continue
        try:
            candidate = extract_task_id(task) if callable(extract_task_id) else str(
                task.get("task_id") or task.get("task_name") or task.get("id") or ""
            ).strip()
        except Exception:
            candidate = str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()
        if candidate == normalized_task_id:
            if callable(hydrate_fn):
                try:
                    hydrated = hydrate_fn(task)
                except Exception:
                    hydrated = task
                return hydrated if isinstance(hydrated, dict) else task
            return copy.deepcopy(task)

    return None


def compact_runner_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a short, CLI-friendly result without mutating the input."""
    if not isinstance(result, dict):
        return result

    def _compact_multi(payload: Dict[str, Any], parent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        parent = parent if isinstance(parent, dict) else {}
        edits = payload.get("edits") if isinstance(payload.get("edits"), list) else []
        compact = {
            "ok": bool(payload.get("ok", False)),
            "action": str(payload.get("action") or "multi_code_edit"),
            "task_id": str(parent.get("task_id") or result.get("task_id") or ""),
            "status": str(parent.get("status") or result.get("status") or ""),
            "atomic": bool(payload.get("atomic", False)),
            "rollback": bool(
                payload.get("rollback")
                or payload.get("rollback_applied")
                or payload.get("staged_changes_discarded")
                or (
                    str(payload.get("action") or "").strip().lower() == "multi_code_edit_failed"
                    and bool(payload.get("atomic", False))
                )
            ),
            "changed_files": copy.deepcopy(payload.get("changed_files", [])),
            "edit_count": int(payload.get("edit_count", len(edits)) or 0),
            "failed_reason": str(payload.get("failed_reason") or payload.get("error") or ""),
            "step_count": result.get("step_count", parent.get("step_count", 0)),
            "steps_total": result.get("steps_total", parent.get("steps_total", 0)),
        }
        if isinstance(result.get("orchestration_summary"), dict):
            compact["orchestration_summary"] = copy.deepcopy(result.get("orchestration_summary"))
        if isinstance(result.get("repair_chain_orchestration"), dict):
            compact["repair_chain_orchestration"] = copy.deepcopy(result.get("repair_chain_orchestration"))
        return compact

    action = str(result.get("action") or "").strip().lower()
    if action in {"multi_code_edit", "multi_code_edit_failed"}:
        return _compact_multi(result)

    last_step_result = result.get("last_step_result")
    if isinstance(last_step_result, dict):
        nested = last_step_result.get("result")
        if isinstance(nested, dict):
            nested_action = str(nested.get("action") or "").strip().lower()
            if nested_action in {"multi_code_edit", "multi_code_edit_failed"}:
                return _compact_multi(nested, parent=last_step_result)

    if action in {"simple_task_finished", "terminal_skip"}:
        compact = {
            "ok": bool(result.get("ok", False)),
            "action": str(result.get("action") or ""),
            "task_id": str(result.get("task_id") or ""),
            "status": str(result.get("status") or ""),
            "step_count": result.get("step_count", 0),
            "steps_total": result.get("steps_total", 0),
        }
        orchestration_summary = result.get("orchestration_summary")
        if isinstance(orchestration_summary, dict) and orchestration_summary:
            compact["orchestration_summary"] = copy.deepcopy(orchestration_summary)
        return compact

    return result


def mark_repo_task_finished(
    scheduler: Any,
    task_id: str,
    result: Any = None,
    *,
    completion_authority: Any = None,
) -> None:
    from core.runtime.runtime_authority_seal import is_task_completion_authority

    if not is_task_completion_authority(completion_authority, task_id=task_id):
        raise PermissionError("task_completion_authority_required")
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    project_runtime_status(task, "finished", owner="core/tasks/scheduler_core/repo_task_state.py")
    task["blocked_reason"] = ""
    task["last_error"] = ""
    task["failure_message"] = ""
    task["finished_tick"] = getattr(scheduler, "current_tick", 0)
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")

    if result is not None:
        task["final_answer"] = result
    else:
        task["final_answer"] = task.get("final_answer", "")

    task["history"] = scheduler._append_history(task.get("history"), "finished")
    scheduler._persist_task_payload(
        task_id=task_id,
        task=task,
        completion_authority=completion_authority,
    )
    scheduler.worker_pool.release_by_task(task_id)
    scheduler._unblock_tasks_if_dependencies_done()


def mark_repo_task_failed(scheduler: Any, task_id: str, error: str = "") -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    final_error = str(error or task.get("last_error") or task.get("failure_message") or "task failed")

    project_runtime_status(task, "failed", owner="core/tasks/scheduler_core/repo_task_state.py")
    task["blocked_reason"] = ""
    task["last_error"] = final_error
    task["failure_message"] = final_error
    task["last_failure_tick"] = getattr(scheduler, "current_tick", 0)
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")
    task["history"] = scheduler._append_history(task.get("history"), "failed")
    task["observability_event"] = build_failure_observability_event(
        event_type="repo_task_failed",
        task=task,
        task_id=task_id,
        error_text=final_error,
        status="failed",
    )

    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)


def mark_repo_task_queued(scheduler: Any, task_id: str, error: str = "") -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    project_runtime_status(task, "queued", owner="core/tasks/scheduler_core/repo_task_state.py")
    task["blocked_reason"] = ""
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")

    final_error = str(error or "").strip()
    if final_error:
        task["last_error"] = final_error
        task["failure_message"] = final_error
    else:
        task["last_error"] = ""
        task["failure_message"] = ""

    task["history"] = scheduler._append_history(task.get("history"), "queued")
    if final_error:
        task["observability_event"] = build_failure_observability_event(
            event_type="repo_task_requeued",
            task=task,
            task_id=task_id,
            error_text=final_error,
            status="queued",
        )
    scheduler._persist_task_payload(task_id=task_id, task=task)


def _resolve_repo_task_mark_adapter_callback(scheduler: Any, operation: str) -> Any:
    adapter = getattr(scheduler, "repo_task_mark_adapter", None)
    if adapter is None:
        adapter = getattr(scheduler, "repo_task_mark_callbacks", None)
    if adapter is None:
        return None

    names = {
        "finished": ("mark_finished", "mark_repo_task_finished", "finished"),
        "failed": ("mark_failed", "mark_repo_task_failed", "failed"),
        "queued": ("mark_queued", "mark_repo_task_queued", "queued"),
    }.get(operation, ())

    if isinstance(adapter, dict):
        for name in names:
            callback = adapter.get(name)
            if callable(callback):
                return callback
        return None

    for name in names:
        callback = getattr(adapter, name, None)
        if callable(callback):
            return callback

    return None


def mark_repo_task_with_adapter(
    scheduler: Any,
    operation: str,
    task_id: str,
    *,
    result: Any = None,
    error: str = "",
    completion_authority: Any = None,
) -> None:
    normalized_operation = str(operation or "").strip().lower()
    if normalized_operation == "finished":
        from core.runtime.runtime_authority_seal import is_task_completion_authority

        if not is_task_completion_authority(completion_authority, task_id=task_id):
            raise PermissionError("task_completion_authority_required")
    callback = _resolve_repo_task_mark_adapter_callback(scheduler, normalized_operation)
    if callable(callback):
        if normalized_operation == "finished":
            callback(
                scheduler=scheduler,
                task_id=task_id,
                result=result,
                completion_authority=completion_authority,
            )
            return
        callback(scheduler=scheduler, task_id=task_id, error=error)
        return

    if normalized_operation == "finished":
        mark_repo_task_finished(
            scheduler=scheduler,
            task_id=task_id,
            result=result,
            completion_authority=completion_authority,
        )
        return
    if normalized_operation == "failed":
        mark_repo_task_failed(scheduler=scheduler, task_id=task_id, error=error)
        return
    if normalized_operation == "queued":
        mark_repo_task_queued(scheduler=scheduler, task_id=task_id, error=error)
        return
