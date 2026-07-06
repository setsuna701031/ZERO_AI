from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping

from core.runtime.runtime_goal_intake import (
    adapt_goal_to_runtime_work_package,
    build_goal_intake_record,
)
from core.runtime.runtime_operator_config import RuntimeOperatorConfig


RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA = "zero.runtime.goal_session_launch.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: str) -> str:
    joined = "|".join(_text(part) for part in parts)
    fragment = sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{fragment}"


def _config_dict(config: Any) -> dict[str, Any]:
    if isinstance(config, RuntimeOperatorConfig):
        return config.to_dict()
    return _mapping(config)


def validate_runtime_launch_config(config: Any) -> dict[str, Any]:
    data = _config_dict(config)
    mode = _text(data.get("runtime_mode")).lower()
    max_tick = data.get("max_tick_limit")
    checkpoint_path = _text(data.get("checkpoint_path"))
    problems: list[str] = []

    try:
        tick_limit = int(max_tick)
    except (TypeError, ValueError):
        tick_limit = 0

    if mode not in {"manual", "autonomous"}:
        problems.append("invalid_runtime_mode")
    if tick_limit <= 0:
        problems.append("invalid_max_tick_limit")
    if not checkpoint_path:
        problems.append("missing_checkpoint_path")

    return {
        "schema": RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA + ".config_validation",
        "config_valid": not problems,
        "runtime_mode": mode,
        "max_tick_limit": tick_limit,
        "checkpoint_path": checkpoint_path,
        "problems": problems,
        "denial_reason": problems[0] if problems else "",
        "runtime_state_mutated": False,
        "task_executed": False,
    }


def build_runtime_session_launch_request(
    goal_text: Any,
    config: Any,
    *,
    explicit_manual_mode: bool = False,
    emergency_stop_active: bool = False,
    operator_id: str = "zero-runtime-operator",
) -> dict[str, Any]:
    goal = build_goal_intake_record(goal_text, operator_id=operator_id)
    work_package = adapt_goal_to_runtime_work_package(goal)
    config_validation = validate_runtime_launch_config(config)
    runtime_mode = config_validation["runtime_mode"]

    launch_id = (
        _stable_id("runtime-session-launch", goal.get("goal_id"), work_package.get("work_package_id"))
        if goal.get("goal_valid") and work_package.get("work_package_created")
        else ""
    )

    return {
        "schema": RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA,
        "launch_request_id": launch_id,
        "goal": goal,
        "work_package": work_package,
        "config_validation": config_validation,
        "runtime_mode": runtime_mode,
        "explicit_manual_mode": explicit_manual_mode is True,
        "emergency_stop_active": emergency_stop_active is True,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def evaluate_session_launch_admission(launch_request: Any) -> dict[str, Any]:
    request = _mapping(launch_request)
    goal = _mapping(request.get("goal"))
    work_package = _mapping(request.get("work_package"))
    config = _mapping(request.get("config_validation"))
    runtime_mode = _text(request.get("runtime_mode")).lower()
    explicit_manual = request.get("explicit_manual_mode") is True

    if not request:
        denial = "missing_launch_request"
        admitted = False
    elif goal.get("goal_valid") is not True:
        denial = goal.get("denial_reason") or "goal_not_valid"
        admitted = False
    elif work_package.get("work_package_created") is not True:
        denial = work_package.get("denial_reason") or "work_package_not_created"
        admitted = False
    elif config.get("config_valid") is not True:
        denial = config.get("denial_reason") or "invalid_config"
        admitted = False
    elif request.get("emergency_stop_active") is True:
        denial = "emergency_stop_active"
        admitted = False
    elif runtime_mode == "manual" and not explicit_manual:
        denial = "manual_mode_requires_explicit_launch"
        admitted = False
    elif runtime_mode not in {"manual", "autonomous"}:
        denial = "invalid_runtime_mode"
        admitted = False
    else:
        denial = ""
        admitted = True

    runtime_session_id = (
        _stable_id(
            "runtime-session",
            goal.get("goal_id"),
            work_package.get("work_package_id"),
            runtime_mode,
        )
        if admitted
        else ""
    )

    return {
        "schema": RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA + ".admission",
        "launch_admitted": admitted,
        "launch_request_id": request.get("launch_request_id") or "",
        "goal_id": goal.get("goal_id") or "",
        "work_package_id": work_package.get("work_package_id") or "",
        "runtime_session_id": runtime_session_id,
        "runtime_mode": runtime_mode,
        "autonomous_start_requested": admitted and runtime_mode == "autonomous",
        "manual_start_requested": admitted and runtime_mode == "manual",
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


def launch_goal_session(
    goal_text: Any,
    config: Any,
    *,
    explicit_manual_mode: bool = False,
    emergency_stop_active: bool = False,
    operator_id: str = "zero-runtime-operator",
) -> dict[str, Any]:
    request = build_runtime_session_launch_request(
        goal_text,
        config,
        explicit_manual_mode=explicit_manual_mode,
        emergency_stop_active=emergency_stop_active,
        operator_id=operator_id,
    )
    admission = evaluate_session_launch_admission(request)
    return {
        "schema": RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA + ".result",
        "ok": admission["launch_admitted"],
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "runtime_session": {
            "runtime_session_id": admission["runtime_session_id"],
            "goal_id": admission["goal_id"],
            "work_package_id": admission["work_package_id"],
            "launch_admitted": admission["launch_admitted"],
            "queue_admission_ready": admission["launch_admitted"],
        },
        "launch_admitted": admission["launch_admitted"],
        "autonomous_start_requested": admission["autonomous_start_requested"],
        "denial_reason": admission["denial_reason"],
        "launch_request": request,
        "launch_admission": admission,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
    }


__all__ = [
    "RUNTIME_GOAL_SESSION_LAUNCH_SCHEMA",
    "validate_runtime_launch_config",
    "build_runtime_session_launch_request",
    "evaluate_session_launch_admission",
    "launch_goal_session",
]
