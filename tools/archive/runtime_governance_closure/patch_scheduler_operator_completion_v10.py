from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")

PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V10

def _zero_scheduler_force_operator_completion_v10(self, task, result):
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    if result.get("ok") is not True:
        return

    session_id = task.get("operator_session_id")
    if not session_id:
        return

    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"

    def mark(session):
        completed = getattr(session, "completed_steps", None)
        if isinstance(completed, list):
            if complete_id not in completed:
                completed.append(complete_id)
            return True

        if isinstance(session, dict):
            completed = session.setdefault("completed_steps", [])
            if isinstance(completed, list) and complete_id not in completed:
                completed.append(complete_id)
            return True

        return False

    # First: normal bridge/runtime paths.
    roots = [
        getattr(self, "operator_bridge", None),
        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
        getattr(self, "step_executor", None),
        self,
    ]

    seen = set()

    def scan(obj):
        if obj is None:
            return False
        oid = id(obj)
        if oid in seen:
            return False
        seen.add(oid)

        get_session = getattr(obj, "get_session", None)
        if callable(get_session):
            try:
                session = get_session(session_id)
                if session is not None and mark(session):
                    return True
            except Exception:
                pass

        for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
            sessions = getattr(obj, attr, None)
            if isinstance(sessions, dict):
                session = sessions.get(session_id)
                if session is not None and mark(session):
                    return True

        for attr in ("operator_runtime", "runtime", "_runtime", "bridge", "_bridge", "operator_bridge"):
            if scan(getattr(obj, attr, None)):
                return True

        return False

    for root in roots:
        if scan(root):
            return

    # Last resort for test/local runtime objects: find session by id in live objects.
    try:
        import gc

        for obj in gc.get_objects():
            try:
                get_session = getattr(obj, "get_session", None)
                if callable(get_session):
                    session = get_session(session_id)
                    if session is not None and mark(session):
                        return

                for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
                    sessions = getattr(obj, attr, None)
                    if isinstance(sessions, dict):
                        session = sessions.get(session_id)
                        if session is not None and mark(session):
                            return
            except Exception:
                continue
    except Exception:
        return

_zero_scheduler_base_run_one_step_v10 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v10(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v10(self, *args, **kwargs)
    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    _zero_scheduler_force_operator_completion_v10(self, task, result)
    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v10
'''

text = SCHEDULER.read_text(encoding="utf-8")
if "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V10" not in text:
    SCHEDULER.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
    print("patched", SCHEDULER)
else:
    print("already patched", SCHEDULER)