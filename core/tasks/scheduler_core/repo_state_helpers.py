from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional, Tuple


LOOP_STATE_KEYS = (
    "last_observation",
    "last_decision",
    "last_decision_reason",
    "next_action",
    "terminal_reason",
    "loop_cycle_count",
    "loop_history",
)

REVIEW_STATE_KEYS = (
    "review_id",
    "review_status",
    "requires_review",
    "agent_action",
    "review_payload",
)




def _save_runtime_state_from_merged(scheduler: Any, merged: Dict[str, Any]) -> None:
    runtime = getattr(scheduler, "task_runtime", None)
    if runtime is None:
        return

    save_fn = getattr(runtime, "save_runtime_state", None)
    if not callable(save_fn):
        return

    state_payload: Dict[str, Any] = copy.deepcopy(merged)

    load_fn = getattr(runtime, "load_runtime_state", None)
    if callable(load_fn):
        try:
            loaded = load_fn(merged)
            if isinstance(loaded, dict):
                loaded.update(copy.deepcopy(merged))
                state_payload = loaded
        except Exception:
            pass

    try:
        save_fn(merged, state_payload)
    except Exception:
        pass

# ============================================================
# ZERO Runtime Aggregate Convergence v1.3A
# Repo Runtime State Aggregate Adapter Payload
# ============================================================

def attach_repo_runtime_state_adapter_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("adapter_payload"), dict):
        return payload

    ok = _repo_runtime_adapter_ok(payload)
    message = _repo_runtime_adapter_message(payload, ok=ok)
    final_answer = _repo_runtime_adapter_final_answer(payload, message=message)

    adapter_payload = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else _repo_runtime_adapter_error_text(payload),
        "error_type": "" if ok else _repo_runtime_adapter_error_type(payload),
        "runtime_mode": _repo_runtime_adapter_runtime_mode(payload),
        "last_result": _repo_runtime_adapter_last_result(payload),
        "execution_trace": _repo_runtime_adapter_execution_trace(payload),
        "raw": copy.deepcopy(payload),
    }

    payload["adapter_payload"] = adapter_payload
    return payload


def build_repo_runtime_state_adapter_payload(
    *,
    merged: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = copy.deepcopy(merged) if isinstance(merged, dict) else {}
    runner_payload = copy.deepcopy(runner_result) if isinstance(runner_result, dict) else {}

    if isinstance(runner_payload.get("adapter_payload"), dict):
        adapter = copy.deepcopy(runner_payload["adapter_payload"])
        merged_payload["adapter_payload"] = adapter
        return merged_payload

    status = str(merged_payload.get("status") or "").strip().lower()
    runner_ok = runner_payload.get("ok") if isinstance(runner_payload, dict) else None

    if runner_ok is not None:
        ok = bool(runner_ok)
    elif status in {"failed", "error", "cancelled"}:
        ok = False
    else:
        ok = True

    message = str(
        merged_payload.get("message")
        or runner_payload.get("message")
        or merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or ("runtime state ok" if ok else "runtime state failed")
    )

    final_answer = str(
        merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or message
    )

    error_text = str(
        merged_payload.get("last_error")
        or merged_payload.get("failure_message")
        or runner_payload.get("error")
        or ""
    )

    error_type = str(
        merged_payload.get("failure_type")
        or runner_payload.get("error_type")
        or ""
    )

    execution_trace = []
    for source in (runner_payload, merged_payload):
        trace = source.get("execution_trace") if isinstance(source, dict) else None
        if isinstance(trace, list):
            execution_trace = copy.deepcopy(trace)
            break

    last_result = {}
    for source in (runner_payload, merged_payload):
        candidate = source.get("last_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break
        candidate = source.get("last_step_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break

    merged_payload["adapter_payload"] = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else error_text,
        "error_type": "" if ok else (error_type or "runtime_state_failed"),
        "runtime_mode": str(merged_payload.get("runtime_mode") or runner_payload.get("runtime_mode") or "repo_state"),
        "last_result": last_result,
        "execution_trace": execution_trace,
        "raw": copy.deepcopy(merged_payload),
    }
    return merged_payload


def _repo_runtime_adapter_ok(payload: Dict[str, Any]) -> bool:
    if "ok" in payload:
        return bool(payload.get("ok"))

    status = str(payload.get("status") or "").strip().lower()
    if status in {"failed", "error", "cancelled"}:
        return False

    if payload.get("last_error") or payload.get("failure_message"):
        return False

    return True


def _repo_runtime_adapter_message(payload: Dict[str, Any], *, ok: bool) -> str:
    for key in ("message", "summary", "final_answer"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    if not ok:
        return _repo_runtime_adapter_error_text(payload) or "runtime state failed"

    return "runtime state ok"


def _repo_runtime_adapter_final_answer(payload: Dict[str, Any], *, message: str) -> str:
    value = payload.get("final_answer")
    if value is not None and str(value).strip():
        return str(value).strip()
    return message


def _repo_runtime_adapter_error_text(payload: Dict[str, Any]) -> str:
    for key in ("last_error", "failure_message", "error_text", "error"):
        value = payload.get(key)
        if isinstance(value, dict):
            message = value.get("message") or value.get("error") or value.get("text")
            if message is not None and str(message).strip():
                return str(message).strip()
        elif value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _repo_runtime_adapter_error_type(payload: Dict[str, Any]) -> str:
    for key in ("failure_type", "error_type"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("type", "error_type", "code"):
            value = error.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return "runtime_state_failed" if _repo_runtime_adapter_error_text(payload) else ""


def _repo_runtime_adapter_runtime_mode(payload: Dict[str, Any]) -> str:
    for key in ("runtime_mode", "mode", "execution_mode"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "repo_state"


def _repo_runtime_adapter_last_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("last_result", "last_step_result", "runner_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def _repo_runtime_adapter_execution_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        return copy.deepcopy(trace)

    for key in ("last_result", "last_step_result", "runner_result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_trace = nested.get("execution_trace")
            if isinstance(nested_trace, list):
                return copy.deepcopy(nested_trace)

    return []


# ============================================================
# ZERO Runtime Observability Layer v1B
# Failure / Retry Observability Envelope
# ============================================================

def build_failure_observability_event(
    *,
    event_type: str,
    task: Dict[str, Any],
    task_id: str = "",
    error_text: str = "",
    status: str = "",
) -> Dict[str, Any]:
    task_payload = task if isinstance(task, dict) else {}
    resolved_task_id = str(
        task_id
        or task_payload.get("task_id")
        or task_payload.get("id")
        or task_payload.get("task_name")
        or ""
    ).strip()

    resolved_status = str(status or task_payload.get("status") or "").strip().lower()
    resolved_error = str(
        error_text
        or task_payload.get("last_error")
        or task_payload.get("failure_message")
        or ""
    ).strip()

    failure_type = str(
        task_payload.get("failure_type")
        or ("repo_task_failed" if resolved_status == "failed" else "repo_task_requeued")
    ).strip()

    event = {
        "event_type": str(event_type or "repo_task_failure"),
        "ok": False if resolved_status in {"failed", "error"} else True,
        "task_id": resolved_task_id,
        "status": resolved_status,
        "failure_type": failure_type,
        "error_text": resolved_error,
        "runtime_mode": "repo_state",
        "retry_count": int(task_payload.get("retry_count", 0) or 0),
        "replan_count": int(task_payload.get("replan_count", 0) or 0),
        "repair_fingerprint": str(task_payload.get("repair_fingerprint") or ""),
    }
    return event

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


def mark_repo_task_finished(scheduler: Any, task_id: str, result: Any = None) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    task["status"] = "finished"
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
    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)
    scheduler._unblock_tasks_if_dependencies_done()


def mark_repo_task_failed(scheduler: Any, task_id: str, error: str = "") -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    final_error = str(error or task.get("last_error") or task.get("failure_message") or "task failed")

    task["status"] = "failed"
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

    task["status"] = "queued"
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
) -> None:
    normalized_operation = str(operation or "").strip().lower()
    callback = _resolve_repo_task_mark_adapter_callback(scheduler, normalized_operation)
    if callable(callback):
        if normalized_operation == "finished":
            callback(scheduler=scheduler, task_id=task_id, result=result)
            return
        callback(scheduler=scheduler, task_id=task_id, error=error)
        return

    if normalized_operation == "finished":
        mark_repo_task_finished(scheduler=scheduler, task_id=task_id, result=result)
        return
    if normalized_operation == "failed":
        mark_repo_task_failed(scheduler=scheduler, task_id=task_id, error=error)
        return
    if normalized_operation == "queued":
        mark_repo_task_queued(scheduler=scheduler, task_id=task_id, error=error)
        return


def sync_blocked_state(scheduler: Any, task_id: str, blocked_reason: str) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    final_reason = str(blocked_reason or task.get("blocked_reason") or "").strip()
    changed = False

    if current_status != scheduler.STATUS_BLOCKED:
        task["status"] = scheduler.STATUS_BLOCKED
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
            "blocked_reason": str(blocked_reason or ""),
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
        task["status"] = "queued"
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


def _sync_loop_fields_into_merged(merged: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in LOOP_STATE_KEYS:
        if key in source:
            merged[key] = copy.deepcopy(source.get(key))


def _sync_review_fields_into_merged(merged: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in REVIEW_STATE_KEYS:
        if key in source:
            merged[key] = copy.deepcopy(source.get(key))




def _select_effective_task_payload(task: Dict[str, Any], runner_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    effective = copy.deepcopy(task if isinstance(task, dict) else {})
    if isinstance(runner_result, dict):
        runner_task = runner_result.get("task")
        if isinstance(runner_task, dict):
            effective.update(copy.deepcopy(runner_task))
    return effective
def sync_runtime_back_to_repo(
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> None:
    task_id = str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()
    if not task_id:
        return

    effective_task = _select_effective_task_payload(task=task, runner_result=runner_result)

    repo_task = scheduler._get_task_from_repo(task_id)
    base_task = copy.deepcopy(repo_task if isinstance(repo_task, dict) else effective_task)
    base_task = scheduler._hydrate_task_from_workspace(base_task)
    _sync_loop_fields_into_merged(base_task, effective_task)
    _sync_review_fields_into_merged(base_task, effective_task)

    runtime_state = None
    if scheduler.task_runtime is not None and hasattr(scheduler.task_runtime, "load_runtime_state"):
        try:
            runtime_state = scheduler.task_runtime.load_runtime_state(base_task)
        except Exception:
            runtime_state = None

    merged = copy.deepcopy(base_task)

    if isinstance(runtime_state, dict):
        for key in (
            "status", "priority", "retry_count", "max_retries", "retry_delay", "next_retry_tick", "timeout_ticks",
            "wait_until_tick", "created_tick", "last_run_tick", "last_failure_tick", "finished_tick", "depends_on",
            "blocked_reason", "failure_type", "failure_message", "last_error", "final_answer", "cancel_requested",
            "cancel_reason", "current_step_index", "steps", "steps_total", "results", "step_results",
            "last_step_result", "replan_count", "replanned", "replan_reason", "replan_decision", "replan_summary",
            "replan_failed_step_type", "replan_repairable", "completion_mode", "verification_required",
            "verification_passed", "max_replans", "planner_result", "history", "execution_log", "result_file",
            "execution_log_file", "plan_file", "log_file", "runtime_state_file", "trace_file", "workspace_root",
            "workspace_dir", "shared_dir", "task_dir", "scheduler_build",
        ):
            if key in runtime_state:
                merged[key] = copy.deepcopy(runtime_state.get(key))
        _sync_loop_fields_into_merged(merged, runtime_state)
        _sync_review_fields_into_merged(merged, runtime_state)

    _sync_loop_fields_into_merged(merged, task)
    _sync_review_fields_into_merged(merged, task)

    if isinstance(runner_result, dict):
        for key in (
            "status", "final_answer", "execution_log", "results", "step_results", "last_step_result",
            "current_step_index", "steps_total", "last_run_tick", "last_failure_tick", "finished_tick",
            "blocked_reason", "replan_decision", "replan_summary", "replan_failed_step_type",
            "replan_repairable", "completion_mode", "verification_required", "verification_passed",
        ):
            if key in runner_result:
                merged[key] = copy.deepcopy(runner_result.get(key))
        _sync_loop_fields_into_merged(merged, runner_result)
        _sync_review_fields_into_merged(merged, runner_result)

        runner_task = runner_result.get("task")
        if isinstance(runner_task, dict):
            _sync_loop_fields_into_merged(merged, runner_task)
            _sync_review_fields_into_merged(merged, runner_task)

    if isinstance(runner_result, dict):
        replan_result = runner_result.get("replan_result")
        if isinstance(replan_result, dict) and bool(replan_result.get("replanned")):
            raw_replan_result = replan_result.get("raw_replan_result", {})
            plan = raw_replan_result.get("plan", {}) if isinstance(raw_replan_result, dict) else {}
            new_steps = plan.get("steps", []) if isinstance(plan, dict) else []

            if isinstance(new_steps, list) and new_steps:
                merged["steps"] = copy.deepcopy(new_steps)
                merged["steps_total"] = len(new_steps)
                merged["current_step_index"] = 0
            else:
                merged["current_step_index"] = 0

            merged["replanned"] = True
            merged["replan_count"] = int(replan_result.get("replan_count", merged.get("replan_count", 0)) or 0)
            merged["planner_result"] = copy.deepcopy(plan) if isinstance(plan, dict) else {}
            merged["replan_reason"] = str(
                runner_result.get("replan_reason")
                or merged.get("last_error")
                or merged.get("failure_message")
                or ""
            )

            status_from_runner = str(runner_result.get("status") or "").strip().lower()
            if status_from_runner:
                merged["status"] = status_from_runner

    if not isinstance(merged.get("results"), list):
        merged["results"] = []
    if not isinstance(merged.get("step_results"), list):
        merged["step_results"] = copy.deepcopy(merged.get("results", []))

    if merged.get("last_step_result") is None and merged.get("step_results"):
        try:
            merged["last_step_result"] = copy.deepcopy(merged["step_results"][-1])
        except Exception:
            pass

    steps = merged.get("steps", [])
    if isinstance(steps, list):
        merged["steps_total"] = int(merged.get("steps_total", len(steps)) or len(steps))
    else:
        merged["steps_total"] = int(merged.get("steps_total", 0) or 0)

    if merged.get("current_step_index") is None:
        merged["current_step_index"] = 0

    merged["task_name"] = merged.get("task_name") or task_id
    merged["task_dir"] = merged.get("task_dir") or os.path.join(scheduler.tasks_root, task_id)
    merged["plan_file"] = merged.get("plan_file") or os.path.join(merged["task_dir"], "plan.json")
    merged["runtime_state_file"] = merged.get("runtime_state_file") or os.path.join(merged["task_dir"], "runtime_state.json")
    merged["trace_file"] = merged.get("trace_file") or os.path.join(merged["task_dir"], "trace.json")
    merged["workspace_root"] = merged.get("workspace_root") or scheduler.workspace_root
    merged["workspace_dir"] = merged.get("workspace_dir") or scheduler.tasks_root
    merged["shared_dir"] = merged.get("shared_dir") or scheduler.shared_dir
    merged["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")

    merged.setdefault("last_observation", {})
    merged.setdefault("last_decision", "")
    merged.setdefault("last_decision_reason", "")
    merged.setdefault("next_action", "")
    merged.setdefault("terminal_reason", "")
    merged["loop_cycle_count"] = int(merged.get("loop_cycle_count", 0) or 0)
    if not isinstance(merged.get("loop_history"), list):
        merged["loop_history"] = []
    merged.setdefault("review_id", "")
    merged.setdefault("review_status", "")
    merged.setdefault("requires_review", False)
    merged.setdefault("transaction_state", "")
    merged.setdefault("allowed_next_action", "")
    merged.setdefault("approval_required", bool(merged.get("requires_approval", False)))
    merged.setdefault("agent_action", "")
    if not isinstance(merged.get("review_payload"), dict):
        merged["review_payload"] = {}

    inferred_replan_result = None
    if isinstance(runner_result, dict):
        maybe_replan = runner_result.get("replan_result")
        if isinstance(maybe_replan, dict):
            inferred_replan_result = maybe_replan

    merged = scheduler._backfill_replan_decision_fields(merged, replan_result=inferred_replan_result)
    merged = scheduler._infer_completion_fields(merged)
    merged = scheduler._clear_stale_replan_fields(merged)
    merged = scheduler._refresh_task_public_fields(merged)
    merged = build_repo_runtime_state_adapter_payload(merged=merged, runner_result=runner_result)
    _save_runtime_state_from_merged(scheduler, merged)
    scheduler._persist_task_payload(task_id=task_id, task=merged)

    normalized_status = str(merged.get("status") or "").strip().lower()
    if not normalized_status:
        return

    if normalized_status in {"finished", "done", "success", "completed", scheduler.STATUS_FINISHED}:
        final_answer = merged.get("final_answer", "")
        mark_repo_task_finished(scheduler=scheduler, task_id=task_id, result=final_answer)
        return

    if normalized_status in {"failed", "error", scheduler.STATUS_FAILED}:
        final_error = str(
            merged.get("last_error")
            or merged.get("failure_message")
            or (runner_result or {}).get("error")
            or "task failed"
        )
        mark_repo_task_failed(scheduler=scheduler, task_id=task_id, error=final_error)
        return

    if normalized_status in {scheduler.STATUS_BLOCKED, "blocked"}:
        blocked_reason = str(merged.get("blocked_reason") or "")
        sync_blocked_state(scheduler=scheduler, task_id=task_id, blocked_reason=blocked_reason)
        return

    if normalized_status in {"queued", scheduler.STATUS_QUEUED, "ready", "retry"}:
        queue_error = str(merged.get("last_error") or merged.get("failure_message") or "")
        mark_repo_task_queued(scheduler=scheduler, task_id=task_id, error=queue_error)
        return

    if normalized_status in {"running"}:
        sync_unblocked_state(scheduler=scheduler, task_id=task_id)
        return
