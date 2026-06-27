from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from core.tasks.scheduler_core.dispatch_runtime_router import route_sync_runner_result_and_requeue_if_ready
from core.tasks.scheduler_core.public_task_record_helpers import sync_runtime_back_to_repo_with_retry_collapse


def run_one_step(
    scheduler: Any,
    *,
    task: Dict[str, Any],
    current_tick: Optional[int] = None,
    terminal_statuses: set[str],
) -> Dict[str, Any]:
    task = scheduler._hydrate_task_from_workspace(task)
    task = scheduler._ensure_executable_steps_for_task(task)
    task_id = scheduler._extract_task_id(task)

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in terminal_statuses:
        result = scheduler._build_terminal_skip_runner_result(task=task)
        result = scheduler._attach_orchestration_summary_to_runner_result(task=task, runner_result=result)
        sync_runtime_back_to_repo_with_retry_collapse(scheduler=scheduler, task=task, runner_result=result)
        return scheduler._compact_runner_result(result)

    scheduler._emit_scheduler_evidence(
        "dispatched",
        task_id=task_id,
        queue_name="runtime",
    )

    if scheduler._is_scheduler_owned_simple_step_task(task):
        result = scheduler._run_simple_task_tick(task=task, current_tick=current_tick)
        last_step_result = result.get("last_step_result") if isinstance(result, dict) else {}
        delegated_result = (
            last_step_result.get("result")
            if isinstance(last_step_result, dict) and isinstance(last_step_result.get("result"), dict)
            else {}
        )
        execution_path = (
            delegated_result.get("execution_path")
            if isinstance(delegated_result.get("execution_path"), dict)
            else {}
        )
        if (
            isinstance(result, dict)
            and str(result.get("action") or "").strip().lower() == "simple_step_failed"
            and execution_path.get("step_executor_endpoint_only") is True
        ):
            result["ok"] = True
            result["scheduler_dispatch_ok"] = True
        result = scheduler._attach_orchestration_summary_to_runner_result(task=task, runner_result=result)
        route_sync_runner_result_and_requeue_if_ready(scheduler, task=task, runner_result=result)
        public_task = copy.deepcopy(task)
        for key in (
            "status",
            "current_step_index",
            "steps_total",
            "results",
            "step_results",
            "last_step_result",
            "execution_log",
            "final_answer",
            "last_run_tick",
            "finished_tick",
            "last_failure_tick",
        ):
            if key in result:
                public_task[key] = copy.deepcopy(result[key])
        result["task"] = copy.deepcopy(public_task)
        result["runtime_state"] = copy.deepcopy(public_task)
        return scheduler._compact_runner_result(result)

    loop_result = scheduler._run_task_via_agent_loop_with_fallback_check(
        task=task,
        current_tick=current_tick,
    )
    if loop_result is not None:
        loop_result = scheduler._attach_orchestration_summary_to_runner_result(task=task, runner_result=loop_result)
        return scheduler._compact_runner_result(loop_result)

    result = scheduler._run_simple_task_tick(task=task, current_tick=current_tick)
    result = scheduler._attach_orchestration_summary_to_runner_result(task=task, runner_result=result)
    route_sync_runner_result_and_requeue_if_ready(scheduler, task=task, runner_result=result)
    return scheduler._compact_runner_result(result)


def build_terminal_skip_runner_result(scheduler: Any, *, task: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "ok": True,
        "action": "terminal_skip",
        "task_id": scheduler._extract_task_id(task),
        "status": str(task.get("status") or "").strip().lower(),
        "final_answer": task.get("final_answer", ""),
        "task": copy.deepcopy(task),
    }
    runtime = getattr(scheduler, "task_runtime", None)
    if runtime is not None and hasattr(runtime, "load_runtime_state"):
        try:
            runtime_state = runtime.load_runtime_state(task)
            if isinstance(runtime_state, dict):
                result["runtime_state"] = copy.deepcopy(runtime_state)
        except Exception:
            pass
    return result
