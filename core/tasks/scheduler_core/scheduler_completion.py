from __future__ import annotations

from typing import Any


def task_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return kwargs.get("task") if "task" in kwargs else (args[0] if args else None)


def task_id(task: dict[str, Any]) -> str:
    return str(task.get("id") or task.get("task_id") or "task")
