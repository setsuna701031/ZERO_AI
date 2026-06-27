from __future__ import annotations

from typing import Any, Callable, Dict

from core.runtime.task_runtime import project_runtime_status
from core.tasks.scheduler_core.create_task_intent_helpers import (
    build_forced_repo_edit_intent,
    is_repo_edit_intent_candidate,
)


def install_scheduler_create_task_compat(
    scheduler_cls: Any,
    *,
    global_lookup: Callable[[str, Any], Any],
    status_queued: str,
) -> Dict[str, Any]:
    original_try_force_repo_edit = scheduler_cls._try_force_repo_edit_at_create_task
    original_create_task_record = scheduler_cls._create_task_record

    def _zero_v7337_scheduler_try_force_repo_edit_at_create_task(self, goal: str):
        text = str(goal or "").strip()
        if is_repo_edit_intent_candidate(text):
            return build_forced_repo_edit_intent(text, queued_status=status_queued)
        original = global_lookup(
            "_ZERO_V7337_ORIGINAL_SCHEDULER_TRY_FORCE_REPO_EDIT_AT_CREATE_TASK",
            original_try_force_repo_edit,
        )
        return original(self, goal)

    def _zero_v7337_scheduler_create_task_record(self, *args, **kwargs):
        original = global_lookup(
            "_ZERO_V7337_ORIGINAL_SCHEDULER_CREATE_TASK_RECORD",
            original_create_task_record,
        )
        task = original(self, *args, **kwargs)
        if not isinstance(task, dict):
            return task

        forced = task.get("last_step_result")
        planner = task.get("planner_result")
        if isinstance(planner, dict) and isinstance(planner.get("forced_repo_edit"), dict):
            forced = planner.get("forced_repo_edit")

        if isinstance(forced, dict) and forced.get("execution_intent_only"):
            project_runtime_status(task, status_queued, owner="core/tasks/scheduler.py")
            task["current_step_index"] = 0
            task["finished_tick"] = None
            task["final_answer"] = ""
            task["results"] = []
            task["step_results"] = []
            task["last_step_result"] = None
            task["execution_intent_only"] = True
            task["mutation_executed"] = False
            task["authority_context"] = self._build_scheduler_authority_context(task)
            if isinstance(task.get("planner_result"), dict):
                task["planner_result"]["execution_intent_only"] = True
                task["planner_result"]["mutation_executed"] = False
        return task

    scheduler_cls._try_force_repo_edit_at_create_task = _zero_v7337_scheduler_try_force_repo_edit_at_create_task
    scheduler_cls._create_task_record = _zero_v7337_scheduler_create_task_record

    return {
        "_ZERO_V7337_ORIGINAL_SCHEDULER_TRY_FORCE_REPO_EDIT_AT_CREATE_TASK": original_try_force_repo_edit,
        "_ZERO_V7337_ORIGINAL_SCHEDULER_CREATE_TASK_RECORD": original_create_task_record,
        "_zero_v7337_scheduler_try_force_repo_edit_at_create_task": _zero_v7337_scheduler_try_force_repo_edit_at_create_task,
        "_zero_v7337_scheduler_create_task_record": _zero_v7337_scheduler_create_task_record,
    }
