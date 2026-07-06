from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_GOAL_INTAKE_SCHEMA = "zero.runtime.goal_intake.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _stable_id(prefix: str, value: str) -> str:
    fragment = sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{fragment}"


def build_goal_intake_record(
    goal_text: Any,
    *,
    operator_id: str = "zero-runtime-operator",
) -> dict[str, Any]:
    goal = _text(goal_text)
    valid = bool(goal)
    return {
        "schema": RUNTIME_GOAL_INTAKE_SCHEMA,
        "goal_id": _stable_id("runtime-goal", goal) if valid else "",
        "goal_text": goal,
        "operator_id": _text(operator_id),
        "goal_valid": valid,
        "denial_reason": "" if valid else "empty_goal_text",
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def adapt_goal_to_runtime_work_package(goal_record: Any) -> dict[str, Any]:
    goal = _mapping(goal_record)
    if not goal:
        return {
            "schema": RUNTIME_GOAL_INTAKE_SCHEMA + ".work_package",
            "work_package_created": False,
            "work_package_id": "",
            "goal_id": "",
            "goal_text": "",
            "denial_reason": "missing_goal_record",
            "runtime_state_mutated": False,
            "task_executed": False,
            "direct_dispatch_requested": False,
        }
    if goal.get("goal_valid") is not True:
        return {
            "schema": RUNTIME_GOAL_INTAKE_SCHEMA + ".work_package",
            "work_package_created": False,
            "work_package_id": "",
            "goal_id": goal.get("goal_id") or "",
            "goal_text": goal.get("goal_text") or "",
            "denial_reason": goal.get("denial_reason") or "goal_not_valid",
            "runtime_state_mutated": False,
            "task_executed": False,
            "direct_dispatch_requested": False,
        }

    goal_id = _text(goal.get("goal_id"))
    return {
        "schema": RUNTIME_GOAL_INTAKE_SCHEMA + ".work_package",
        "work_package_created": True,
        "work_package_id": _stable_id("runtime-work-package", goal_id),
        "goal_id": goal_id,
        "goal_text": _text(goal.get("goal_text")),
        "operator_id": _text(goal.get("operator_id")),
        "work_package_status": "launch_ready",
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "denial_reason": "",
    }


__all__ = [
    "RUNTIME_GOAL_INTAKE_SCHEMA",
    "build_goal_intake_record",
    "adapt_goal_to_runtime_work_package",
]
