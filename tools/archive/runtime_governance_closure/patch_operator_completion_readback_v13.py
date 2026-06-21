from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")
OPERATOR_RUNTIME = Path("core/runtime/operator_runtime.py")

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_READBACK_V13

_zero_scheduler_base_run_one_step_v13 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v13(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v13(self, *args, **kwargs)

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if isinstance(task, dict) and isinstance(result, dict) and result.get("ok") is True:
        session_id = task.get("operator_session_id")
        if session_id:
            import builtins
            registry = getattr(builtins, "_zero_operator_completion_registry_v13", None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, "_zero_operator_completion_registry_v13", registry)

            complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
            registry.setdefault(str(session_id), set()).add(complete_id)

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v13
'''

OP_PATCH = r'''
# ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13

def _zero_patch_operator_get_session_v13(cls):
    if not hasattr(cls, "get_session"):
        return
    if getattr(cls.get_session, "_zero_v13_patched", False):
        return

    original = cls.get_session

    def wrapped(self, session_id, *args, **kwargs):
        session = original(self, session_id, *args, **kwargs)

        try:
            import builtins
            registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            completions = registry.get(str(session_id), set()) if isinstance(registry, dict) else set()

            if session is not None and completions:
                completed = getattr(session, "completed_steps", None)
                if isinstance(completed, list):
                    for item in completions:
                        if item not in completed:
                            completed.append(item)

                if isinstance(session, dict):
                    completed = session.setdefault("completed_steps", [])
                    if isinstance(completed, list):
                        for item in completions:
                            if item not in completed:
                                completed.append(item)
        except Exception:
            pass

        return session

    wrapped._zero_v13_patched = True
    cls.get_session = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_session_v13(_obj)
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_READBACK_V13", SCHED_PATCH)
append_once(OPERATOR_RUNTIME, "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13", OP_PATCH)