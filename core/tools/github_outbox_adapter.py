from __future__ import annotations

import re
from typing import Any, Dict


GITHUB_OUTBOX_KEYWORDS = (
    "commit",
    "pull request",
    "github",
    "publish",
)


def should_use_github_outbox(task: Any = None, tool_input: Any = None) -> bool:
    task_data = task if isinstance(task, dict) else {}
    if _task_type(task_data) == "github_outbox":
        return True

    text = _combined_text(task, tool_input).lower()
    return any(keyword in text for keyword in GITHUB_OUTBOX_KEYWORDS) or re.search(r"\bpr\b", text) is not None


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


def execute_github_outbox_if_needed(
    *,
    tool_registry: Any,
    tool_name: str = "",
    tool_input: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    payload = tool_input if isinstance(tool_input, dict) else {}
    task = payload.get("task")

    explicit_tool = str(tool_name or "").strip().lower() == "github_outbox"
    if not explicit_tool and not should_use_github_outbox(task=task, tool_input=payload):
        return None

    outbox_input = build_github_outbox_input(task=task, tool_input=payload)
    return tool_registry.execute_tool("github_outbox", outbox_input)


def build_github_outbox_step(task: Dict[str, Any]) -> Dict[str, Any] | None:
    if not should_use_github_outbox(task=task):
        return None
    return {
        "type": "tool",
        "tool_name": "github_outbox",
        "tool_input": build_github_outbox_input(task=task),
    }


def _task_type(task: Dict[str, Any]) -> str:
    return str(task.get("type") or task.get("task_type") or "").strip().lower()


def _combined_text(task: Any = None, tool_input: Any = None) -> str:
    chunks = []
    for value in (task, tool_input):
        if isinstance(value, dict):
            for key in ("title", "goal", "input", "user_input", "task", "description", "type", "task_type"):
                if value.get(key) is not None:
                    chunks.append(str(value.get(key)))
        elif value is not None:
            chunks.append(str(value))
    return "\n".join(chunks)


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
