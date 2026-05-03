"""Repo sandbox package for controlled repository edits.

This package provides a safe first step for ZERO to copy explicitly selected
repository files into a sandbox, edit only those sandbox copies, verify them,
and produce reviewable unified diffs without touching the original repo.
"""

from .controlled_edit import ControlledEditSession, ControlledEditResult
from .diff import build_unified_diff
from .policy import RepoSandboxPolicy, PolicyDecision, PolicyViolation
from .sandbox import RepoSandbox, SandboxFile
from .tool import RepoEditRequest, RepoEditTool, RepoEditToolResult, run_repo_edit

__all__ = [
    "ControlledEditSession",
    "ControlledEditResult",
    "RepoSandbox",
    "SandboxFile",
    "RepoSandboxPolicy",
    "PolicyDecision",
    "PolicyViolation",
    "build_unified_diff",
    "RepoEditRequest",
    "RepoEditTool",
    "RepoEditToolResult",
    "run_repo_edit",
]
