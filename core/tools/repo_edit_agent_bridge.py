"""Safe bridge for letting ZERO route explicit repo-edit tasks to repo_edit_tool.

This module is intentionally narrow:
- It does not choose files automatically.
- It only accepts an explicit file_path.
- It blocks high-risk core files for the first self-edit phase.
- It calls repo_edit through the existing tool registry / runner path.

This is F package: Agent Loop Tool Decision (semi-automatic).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.tools.tool_runner import run_tool

# Import side effect: registers "repo_edit" in the tool registry.
import core.tools.repo_edit_tool  # noqa: F401


BLOCKED_SELF_EDIT_PATHS = {
    "core/agent/agent_loop.py",
    "core/tasks/scheduler.py",
}

BLOCKED_PATH_KEYWORDS = (
    ".git/",
    ".env",
    "secret",
    "token",
    "credential",
    "__pycache__/",
    "venv/",
    ".venv/",
)


def normalize_repo_path(file_path: str | Path) -> str:
    """Normalize a repo-relative path into forward-slash form."""

    raw = str(file_path).strip().strip("\"'")
    raw = raw.replace("\\", "/")

    # If an absolute path under the current repo was supplied, convert it to a
    # repo-relative path. Absolute paths outside the repo remain absolute and
    # should be blocked by the lower repo_edit policy.
    path = Path(raw)
    if path.is_absolute():
        try:
            raw = str(path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
        except ValueError:
            raw = str(path).replace("\\", "/")

    while raw.startswith("./"):
        raw = raw[2:]

    return raw


def is_high_risk_repo_edit_path(file_path: str | Path) -> tuple[bool, str | None]:
    """Return whether a file path is blocked for F-package self-edit routing."""

    normalized = normalize_repo_path(file_path)
    lowered = normalized.lower()

    if normalized in BLOCKED_SELF_EDIT_PATHS:
        return True, f"F-package blocks direct self-edit of high-risk core file: {normalized}"

    for keyword in BLOCKED_PATH_KEYWORDS:
        if keyword in lowered:
            return True, f"F-package blocks unsafe path keyword '{keyword}' in: {normalized}"

    if normalized.startswith("../") or "/../" in normalized:
        return True, f"F-package blocks parent traversal path: {normalized}"

    return False, None


def extract_explicit_file_path(task_text: str) -> str | None:
    """Extract an explicit file path from simple task text.

    Supported forms:
    - file_path: workspace/example.py
    - file: workspace/example.py
    - path: workspace/example.py
    - modify file workspace/example.py
    - modify workspace/example.py
    """

    text = task_text.strip()

    labeled = re.search(
        r"(?:file_path|file|path)\s*[:=]\s*([A-Za-z0-9_./\\:\- ]+?\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg))",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        return normalize_repo_path(labeled.group(1).strip())

    modify_file = re.search(
        r"\bmodify\s+(?:file\s+)?([A-Za-z0-9_./\\:\- ]+?\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg))",
        text,
        flags=re.IGNORECASE,
    )
    if modify_file:
        return normalize_repo_path(modify_file.group(1).strip())

    return None


def should_route_to_repo_edit(task: dict[str, Any] | str) -> tuple[bool, dict[str, Any]]:
    """Decide whether an explicit task should route to repo_edit.

    This is intentionally conservative. It returns route=True only when a
    file_path is explicit. It does not infer target files from repo contents.
    """

    if isinstance(task, str):
        task_text = task
        file_path = extract_explicit_file_path(task_text)
        instruction = task_text
        mode = "append_text"
        payload: dict[str, Any] = {
            "file_path": file_path,
            "instruction": instruction,
            "mode": mode,
            "text": "\n# ZERO repo_edit bridge touched this file.\n",
        }
    else:
        task_text = str(task.get("task_text") or task.get("instruction") or "")
        file_path = task.get("file_path") or extract_explicit_file_path(task_text)
        payload = dict(task)
        payload["file_path"] = normalize_repo_path(file_path) if file_path else None
        payload.setdefault("instruction", task_text or "Controlled repo edit request.")

    if not payload.get("file_path"):
        return False, {
            "status": "blocked",
            "reason": "repo_edit requires an explicit file_path; automatic file selection is disabled.",
        }

    blocked, reason = is_high_risk_repo_edit_path(payload["file_path"])
    if blocked:
        return False, {
            "status": "blocked",
            "reason": reason,
            "file_path": payload["file_path"],
        }

    return True, payload


def run_repo_edit_decision(task: dict[str, Any] | str) -> dict[str, Any]:
    """Run the safe F-package repo-edit decision and tool call."""

    should_route, payload_or_reason = should_route_to_repo_edit(task)
    if not should_route:
        return {
            "status": "blocked",
            "tool": "repo_edit",
            "decision": payload_or_reason,
        }

    result = run_tool("repo_edit", payload_or_reason)
    return {
        "status": result.get("status", "unknown"),
        "tool": "repo_edit",
        "routed": True,
        "payload": {
            "file_path": payload_or_reason.get("file_path"),
            "mode": payload_or_reason.get("mode"),
            "instruction": payload_or_reason.get("instruction"),
        },
        "result": result,
    }


__all__ = [
    "BLOCKED_SELF_EDIT_PATHS",
    "extract_explicit_file_path",
    "is_high_risk_repo_edit_path",
    "normalize_repo_path",
    "run_repo_edit_decision",
    "should_route_to_repo_edit",
]
