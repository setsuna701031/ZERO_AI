from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")

PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_FAILED_STEP_V16

_zero_scheduler_base_run_one_step_v16 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v16(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v16(self, *args, **kwargs)

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if isinstance(task, dict) and isinstance(result, dict) and result.get("ok") is True:
        session_id = task.get("operator_session_id")
        if session_id:
            import builtins

            task_id = str(task.get("id") or task.get("task_id") or "task")
            sid = str(session_id)

            completions = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            already_completed = (
                isinstance(completions, dict)
                and sid in completions
                and bool(completions.get(sid))
            )

            if already_completed:
                failures = getattr(builtins, "_zero_operator_failure_registry_v14", None)
                if not isinstance(failures, dict):
                    failures = {}
                    setattr(builtins, "_zero_operator_failure_registry_v14", failures)
                failures[sid] = f"{task_id}-fail"

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v16
'''

text = SCHEDULER.read_text(encoding="utf-8")
if "ZERO_PATCH_SCHEDULER_OPERATOR_FAILED_STEP_V16" not in text:
    SCHEDULER.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
    print("patched", SCHEDULER)
else:
    print("already patched", SCHEDULER)