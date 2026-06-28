from __future__ import annotations

from typing import Any, Dict, List

from core.runtime.task_runtime import project_runtime_status


_SIMPLE_RUNNER_OWNER = "core/tasks/scheduler_core/simple_runner_helpers.py"


def _apply_simple_step_collections_to_task(
    task: Dict[str, Any],
    *,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> None:
    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result


def _apply_simple_failure_fields(
    scheduler,
    task: Dict[str, Any],
    error: Exception,
) -> None:
    task["last_error"] = str(error)
    task["failure_message"] = str(error)
    task["last_failure_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick


def _apply_simple_success_advance(
    scheduler,
    task: Dict[str, Any],
    current_step_index: int,
) -> None:
    task["current_step_index"] = current_step_index + 1
    task["last_run_tick"] = scheduler.current_tick


def _apply_simple_replanned_queued_state(
    scheduler,
    task: Dict[str, Any],
    error: Exception,
) -> None:
    project_runtime_status(task, "queued", owner=_SIMPLE_RUNNER_OWNER)
    task["replan_reason"] = str(task.get("last_error") or task.get("failure_message") or str(error))
    task["current_step_index"] = 0
    task["history"] = scheduler._append_history(task.get("history"), "replanned")
    task["history"] = scheduler._append_history(task.get("history"), "queued")


def _apply_simple_terminal_failed_state(
    scheduler,
    task: Dict[str, Any],
) -> None:
    project_runtime_status(task, "failed", owner=_SIMPLE_RUNNER_OWNER)
    task["history"] = scheduler._append_history(task.get("history"), "failed")


def _apply_simple_terminal_finished_state(
    scheduler,
    task: Dict[str, Any],
    final_answer: str,
) -> None:
    project_runtime_status(task, "finished", owner=_SIMPLE_RUNNER_OWNER)
    task["final_answer"] = final_answer
    task["finished_tick"] = scheduler.current_tick
    task["history"] = scheduler._append_history(task.get("history"), "finished")


def _apply_simple_queued_state(
    scheduler,
    task: Dict[str, Any],
) -> None:
    project_runtime_status(task, "queued", owner=_SIMPLE_RUNNER_OWNER)
    task["history"] = scheduler._append_history(task.get("history"), "queued")
