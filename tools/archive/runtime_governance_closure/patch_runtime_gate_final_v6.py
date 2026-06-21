from pathlib import Path

TASK_RUNNER = Path("core/runtime/task_runner.py")
SCHEDULER = Path("core/tasks/scheduler.py")

TASK_PATCH = r'''
# ZERO_PATCH_RUNTIME_GATE_FINAL_V6

_zero_taskrunner_base_run_task_tick_v6 = TaskRunner.run_task_tick

def _zero_run_task_tick_v6(self, task, *args, **kwargs):
    result = _zero_taskrunner_base_run_task_tick_v6(self, task, *args, **kwargs)

    if isinstance(result, dict) and result.get("ok") is False:
        error = result.get("error")
        error_type = error.get("type") if isinstance(error, dict) else ""
        text = " ".join(str(x or "") for x in (
            result.get("reason"),
            result.get("blocked_reason"),
            result.get("status"),
            error_type,
            error if isinstance(error, str) else "",
        )).lower()

        if (
            error_type == "execution_authority_denied"
            or "runtime_execution_capability_not_validated" in text
            or "runtime_dispatcher_live_capability_required" in text
        ):
            result["status"] = "blocked"
            result["reason"] = "runtime_execution_capability_not_validated"
            result["blocked_reason"] = "runtime_execution_capability_not_validated"
            result["error"] = {
                "type": "execution_authority_denied",
                "reason": "runtime_execution_capability_not_validated",
            }

            if isinstance(task, dict):
                task["status"] = "blocked"
                task["blocked_reason"] = "runtime_execution_capability_not_validated"
                task["results"] = [{
                    "ok": False,
                    "status": "blocked",
                    "result": {
                        "executed": False,
                        "blocked": True,
                    },
                    "error": result["error"],
                }]
                result["task"] = task

    return result

TaskRunner.run_task_tick = _zero_run_task_tick_v6

if hasattr(TaskRunner, "run_task"):
    _zero_taskrunner_base_run_task_v6 = TaskRunner.run_task

    def _zero_run_task_v6(self, task, *args, **kwargs):
        result = _zero_taskrunner_base_run_task_v6(self, task, *args, **kwargs)
        if isinstance(result, dict) and isinstance(task, dict) and task.get("status") == "blocked":
            result["task"] = task
        return result

    TaskRunner.run_task = _zero_run_task_v6
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_RESULT_SHAPE_V6

_zero_scheduler_base_run_one_step_v6 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v6(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v6(self, *args, **kwargs)

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)

    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
        try:
            current_index = int(task.get("current_step_index", task.get("step_index", 0)))
        except Exception:
            current_index = 0

        result.setdefault("current_step_index", current_index)
        result.setdefault("next_step_index", current_index + 1)

        if task.get("operator_session_id"):
            result.setdefault("operator_session_id", task.get("operator_session_id"))

        task["current_step_index"] = result["next_step_index"]

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v6
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(TASK_RUNNER, "ZERO_PATCH_RUNTIME_GATE_FINAL_V6", TASK_PATCH)
append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_RESULT_SHAPE_V6", SCHED_PATCH)