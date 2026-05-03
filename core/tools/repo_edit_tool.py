"""Compatibility adapter for registering repo_edit as a ZERO tool.

Keep this file thin.  The real sandbox/edit/diff logic lives in
core.repo_sandbox so scheduler.py and agent_loop.py do not absorb repo-edit
responsibilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.repo_sandbox.tool import RepoEditTool, run_repo_edit

TOOL_NAME = "repo_edit"
TOOL_DESCRIPTION = "Controlled repo edit in workspace/repo_sandbox with unified diff output."


def run(payload: dict[str, Any], *, repo_root: str | Path = ".") -> dict[str, Any]:
    """Generic adapter entry point."""

    return run_repo_edit(payload, repo_root=repo_root)


__all__ = ["RepoEditTool", "TOOL_NAME", "TOOL_DESCRIPTION", "run", "run_repo_edit"]
