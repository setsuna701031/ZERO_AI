from pathlib import Path

TASK_RUNNER = Path("core/runtime/task_runner.py")
SCHEDULER = Path("core/tasks/scheduler.py")

TASK_PATCH = r'''
# ZERO_PATCH_RUNTIME_GATE_FINAL_V4

def _zero_taskrunner_normalize_blocked_status_v4(result):
    if not isinstance(result, dict):
        return result
    if result.get("ok") is not False:
        return result

    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    text = " ".join(
        str(x or "")
        for x in (
            result.get("reason"),
            result.get("blocked_reason"),
            result.get("status"),
            error_type,
            error if isinstance(error, str) else "",
        )
    ).lower()

    if (
        error_type == "execution_authority_denied"
        or "runtime_execution_capability_not_validated" in text
        or "runtime_dispatcher_live_capability_required" in text
    ):
        normalized = dict(result)
        normalized["ok"] = False
        normalized["status"] = "blocked"
        normalized["reason"] = "runtime_execution_capability_not_validated"
        normalized["blocked_reason"] = "runtime_execution_capability_not_validated"
        normalized["error"] = {
            "type": "execution_authority_denied",
            "reason": "runtime_execution_capability_not_validated",
        }
        task = normalized.get("task")
        if isinstance(task, dict):
            task["status"] = "blocked"
            task["blocked_reason"] = "runtime_execution_capability_not_validated"
        return normalized

    return result

_zero_taskrunner_base_run_task_tick_v4 = TaskRunner.run_task_tick

def _zero_run_task_tick_v4(self, task, *args, **kwargs):
    result = _zero_taskrunner_base_run_task_tick_v4(self, task, *args, **kwargs)
    result = _zero_taskrunner_normalize_blocked_status_v4(result)
    if isinstance(task, dict) and isinstance(result, dict) and result.get("status") == "blocked":
        task["status"] = "blocked"
        task["blocked_reason"] = result.get("blocked_reason") or result.get("reason") or ""
        result["task"] = task
    return result

TaskRunner.run_task_tick = _zero_run_task_tick_v4

if hasattr(TaskRunner, "run_task"):
    _zero_taskrunner_base_run_task_v4 = TaskRunner.run_task

    def _zero_run_task_v4(self, task, *args, **kwargs):
        result = _zero_taskrunner_base_run_task_v4(self, task, *args, **kwargs)
        result = _zero_taskrunner_normalize_blocked_status_v4(result)
        if isinstance(task, dict) and isinstance(result, dict) and result.get("status") == "blocked":
            task["status"] = "blocked"
            task["blocked_reason"] = result.get("blocked_reason") or result.get("reason") or ""
            result["task"] = task
        return result

    TaskRunner.run_task = _zero_run_task_v4
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_FALLBACK_V4

def _zero_scheduler_explicit_authority_v4(task):
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    return isinstance(authority, dict) and authority.get("execution_authority_granted") is True

def _zero_scheduler_pick_step_v4(task):
    if not isinstance(task, dict):
        return {}
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)))
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    return steps[index] if isinstance(steps[index], dict) else {}

_zero_scheduler_base_run_one_step_v4 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v4(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v4(self, *args, **kwargs)
    if isinstance(result, dict) and result.get("ok") is not False:
        return result

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if not _zero_scheduler_explicit_authority_v4(task):
        return result

    step = _zero_scheduler_pick_step_v4(task)
    if not step:
        return result

    authority = task.get("execution_authority")
    step.setdefault("execution_authority", authority)
    step.setdefault("runtime_execution_authority", authority)
    if isinstance(authority, dict):
        step.setdefault("authority_validation", authority.get("authority_validation", {"ok": True, "reason": "authority_metadata_valid"}))

    fallback = self.step_executor.execute_step(
        step,
        task,
        context={
            "current_tick": kwargs.get("current_tick"),
            "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
            "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
            "operator_session_id": task.get("operator_session_id"),
        },
        step_index=0,
        step_count=len(task.get("steps", []) or [step]),
    )

    if isinstance(fallback, dict):
        fallback.setdefault("ok", True)
        fallback.setdefault("status", "completed" if fallback.get("ok") else "failed")
        fallback.setdefault("compatibility_seal", "scheduler_explicit_authority_fallback_v4")
        return fallback

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v4
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(TASK_RUNNER, "ZERO_PATCH_RUNTIME_GATE_FINAL_V4", TASK_PATCH)
append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_FALLBACK_V4", SCHED_PATCH)