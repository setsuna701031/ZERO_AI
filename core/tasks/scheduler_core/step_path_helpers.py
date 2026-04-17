from __future__ import annotations

import os
from typing import Any, Dict


def normalize_step_scope(scope: Any) -> str:
    value = str(scope or "").strip().lower()
    if value in {"task", "shared", "auto"}:
        return value
    return "auto"


def resolve_step_path(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
) -> str:
    normalized = str(raw_path or "").replace("\\", "/").strip()
    step_scope = normalize_step_scope(scope)
    if os.path.isabs(normalized):
        return os.path.abspath(normalized)
    if normalized.startswith("workspace/shared/"):
        relative_part = normalized[len("workspace/shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))
    if normalized.startswith("shared/"):
        relative_part = normalized[len("shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))
    if step_scope == "shared":
        return os.path.abspath(os.path.join(shared_dir, normalized))
    return os.path.abspath(os.path.join(task_dir, normalized))


def resolve_read_path_with_fallback(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
) -> str:
    normalized = str(raw_path or "").replace("\\", "/").strip()
    step_scope = normalize_step_scope(scope)
    if os.path.isabs(normalized):
        return os.path.abspath(normalized)
    if normalized.startswith("workspace/shared/"):
        relative_part = normalized[len("workspace/shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))
    if normalized.startswith("shared/"):
        relative_part = normalized[len("shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))
    task_local = os.path.abspath(os.path.join(task_dir, normalized))
    shared_fallback = os.path.abspath(os.path.join(shared_dir, normalized))
    if step_scope == "task":
        return task_local
    if step_scope == "shared":
        return shared_fallback
    if os.path.exists(task_local):
        return task_local
    if os.path.exists(shared_fallback):
        return shared_fallback
    return task_local


def needs_scheduler_path_resolution(raw_path: str) -> bool:
    normalized = str(raw_path or "").replace("\\", "/").strip().lower()
    return bool(
        normalized.startswith("shared/")
        or normalized.startswith("workspace/shared/")
        or normalized.startswith("workspace/tasks/")
        or normalized.startswith("tasks/")
    )


def resolve_guard_target_path(
    raw_path: str,
    task_dir: str,
    shared_dir: str,
    scope: str = "auto",
    resolved_path: str = "",
) -> str:
    if resolved_path:
        normalized_resolved = os.path.abspath(str(resolved_path).strip())
        normalized_raw = str(raw_path or "").replace("\\", "/").strip().lower()
        step_scope = normalize_step_scope(scope)
        if step_scope == "shared":
            if normalized_raw.startswith("shared/") or normalized_raw.startswith("workspace/shared/"):
                return normalized_resolved
        elif step_scope == "task":
            if not (normalized_raw.startswith("shared/") or normalized_raw.startswith("workspace/shared/")):
                return normalized_resolved
        else:
            return normalized_resolved
    return resolve_step_path(raw_path=raw_path, task_dir=task_dir, shared_dir=shared_dir, scope=scope)


def extract_text_from_result_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("text", "content", "message", "response", "final_answer", "stdout", "checked_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        result_block = payload.get("result")
        if isinstance(result_block, dict):
            for key in ("text", "content", "message", "response", "final_answer", "stdout", "checked_text"):
                value = result_block.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return ""


def extract_text_from_previous_result(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return ""
    last = task.get("last_step_result")
    if isinstance(last, dict):
        direct = extract_text_from_result_payload(last)
        if direct:
            return direct
        result_block = last.get("result")
        direct = extract_text_from_result_payload(result_block)
        if direct:
            return direct
    results = task.get("results", [])
    if isinstance(results, list) and results:
        last_item = results[-1]
        direct = extract_text_from_result_payload(last_item)
        if direct:
            return direct
    return ""
