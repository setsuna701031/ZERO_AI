from __future__ import annotations

import os
import shlex
from typing import Any, Callable, Dict, List, Optional


def infer_repair_source_path(step: Any, step_result: Any) -> str:
    if isinstance(step, dict):
        for key in ("repair_source_path", "source_path", "path", "target_path", "file_path"):
            value = step.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        command = str(step.get("command") or step.get("cmd") or "").strip()
        inferred = _infer_python_compile_path_from_command(command)
        if inferred:
            return inferred

    if isinstance(step_result, dict):
        for key in ("path", "resolved_path"):
            value = step_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        result = step_result.get("result")
        if isinstance(result, dict):
            for key in ("path", "resolved_path"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            nested = result.get("result")
            if isinstance(nested, dict):
                for key in ("path", "resolved_path"):
                    value = nested.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

    return ""


def _infer_python_compile_path_from_command(command: str) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text, posix=False)
    except Exception:
        parts = text.split()
    if len(parts) >= 4:
        lowered = [str(part).strip().strip('"\'').lower() for part in parts]
        for index in range(0, len(lowered) - 2):
            if lowered[index] in {"python", "python3", "py"} or lowered[index].endswith("python.exe"):
                if lowered[index + 1] == "-m" and lowered[index + 2] == "py_compile":
                    for candidate in parts[index + 3:]:
                        cleaned = str(candidate).strip().strip('"\'')
                        if cleaned.endswith(".py"):
                            return cleaned
    for token in parts:
        cleaned = str(token).strip().strip('"\'')
        if cleaned.endswith(".py"):
            return cleaned
    return ""


def read_repair_source_text(
    task: Dict[str, Any],
    state: Dict[str, Any],
    source_path: str,
    workspace_root: str,
    *,
    resolve_read_path: Optional[Callable[..., Any]] = None,
    read_text: Optional[Callable[..., str]] = None,
) -> str:
    _ = workspace_root
    if not source_path:
        return ""

    candidates: List[str] = []

    def add_candidate(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        try:
            normalized = os.path.abspath(text)
        except Exception:
            normalized = text
        if normalized not in candidates:
            candidates.append(normalized)

    if os.path.isabs(source_path):
        add_candidate(source_path)
    else:
        for base in (
            state.get("sandbox_dir"),
            state.get("task_dir"),
            task.get("sandbox_dir"),
            task.get("task_dir"),
            task.get("target_repo_root"),
            state.get("target_repo_root"),
        ):
            if isinstance(base, str) and base.strip():
                add_candidate(os.path.join(base, source_path))

    if callable(resolve_read_path):
        try:
            resolved = resolve_read_path(
                relative_path=source_path,
                task=task,
                prefer_scopes=("sandbox", "shared"),
                return_fallback_candidate_if_missing=True,
            )
            add_candidate(resolved)
        except Exception:
            pass

    for candidate in candidates:
        if os.path.exists(candidate) and os.path.isfile(candidate):
            try:
                if callable(read_text):
                    return read_text(candidate, default="")
            except Exception:
                continue
    return ""


def first_repair_action_path(repair_plan: Any) -> str:
    if not isinstance(repair_plan, dict):
        return ""
    actions = repair_plan.get("actions")
    if not isinstance(actions, list):
        return ""
    for action in actions:
        if isinstance(action, dict):
            path = str(action.get("path") or "").strip()
            if path:
                return path
    return ""


__all__ = [
    "infer_repair_source_path",
    "read_repair_source_text",
    "first_repair_action_path",
]
