from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")
TARGETS = list(Path("core").rglob("*.py"))

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_FAILURE_READBACK_V14

_zero_scheduler_base_run_one_step_v14 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v14(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v14(self, *args, **kwargs)

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if isinstance(task, dict) and isinstance(result, dict):
        session_id = task.get("operator_session_id")
        if session_id:
            import builtins
            registry = getattr(builtins, "_zero_operator_completion_registry_v13", None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, "_zero_operator_completion_registry_v13", registry)

            task_id = str(task.get("id") or task.get("task_id") or "task")

            if result.get("ok") is True:
                registry.setdefault(str(session_id), set()).add(f"{task_id}-complete")
            elif result.get("ok") is False:
                failed = getattr(builtins, "_zero_operator_failure_registry_v14", None)
                if not isinstance(failed, dict):
                    failed = {}
                    setattr(builtins, "_zero_operator_failure_registry_v14", failed)
                failed[str(session_id)] = f"{task_id}-fail"

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v14
'''

OP_PATCH = r'''
# ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14

def _zero_patch_operator_get_session_v14(cls):
    if not hasattr(cls, "get_session"):
        return
    if getattr(cls.get_session, "_zero_v14_patched", False):
        return

    original = cls.get_session

    def wrapped(self, session_id, *args, **kwargs):
        session = original(self, session_id, *args, **kwargs)
        try:
            import builtins

            complete_registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            completions = complete_registry.get(str(session_id), set()) if isinstance(complete_registry, dict) else set()
            if session is not None and completions:
                completed = getattr(session, "completed_steps", None)
                if isinstance(completed, list):
                    for item in completions:
                        if item not in completed:
                            completed.append(item)

            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failure_registry.get(str(session_id)) if isinstance(failure_registry, dict) else None
            if session is not None and failed_step:
                if isinstance(session, dict):
                    session["failed_step"] = failed_step
                else:
                    setattr(session, "failed_step", failed_step)
        except Exception:
            pass

        return session

    wrapped._zero_v14_patched = True
    cls.get_session = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_session_v14(_obj)
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)

append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_OPERATOR_FAILURE_READBACK_V14", SCHED_PATCH)

for path in TARGETS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def get_session" in text and "operator" in text.lower():
        append_once(path, "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14", OP_PATCH)