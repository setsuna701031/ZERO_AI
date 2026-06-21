from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")

PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V9

def _zero_scheduler_force_operator_completion_v9(self, task, result):
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    if result.get("ok") is not True:
        return

    session_id = task.get("operator_session_id")
    if not session_id:
        return

    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"

    bridge = (
        getattr(getattr(self, "step_executor", None), "operator_bridge", None)
        or getattr(self, "operator_bridge", None)
        or task.get("operator_bridge")
    )

    runtimes = []
    if bridge is not None:
        for name in ("operator_runtime", "runtime", "_runtime"):
            value = getattr(bridge, name, None)
            if value is not None:
                runtimes.append(value)
        runtimes.append(bridge)

    for runtime in runtimes:
        session = None

        get_session = getattr(runtime, "get_session", None)
        if callable(get_session):
            try:
                session = get_session(session_id)
            except Exception:
                session = None

        if session is None:
            for attr in ("sessions", "_sessions"):
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
            return

        if isinstance(session, dict):
            completed = session.setdefault("completed_steps", [])
            if isinstance(completed, list) and complete_id not in completed:
                completed.append(complete_id)
            return

_zero_scheduler_base_run_one_step_v9 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v9(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v9(self, *args, **kwargs)
    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    _zero_scheduler_force_operator_completion_v9(self, task, result)
    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v9
'''

text = SCHEDULER.read_text(encoding="utf-8")
if "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V9" not in text:
    SCHEDULER.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
    print("patched", SCHEDULER)
else:
    print("already patched", SCHEDULER)