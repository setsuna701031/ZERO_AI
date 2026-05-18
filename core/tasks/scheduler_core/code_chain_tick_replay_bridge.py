from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Optional, Set


CODE_CHAIN_WORKFLOW_STEP_TYPES = {
    "code_chain_analyze",
    "code_chain_repair",
    "autonomous_code_repair",
    "code_chain_verify",
}


def current_step_type(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return ""
    try:
        idx = int(task.get("current_step_index", 0) or 0)
    except Exception:
        idx = 0
    steps = task.get("steps")
    if not isinstance(steps, list) or not (0 <= idx < len(steps)):
        return ""
    step = steps[idx]
    if not isinstance(step, dict):
        return ""
    return str(step.get("type") or "").strip().lower()


def resolve_task_runner(scheduler: Any) -> Any:
    runner = getattr(scheduler, "task_runner", None)
    if runner is not None:
        return runner
    try:
        from core.runtime.task_runner import TaskRunner

        runner = TaskRunner(
            step_executor=getattr(scheduler, "step_executor", None),
            task_runtime=getattr(scheduler, "task_runtime", None),
            replanner=getattr(scheduler, "replanner", None),
            debug=bool(getattr(scheduler, "debug", False)),
        )
        scheduler.task_runner = runner
        return runner
    except Exception:
        return None


def run_code_chain_simple_tick_bridge(
    scheduler: Any,
    *,
    task: Dict[str, Any],
    current_tick: Optional[int],
    workflow_step_types: Set[str],
    original_run_simple_task_tick: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    step_type = current_step_type(task)
    if step_type in workflow_step_types:
        runner = resolve_task_runner(scheduler)
        if runner is None:
            return {
                "ok": False,
                "action": "code_chain_workflow_runner_missing",
                "status": "failed",
                "error": "TaskRunner is required for Code Chain workflow step advancement",
                "task": copy.deepcopy(task) if isinstance(task, dict) else task,
            }

        tick = current_tick
        if tick is None:
            try:
                tick = int(getattr(scheduler, "current_tick", 0) or 0)
            except Exception:
                tick = 0

        result = runner.run_task_tick(task=task, current_tick=tick)
        if not isinstance(result, dict):
            result = {
                "ok": bool(result),
                "action": "code_chain_workflow_runner_result",
                "status": "running" if result else "failed",
                "raw_result": copy.deepcopy(result),
                "task": copy.deepcopy(task) if isinstance(task, dict) else task,
            }

        try:
            scheduler._sync_runner_result_and_requeue_if_ready(task=task, runner_result=result)
        except Exception:
            pass
        return result

    return original_run_simple_task_tick(scheduler, task=task, current_tick=current_tick)


def build_code_chain_simple_tick_bridge(
    original_run_simple_task_tick: Callable[..., Dict[str, Any]],
) -> Callable[..., Dict[str, Any]]:
    def _run_code_chain_simple_tick_bridge(
        scheduler: Any,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        return run_code_chain_simple_tick_bridge(
            scheduler,
            task=task,
            current_tick=current_tick,
            workflow_step_types=CODE_CHAIN_WORKFLOW_STEP_TYPES,
            original_run_simple_task_tick=original_run_simple_task_tick,
        )

    return _run_code_chain_simple_tick_bridge
