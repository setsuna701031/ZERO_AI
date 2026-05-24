from __future__ import annotations

"""Scheduler runtime contract adapter.

This module is the narrow compatibility surface used by external-facing
runtime/agent layers that need scheduler-owned summary helpers without directly
importing ``core.tasks.scheduler``.

Boundary rule:
- Agent-facing code imports this adapter only.
- The adapter remains inside ``core.tasks`` and may delegate to scheduler-owned
  compatibility helpers.
- The adapter does not enqueue tasks, execute steps, mutate runtime state, or
  bypass governance gates.
"""

import copy
from typing import Any, Dict


def _scheduler_module() -> Any:
    from core.tasks import scheduler as scheduler_module

    return scheduler_module


def _safe_summary(function_name: str, payload: Any) -> Dict[str, Any]:
    try:
        function = getattr(_scheduler_module(), function_name, None)
        if not callable(function):
            return {}
        summary = function(payload)
    except Exception:
        return {}
    return copy.deepcopy(summary) if isinstance(summary, dict) else {}


def governed_continuation_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7333_governed_continuation_summary", payload)


def governed_self_repair_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7334_governed_self_repair_summary", payload)


def controlled_mutation_bridge_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7335_controlled_mutation_bridge_summary", payload)


__all__ = [
    "governed_continuation_summary",
    "governed_self_repair_summary",
    "controlled_mutation_bridge_summary",
]
