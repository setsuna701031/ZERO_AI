from __future__ import annotations

from typing import Any


def update_step_progress(task: dict[str, Any], result: dict[str, Any]) -> None:
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    try:
        current = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
    except Exception:
        current = 0
    result.setdefault("current_step_index", current)
    result.setdefault("next_step_index", current + 1)
    task["current_step_index"] = result["next_step_index"]
