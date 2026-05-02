from __future__ import annotations

import copy
from typing import Any, Dict


DEFAULT_TOOL_BUDGET = {
    "max_loop_steps": 3,
    "max_tool_calls": 3,
    "max_same_tool_repeats": 1,
    "max_retries_per_tool": 1,
}

TERMINATION_PRIORITY = (
    "max_loop_steps",
    "max_tool_calls",
    "max_same_tool_repeats",
    "max_retries_per_tool",
)


def normalize_tool_budget(value: Any = None) -> Dict[str, int]:
    payload = value if isinstance(value, dict) else {}
    budget: Dict[str, int] = {}
    for key, default in DEFAULT_TOOL_BUDGET.items():
        try:
            budget[key] = max(0, int(payload.get(key, default)))
        except Exception:
            budget[key] = int(default)
    return budget


def evaluate_tool_budget(decision_input: Dict[str, Any] | None, budget: Any = None) -> Dict[str, Any]:
    payload = decision_input if isinstance(decision_input, dict) else {}
    limits = normalize_tool_budget(budget or payload.get("tool_budget"))

    used = {
        "loop_steps": _safe_int(payload.get("loop_steps"), _safe_int(payload.get("tool_decision_cycle"), 0)),
        "tool_calls": _safe_int(payload.get("tool_calls"), 0),
        "same_tool_repeats": _safe_int(payload.get("same_tool_repeats"), 0),
        "retries_for_tool": _safe_int(payload.get("retries_for_tool"), _infer_retries(payload)),
    }
    remaining = {
        "loop_steps": max(0, limits["max_loop_steps"] - used["loop_steps"]),
        "tool_calls": max(0, limits["max_tool_calls"] - used["tool_calls"]),
        "same_tool_repeats": max(0, limits["max_same_tool_repeats"] - used["same_tool_repeats"]),
        "retries_for_tool": max(0, limits["max_retries_per_tool"] - used["retries_for_tool"]),
    }

    checks = (
        ("max_loop_steps", used["loop_steps"], limits["max_loop_steps"]),
        ("max_tool_calls", used["tool_calls"], limits["max_tool_calls"]),
        ("max_same_tool_repeats", used["same_tool_repeats"], limits["max_same_tool_repeats"]),
        ("max_retries_per_tool", used["retries_for_tool"], limits["max_retries_per_tool"]),
    )
    for name, current, maximum in checks:
        if maximum >= 0 and current >= maximum:
            return {
                "ok": False,
                "recommendation": "STOP",
                "reason": f"{name}_exhausted",
                "termination_priority": list(TERMINATION_PRIORITY),
                "budget": copy.deepcopy(limits),
                "used": used,
                "budget_remaining": remaining,
            }

    return {
        "ok": True,
        "recommendation": "ALLOW",
        "reason": "budget_available",
        "termination_priority": list(TERMINATION_PRIORITY),
        "budget": copy.deepcopy(limits),
        "used": used,
        "budget_remaining": remaining,
    }


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _infer_retries(payload: Dict[str, Any]) -> int:
    failures = payload.get("previous_failures")
    if not isinstance(failures, list):
        return 0
    requested_tool = str(payload.get("requested_tool") or "").strip()
    if not requested_tool:
        return len(failures)
    count = 0
    for item in failures:
        if isinstance(item, dict) and str(item.get("tool") or "").strip() == requested_tool:
            count += 1
    return count
