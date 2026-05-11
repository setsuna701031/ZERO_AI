from __future__ import annotations

import re

from typing import Any, Dict, Optional


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
    m = re.search(r"([A-Za-z0-9_\\\-./\\\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None