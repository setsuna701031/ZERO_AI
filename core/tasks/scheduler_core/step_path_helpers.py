# core/tasks/scheduler_core/step_path_helpers.py
"""
Scheduler step path helpers.

This module keeps path resolution rules in one place.

Important path model:
- workspace/... is a global project workspace path.
- workspace/shared/... is the shared artifact area.
- shared/... is treated as workspace/shared/...
- sandbox/... is task-local sandbox path.
- plain relative filenames are task-local sandbox paths.

Why this exists:
The scheduler executes task steps inside a task sandbox, but file watcher /
document tasks often use logical workspace paths such as workspace/shared/a.txt.
Those logical workspace paths must NOT be resolved under task_dir/sandbox.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm_slash(path: Any) -> str:
    return _safe_str(path).replace("\\", "/")


def _is_windows_abs(path: str) -> bool:
    value = _norm_slash(path)
    return len(value) >= 3 and value[1:3] == ":/" and value[0].isalpha()


def _is_abs(path: str) -> bool:
    value = _safe_str(path)
    return bool(value and (os.path.isabs(value) or _is_windows_abs(value)))


def _project_root_from_workspace(shared_dir: str) -> str:
    shared_abs = os.path.abspath(_safe_str(shared_dir) or os.path.join("workspace", "shared"))
    workspace_root = os.path.dirname(shared_abs)
    project_root = os.path.dirname(workspace_root)
    return project_root or os.getcwd()


def _workspace_root_from_shared(shared_dir: str) -> str:
    shared_abs = os.path.abspath(_safe_str(shared_dir) or os.path.join("workspace", "shared"))
    return os.path.dirname(shared_abs)


def _resolve_workspace_path(raw_path: str, shared_dir: str) -> str:
    """
    Resolve workspace/... against the project root.

    Example:
        workspace/shared/a.txt -> E:/zero_ai/workspace/shared/a.txt
        workspace/inbox/a.txt  -> E:/zero_ai/workspace/inbox/a.txt
    """
    project_root = _project_root_from_workspace(shared_dir)
    normalized = _norm_slash(raw_path)

    if normalized.lower().startswith("workspace/"):
        rel = normalized[len("workspace/") :]
        return os.path.abspath(os.path.join(project_root, "workspace", *rel.split("/")))

    return os.path.abspath(raw_path)


def _resolve_shared_alias(raw_path: str, shared_dir: str) -> str:
    """
    Resolve shared/... against workspace/shared.
    """
    normalized = _norm_slash(raw_path)
    shared_abs = os.path.abspath(_safe_str(shared_dir) or os.path.join("workspace", "shared"))

    if normalized.lower() == "shared":
        return shared_abs

    if normalized.lower().startswith("shared/"):
        rel = normalized[len("shared/") :]
        return os.path.abspath(os.path.join(shared_abs, *rel.split("/")))

    return os.path.abspath(raw_path)


def _resolve_sandbox_alias(raw_path: str, task_dir: str) -> str:
    """
    Resolve sandbox/... under task sandbox directory.
    """
    normalized = _norm_slash(raw_path)
    task_abs = os.path.abspath(_safe_str(task_dir) or "")

    if normalized.lower() == "sandbox":
        return task_abs

    if normalized.lower().startswith("sandbox/"):
        rel = normalized[len("sandbox/") :]
        return os.path.abspath(os.path.join(task_abs, *rel.split("/")))

    return os.path.abspath(os.path.join(task_abs, raw_path))


def normalize_step_scope(scope: Any) -> str:
    value = _safe_str(scope).lower()
    if value in {"shared", "workspace", "task", "sandbox", "absolute", "auto"}:
        return value
    return "auto"


def needs_scheduler_path_resolution(raw_path: str) -> bool:
    path = _safe_str(raw_path)
    if not path:
        return False

    normalized = _norm_slash(path).lower()

    if normalized.startswith(("workspace/", "shared/", "sandbox/")):
        return True

    if _is_abs(path):
        return False

    return True


def resolve_step_path(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
) -> str:
    """
    Resolve a step path.

    Rules:
    1. absolute paths stay absolute
    2. workspace/... goes to project workspace root
    3. shared/... goes to workspace/shared
    4. scope == shared puts plain paths under shared_dir
    5. sandbox/... or plain paths go under task sandbox/task_dir
    """
    path = _safe_str(raw_path)
    if not path:
        return ""

    normalized = _norm_slash(path)
    lowered = normalized.lower()
    step_scope = normalize_step_scope(scope)

    if _is_abs(normalized):
        return os.path.abspath(normalized)

    if lowered.startswith("workspace/"):
        return _resolve_workspace_path(normalized, shared_dir)

    if lowered == "shared" or lowered.startswith("shared/"):
        return _resolve_shared_alias(normalized, shared_dir)

    if lowered == "sandbox" or lowered.startswith("sandbox/"):
        return _resolve_sandbox_alias(normalized, task_dir)

    if step_scope == "workspace":
        workspace_root = _workspace_root_from_shared(shared_dir)
        return os.path.abspath(os.path.join(workspace_root, *normalized.split("/")))

    if step_scope == "shared":
        shared_abs = os.path.abspath(_safe_str(shared_dir) or os.path.join("workspace", "shared"))
        return os.path.abspath(os.path.join(shared_abs, *normalized.split("/")))

    if step_scope in {"task", "sandbox", "auto"}:
        task_abs = os.path.abspath(_safe_str(task_dir) or "")
        return os.path.abspath(os.path.join(task_abs, *normalized.split("/")))

    return os.path.abspath(normalized)


def resolve_read_path_with_fallback(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
) -> str:
    """
    Resolve read path with safe fallback.

    Critical fix:
    - workspace/... must resolve to the global project workspace, not task sandbox.
    - workspace/shared/... must resolve to the shared artifact directory.
    - plain filenames may fall back to shared if they exist there.
    """
    path = _safe_str(raw_path)
    if not path:
        return ""

    normalized = _norm_slash(path)
    lowered = normalized.lower()
    step_scope = normalize_step_scope(scope)

    if _is_abs(normalized):
        return os.path.abspath(normalized)

    if lowered.startswith("workspace/"):
        return _resolve_workspace_path(normalized, shared_dir)

    if lowered == "shared" or lowered.startswith("shared/"):
        return _resolve_shared_alias(normalized, shared_dir)

    if lowered == "sandbox" or lowered.startswith("sandbox/"):
        return _resolve_sandbox_alias(normalized, task_dir)

    # Scope-specific direct resolution.
    if step_scope == "shared":
        return resolve_step_path(normalized, task_dir=task_dir, shared_dir=shared_dir, scope="shared")

    if step_scope == "workspace":
        return resolve_step_path(normalized, task_dir=task_dir, shared_dir=shared_dir, scope="workspace")

    # Auto fallback:
    # 1. task-local sandbox path
    # 2. shared path if it exists
    task_candidate = resolve_step_path(normalized, task_dir=task_dir, shared_dir=shared_dir, scope="task")
    if os.path.exists(task_candidate):
        return task_candidate

    shared_candidate = resolve_step_path(normalized, task_dir=task_dir, shared_dir=shared_dir, scope="shared")
    if os.path.exists(shared_candidate):
        return shared_candidate

    # Return task-local default to preserve previous behavior for newly-created task files.
    return task_candidate


def resolve_guard_target_path(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
    resolved_path: str = "",
) -> str:
    """
    Resolve the path used by ExecutionGuard.

    Keep it aligned with the actual resolved path when available.
    """
    if _safe_str(resolved_path):
        return os.path.abspath(_safe_str(resolved_path))

    return resolve_step_path(
        raw_path=raw_path,
        task_dir=task_dir,
        shared_dir=shared_dir,
        scope=scope,
    )


def extract_text_from_result_payload(payload: Any) -> str:
    """
    Extract best-effort text from nested step result payloads.
    """
    def _extract(value: Any, depth: int = 0) -> str:
        if depth > 8:
            return ""

        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            for key in (
                "text",
                "content",
                "message",
                "response",
                "answer",
                "final_answer",
                "stdout",
                "checked_text",
            ):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    return item

            for nested_key in (
                "result",
                "raw_result",
                "raw",
                "data",
                "payload",
                "previous_result",
                "last_result",
            ):
                nested = value.get(nested_key)
                text = _extract(nested, depth + 1)
                if text.strip():
                    return text

        if isinstance(value, list):
            for item in reversed(value):
                text = _extract(item, depth + 1)
                if text.strip():
                    return text

        return ""

    return _extract(payload)


def extract_text_from_previous_result(task: Dict[str, Any]) -> str:
    """
    Extract previous step text from task runtime fields.
    """
    if not isinstance(task, dict):
        return ""

    direct = extract_text_from_result_payload(task.get("last_step_result"))
    if direct.strip():
        return direct

    for key in ("step_results", "results", "execution_log"):
        items = task.get(key)
        if isinstance(items, list):
            for item in reversed(items):
                text = extract_text_from_result_payload(item)
                if text.strip():
                    return text

    return ""
