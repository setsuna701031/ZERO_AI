from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")

PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V11

def _zero_scheduler_operator_completion_v11(self, task, result):
    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
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

    seen = set()

    def scan(obj, depth=0):
        if obj is None or depth > 8:
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

        if isinstance(obj, dict):
            if session_id in obj and mark(obj[session_id]):
                return True
            values = list(obj.values())
        else:
            values = []
            d = getattr(obj, "__dict__", None)
            if isinstance(d, dict):
                values.extend(d.values())

            for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
                sessions = getattr(obj, attr, None)
                if isinstance(sessions, dict):
                    session = sessions.get(session_id)
                    if session is not None and mark(session):
                        return True
                    values.extend(sessions.values())

        for value in values:
            if scan(value, depth + 1):
                return True

        return False

    roots = [
        self,
        getattr(self, "step_executor", None),
        getattr(self, "operator_bridge", None),
        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
    ]

    for root in roots:
        if scan(root):
            return

_zero_scheduler_base_run_one_step_v11 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v11(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v11(self, *args, **kwargs)
    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
    _zero_scheduler_operator_completion_v11(self, task, result)
    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v11
'''

text = SCHEDULER.read_text(encoding="utf-8")
if "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V11" not in text:
    SCHEDULER.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
    print("patched", SCHEDULER)
else:
    print("already patched", SCHEDULER)