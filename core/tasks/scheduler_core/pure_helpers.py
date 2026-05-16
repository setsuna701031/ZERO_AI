from __future__ import annotations

import re

from typing import Any, Dict, Optional

from core.tasks.scheduler_core.path_parser_helpers import _extract_file_path as _path_parser_extract_file_path


# Extracted from core/tasks/scheduler.py as pure helper functions.
# This module must remain free of Scheduler, StepExecutor, ExecutionGuard,
# transaction, verify, rollback, queue, and persistence side effects.


def _safe_int_for_runtime_gate(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _extract_task_id(task: Dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()


def _strip_quotes(text: str) -> str:
    value = str(text or "").strip()
    if len(value) >= 2:
        if value[0] == value[-1] and value[0] in {"'", '"', "“", "”", "‘", "’"}:
            return value[1:-1]
    return value


def _extract_file_path(text: str) -> Optional[str]:
    return _path_parser_extract_file_path(text)


def _canonicalize_steps_for_compare(steps: Any) -> List[Dict[str, Any]]:
    if not isinstance(steps, list):
        return []
    canonical: List[Dict[str, Any]] = []
    for item in steps:
        if not isinstance(item, dict):
            canonical.append({'type': str(item)})
            continue
        normalized: Dict[str, Any] = {}
        for key in sorted(item.keys()):
            value = item.get(key)
            normalized[key] = value.strip() if isinstance(value, str) else value
        canonical.append(normalized)
    return canonical
