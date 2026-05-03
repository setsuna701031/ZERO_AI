"""Agent-facing adapter for controlled repo edit review flow.

I package boundary:
- Accepts an agent task text or payload.
- Produces a pending_review through the repo sandbox review flow.
- Never applies changes automatically.
- Never commits or pushes.
- Natural-language code edit remains limited by the lower review_flow / intent policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.repo_sandbox.review_flow import run_code_edit_review_task


AGENT_ACTION_AWAIT_REVIEW = "await_review_decision"
AGENT_ACTION_BLOCKED = "blocked"


def _task_text_from_input(task: str | dict[str, Any]) -> str:
    if isinstance(task, str):
        return task

    for key in ("task_text", "task", "goal", "instruction", "message"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return ""


def run_agent_repo_edit_review(
    task: str | dict[str, Any],
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    """Run a controlled code-edit request through review flow.

    The returned result is intended for agent_loop/scheduler integration, but this
    adapter does not import or mutate either component. It is a safe boundary
    object: agent layers can call it and then stop, waiting for explicit human
    apply/reject.
    """

    task_text = _task_text_from_input(task)

    if not task_text.strip():
        return {
            "status": "blocked",
            "agent_action": AGENT_ACTION_BLOCKED,
            "reason": "empty code edit task",
        }

    result = run_code_edit_review_task(task_text, repo_root=repo_root)
    status = result.get("status")

    if status == "pending_review":
        return {
            **result,
            "agent_action": AGENT_ACTION_AWAIT_REVIEW,
            "auto_apply": False,
            "requires_review": True,
        }

    return {
        **result,
        "agent_action": AGENT_ACTION_BLOCKED,
        "auto_apply": False,
        "requires_review": False,
    }


__all__ = [
    "AGENT_ACTION_AWAIT_REVIEW",
    "AGENT_ACTION_BLOCKED",
    "run_agent_repo_edit_review",
]
