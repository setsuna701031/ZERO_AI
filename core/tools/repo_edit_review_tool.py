"""Tool adapter for H package review/apply flow."""

from __future__ import annotations

from typing import Any

from core.repo_sandbox.review_flow import decide_review, run_code_edit_review_task
from core.tools.registry import register_tool

TOOL_NAME = "repo_edit_review"
TOOL_DESCRIPTION = "Run a controlled repo edit into sandbox and return a pending human review."


def repo_edit_review_tool(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "review").strip().lower()

    if action == "review":
        task_text = str(payload.get("task_text") or payload.get("task") or "")
        if not task_text.strip():
            return {"status": "error", "reason": "task_text is required"}
        return run_code_edit_review_task(task_text)

    if action == "decide":
        review_id = str(payload.get("review_id") or "")
        decision = str(payload.get("decision") or "")
        if not review_id or not decision:
            return {"status": "error", "reason": "review_id and decision are required"}
        return decide_review(review_id, decision, reason=str(payload.get("reason") or ""))

    return {"status": "blocked", "reason": f"unknown action: {action}"}


register_tool(TOOL_NAME, repo_edit_review_tool)

__all__ = ["TOOL_NAME", "TOOL_DESCRIPTION", "repo_edit_review_tool"]
