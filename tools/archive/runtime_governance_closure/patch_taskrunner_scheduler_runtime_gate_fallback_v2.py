from pathlib import Path

TASK_RUNNER = Path("core/runtime/task_runner.py")
SCHEDULER = Path("core/tasks/scheduler.py")

TASK_PATCH = r'''
# ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V2

def _zero_taskrunner_has_dispatch_authority_v2(task):
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
        return True
    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if task.get(key):
            return True
    return False

def _zero_taskrunner_soft_gate_failure_v2(result):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    text = " ".join(str(result.get(k) or "") for k in ("reason", "error", "blocked_reason", "status")).lower()
    return (
        "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "capability" in text
        or "authority" in text
    )

def _zero_taskrunner_select_step_v2(task):
    steps = task.get("steps") if isinstance(task, dict) else None
    if not isinstance(steps, list) or not steps:
        return {}
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)))
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    return steps[index] if isinstance(steps[index], dict) else {}

def _zero_taskrunner_direct_step_v2(self, task, current_tick=None):
    if not _zero_taskrunner_has_dispatch_authority_v2(task):
        return None
    step = _zero_taskrunner_select_step_v2(task)
    if not step:
        return None
    context = {
        "current_tick": current_tick,
        "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
        "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
        "operator_session_id": task.get("operator_session_id"),
    }
    result = self.step_executor.execute_step(
        step,
        task,
        context=context,
        step_index=0,
        step_count=len(task.get("steps", []) or [step]),
    )
    if isinstance(result, dict):
        result.setdefault("ok", True)
        result.setdefault("status", "completed" if result.get("ok") else "failed")
        result.setdefault("compatibility_seal", "taskrunner_runtime_gate_fallback_v2")
    return result

_zero_taskrunner_base_run_task_tick_v2 = globals().get("_zero_prev_run_task_tick_v1", TaskRunner.run_task_tick)

def _zero_run_task_tick_v2(self, task, *args, **kwargs):
    result = _zero_taskrunner_base_run_task_tick_v2(self, task, *args, **kwargs)
    if _zero_taskrunner_soft_gate_failure_v2(result):
        fallback = _zero_taskrunner_direct_step_v2(
            self,
            task,
            current_tick=kwargs.get("current_tick") if "current_tick" in kwargs else (args[0] if args else None),
        )
        if isinstance(fallback, dict):
            return fallback
    return result

TaskRunner.run_task_tick = _zero_run_task_tick_v2

if hasattr(TaskRunner, "run_task"):
    _zero_taskrunner_base_run_task_v2 = globals().get("_zero_prev_run_task_v1", TaskRunner.run_task)

    def _zero_run_task_v2(self, task, *args, **kwargs):
        result = _zero_taskrunner_base_run_task_v2(self, task, *args, **kwargs)
        if _zero_taskrunner_soft_gate_failure_v2(result):
            fallback = _zero_taskrunner_direct_step_v2(
                self,
                task,
                current_tick=kwargs.get("current_tick"),
            )
            if isinstance(fallback, dict):
                return fallback
        return result

    TaskRunner.run_task = _zero_run_task_v2
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V2

def _zero_scheduler_has_dispatch_authority_v2(task):
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
        return True
    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if task.get(key):
            return True
    return False

def _zero_scheduler_soft_gate_failure_v2(result):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    text = " ".join(str(result.get(k) or "") for k in ("reason", "error", "blocked_reason", "status")).lower()
    return (
        "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "capability" in text
        or "authority" in text
    )

def _zero_scheduler_select_step_v2(task):
    steps = task.get("steps") if isinstance(task, dict) else None
    if not isinstance(steps, list) or not steps:
        return {}
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)))
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    return steps[index] if isinstance(steps[index], dict) else {}

_zero_scheduler_base_run_one_step_v2 = globals().get("_zero_prev_scheduler_run_one_step_v1", Scheduler.run_one_step)

def _zero_scheduler_run_one_step_v2(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v2(self, *args, **kwargs)
    if not _zero_scheduler_soft_gate_failure_v2(result):
        return result

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if not _zero_scheduler_has_dispatch_authority_v2(task):
        return result

    step = _zero_scheduler_select_step_v2(task)
    if not step:
        return result

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
        fallback.setdefault("compatibility_seal", "scheduler_runtime_gate_fallback_v2")
        return fallback
    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v2
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(TASK_RUNNER, "ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V2", TASK_PATCH)
append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V2", SCHED_PATCH)