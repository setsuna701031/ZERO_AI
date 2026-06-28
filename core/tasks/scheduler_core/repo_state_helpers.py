from __future__ import annotations

from typing import Any, Dict, List

from core.runtime.task_runtime import project_runtime_status
from core.tasks.scheduler_core.repo_blocked_state import (
    _advisory_transition_reason,
    _append_status_to_history,
    _downgrade_advisory_blocked_status,
    _has_remaining_steps,
    _is_successful_nonblocking_step_result,
    _should_downgrade_advisory_blocked_status,
    sync_blocked_state,
    sync_unblocked_state,
)
from core.tasks.scheduler_core.repo_observability import build_failure_observability_event
from core.tasks.scheduler_core.repo_runtime_adapter import (
    attach_repo_runtime_state_adapter_payload,
    build_repo_runtime_state_adapter_payload,
    repo_runtime_adapter_error_text,
    repo_runtime_adapter_error_type,
    repo_runtime_adapter_execution_trace,
    repo_runtime_adapter_final_answer,
    repo_runtime_adapter_last_result,
    repo_runtime_adapter_message,
    repo_runtime_adapter_ok,
    repo_runtime_adapter_runtime_mode,
)
from core.tasks.scheduler_core.repo_runtime_sync import (
    _save_runtime_state_from_merged,
    _select_effective_task_payload,
    _sync_loop_fields_into_merged,
    _sync_review_fields_into_merged,
    sync_runtime_back_to_repo,
)
from core.tasks.scheduler_core.repo_task_state import (
    compact_runner_result,
    extract_effective_status_and_answer,
    get_task_from_repo,
    list_repo_tasks,
    mark_repo_task_failed,
    mark_repo_task_finished,
    mark_repo_task_queued,
    mark_repo_task_with_adapter,
)


def _project_repo_state_runtime_status(target: Dict[str, Any], status: Any) -> Dict[str, Any]:
    return project_runtime_status(target, status, owner="core/tasks/scheduler_core/repo_state_helpers.py")


def _repo_runtime_adapter_ok(payload: Dict[str, Any]) -> bool:
    return repo_runtime_adapter_ok(payload)


def _repo_runtime_adapter_message(payload: Dict[str, Any], *, ok: bool) -> str:
    return repo_runtime_adapter_message(payload, ok=ok)


def _repo_runtime_adapter_final_answer(payload: Dict[str, Any], *, message: str) -> str:
    return repo_runtime_adapter_final_answer(payload, message=message)


def _repo_runtime_adapter_error_text(payload: Dict[str, Any]) -> str:
    return repo_runtime_adapter_error_text(payload)


def _repo_runtime_adapter_error_type(payload: Dict[str, Any]) -> str:
    return repo_runtime_adapter_error_type(payload)


def _repo_runtime_adapter_runtime_mode(payload: Dict[str, Any]) -> str:
    return repo_runtime_adapter_runtime_mode(payload)


def _repo_runtime_adapter_last_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    return repo_runtime_adapter_last_result(payload)


def _repo_runtime_adapter_execution_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return repo_runtime_adapter_execution_trace(payload)


__all__ = [
    "_advisory_transition_reason",
    "_append_status_to_history",
    "_downgrade_advisory_blocked_status",
    "_has_remaining_steps",
    "_is_successful_nonblocking_step_result",
    "_repo_runtime_adapter_error_text",
    "_repo_runtime_adapter_error_type",
    "_repo_runtime_adapter_execution_trace",
    "_repo_runtime_adapter_final_answer",
    "_repo_runtime_adapter_last_result",
    "_repo_runtime_adapter_message",
    "_repo_runtime_adapter_ok",
    "_repo_runtime_adapter_runtime_mode",
    "_save_runtime_state_from_merged",
    "_select_effective_task_payload",
    "_should_downgrade_advisory_blocked_status",
    "_sync_loop_fields_into_merged",
    "_sync_review_fields_into_merged",
    "attach_repo_runtime_state_adapter_payload",
    "build_failure_observability_event",
    "build_repo_runtime_state_adapter_payload",
    "compact_runner_result",
    "extract_effective_status_and_answer",
    "get_task_from_repo",
    "list_repo_tasks",
    "mark_repo_task_failed",
    "mark_repo_task_finished",
    "mark_repo_task_queued",
    "mark_repo_task_with_adapter",
    "sync_blocked_state",
    "sync_runtime_back_to_repo",
    "sync_unblocked_state",
]
