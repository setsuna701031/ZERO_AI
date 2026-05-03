"""Bridge from natural-language task text to the repo_edit tool.

This is the G package boundary:
- It may parse explicit, safe workspace/ edit instructions.
- It may call the registered repo_edit tool.
- It must not choose files, inspect the repo, edit core files, or touch agent_loop.
"""

from __future__ import annotations

from typing import Any

from core.repo_sandbox.intent import parse_code_edit_intent
from core.tools.tool_runner import run_tool

# Import side effect: registers repo_edit.
import core.tools.repo_edit_tool  # noqa: F401


def run_code_edit_task(task_text: str) -> dict[str, Any]:
    """Run a conservative natural-language code-edit task.

    Returns a repo_edit-style result dictionary.
    """

    intent = parse_code_edit_intent(task_text)
    if intent.status != "ready":
        return {
            "status": "blocked",
            "reason": intent.reason,
            "file_path": intent.file_path,
        }

    payload = intent.to_payload()
    result = run_tool("repo_edit", payload)
    result.setdefault("intent", "code_edit")
    result.setdefault("file_path", payload["file_path"])
    return result
