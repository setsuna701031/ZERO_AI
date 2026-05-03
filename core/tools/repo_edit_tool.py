"""Compatibility adapter for registering repo_edit as a ZERO tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.repo_sandbox.tool import RepoEditTool, run_repo_edit
from core.tools.registry import register_tool

TOOL_NAME = "repo_edit"
TOOL_DESCRIPTION = (
    "Controlled repo edit in workspace/repo_sandbox with unified diff output."
)


def run(payload: dict[str, Any], *, repo_root: str | Path = ".") -> dict[str, Any]:
    return run_repo_edit(payload, repo_root=repo_root)


def repo_edit_tool(payload: dict[str, Any]) -> dict[str, Any]:
    return run_repo_edit(payload, repo_root=".")


register_tool(TOOL_NAME, repo_edit_tool)

__all__ = [
    "RepoEditTool",
    "TOOL_NAME",
    "TOOL_DESCRIPTION",
    "run",
    "run_repo_edit",
    "repo_edit_tool",
]