from __future__ import annotations

from typing import Any, Dict


def build_github_outbox_input(task: Any = None, tool_input: Any = None) -> Dict[str, Any]:
    task_text = _task_text(task, tool_input)
    payload = {
        "task": task_text,
        "source": "github_outbox_adapter",
    }
    if isinstance(task, dict):
        payload["task_record"] = task
    if isinstance(tool_input, dict):
        payload["original_tool_input"] = tool_input
    return payload


def execute_github_outbox(
    *,
    tool_registry: Any,
    tool_input: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = tool_input if isinstance(tool_input, dict) else {}
    outbox_input = build_github_outbox_input(task=payload.get("task"), tool_input=payload)
    return tool_registry.execute_tool("github_outbox", outbox_input)


def _task_text(task: Any = None, tool_input: Any = None) -> str:
    if isinstance(task, dict):
        for key in ("title", "goal", "input", "user_input", "description"):
            value = task.get(key)
            if value:
                return str(value)
    if isinstance(tool_input, dict):
        for key in ("task", "goal", "input", "description"):
            value = tool_input.get(key)
            if value:
                return str(value)
    return "github outbox task"
