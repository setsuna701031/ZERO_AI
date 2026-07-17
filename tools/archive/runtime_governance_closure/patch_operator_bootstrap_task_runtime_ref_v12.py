from pathlib import Path

TARGETS = [
    Path("core/runtime/operator_session_bootstrap.py"),
    Path("core/runtime/operator_bootstrap.py"),
    Path("core/runtime/operator_runtime.py"),
    Path("core/tasks/scheduler.py"),
]

BOOT_PATCH = r'''
# ZERO_PATCH_OPERATOR_BOOTSTRAP_TASK_RUNTIME_REF_V12

def _zero_patch_bootstrap_runtime_ref_v12(cls):
    if not hasattr(cls, "ensure_session_for_task"):
        return
    if getattr(cls.ensure_session_for_task, "_zero_v12_patched", False):
        return

    original = cls.ensure_session_for_task

    def wrapped(self, task, *args, **kwargs):
        result = original(self, task, *args, **kwargs)
        if isinstance(task, dict):
            runtime = (
                getattr(self, "operator_runtime", None)
                or getattr(self, "runtime", None)
                or getattr(self, "_runtime", None)
                or getattr(self, "session_runtime", None)
            )
            if runtime is not None:
                task["_zero_operator_runtime_ref"] = runtime
            task["_zero_operator_bootstrap_ref"] = self
        return result

    wrapped._zero_v12_patched = True
    cls.ensure_session_for_task = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_bootstrap_runtime_ref_v12(_obj)
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V12

_zero_scheduler_base_run_one_step_v12 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v12(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v12(self, *args, **kwargs)

    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
        return result

    session_id = task.get("operator_session_id")
    if not session_id:
        return result

    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"

    runtimes = [
        task.get("_zero_operator_runtime_ref"),
        getattr(task.get("_zero_operator_bootstrap_ref"), "operator_runtime", None),
        getattr(task.get("_zero_operator_bootstrap_ref"), "runtime", None),
        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
        getattr(self, "operator_bridge", None),
    ]

    for runtime in runtimes:
        if runtime is None:
            continue

        session = None
        get_session = getattr(runtime, "get_session", None)
        if callable(get_session):
            try:
                session = get_session(session_id)
            except Exception:
                session = None

        if session is None:
            for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
                sessions = getattr(runtime, attr, None)
                if isinstance(sessions, dict):
                    session = sessions.get(session_id)
                    if session is not None:
                        break

        if session is None:
            continue

        completed = getattr(session, "completed_steps", None)
        if isinstance(completed, list):
            if complete_id not in completed:
                completed.append(complete_id)
            return result

        if isinstance(session, dict):
            completed = session.setdefault("completed_steps", [])
            if isinstance(completed, list) and complete_id not in completed:
                completed.append(complete_id)
            return result

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v12
'''

for path in TARGETS:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    if path.as_posix().endswith("scheduler.py"):
        marker, patch = "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V12", SCHED_PATCH
    else:
        marker, patch = "ZERO_PATCH_OPERATOR_BOOTSTRAP_TASK_RUNTIME_REF_V12", BOOT_PATCH

    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)