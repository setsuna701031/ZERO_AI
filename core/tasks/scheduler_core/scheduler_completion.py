from __future__ import annotations

from typing import Any


def task_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return kwargs.get("task") if "task" in kwargs else (args[0] if args else None)


def task_id(task: dict[str, Any]) -> str:
    return str(task.get("id") or task.get("task_id") or "task")

def mark_completed_steps_fallback(owner: Any, task: dict[str, Any], step_id: str) -> bool:
    if not isinstance(task, dict) or not step_id:
        return False
    session_id = task.get("operator_session_id")
    if not session_id:
        return False

    def mark(session: Any) -> bool:
        completed = getattr(session, "completed_steps", None)
        if isinstance(completed, list):
            if step_id not in completed:
                completed.append(step_id)
            return True

        if isinstance(session, dict):
            completed = session.setdefault("completed_steps", [])
            if isinstance(completed, list) and step_id not in completed:
                completed.append(step_id)
            return True

        return False

    seen: set[int] = set()

    def scan(obj: Any, depth: int = 0) -> bool:
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
        task.get("_zero_operator_runtime_ref"),
        getattr(task.get("_zero_operator_bootstrap_ref"), "operator_runtime", None),
        getattr(task.get("_zero_operator_bootstrap_ref"), "runtime", None),
        task.get("operator_bridge"),
        owner,
        getattr(owner, "step_executor", None),
        getattr(owner, "operator_bridge", None),
        getattr(getattr(owner, "step_executor", None), "operator_bridge", None),
    ]

    for root in roots:
        if scan(root):
            return True

    return False

