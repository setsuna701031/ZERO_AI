from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_operator_session import time_text

RECOVERY_STATUSES = {"not_required", "pending", "recovering", "recovered", "blocked", "failed"}
ITERATION_PHASES = {
    "idle", "scheduler_pending", "scheduler_completed", "replanning_pending",
    "replanning_completed", "event_publish_pending", "event_published",
    "iteration_completed",
}
RECOVERABLE_DAEMON_STATUSES = {"starting", "running", "blocked", "failed", "stopping"}
DEFAULT_RECOVERY_POLICY = {
    "daemon_recovery_enabled": True,
    "daemon_recovery_max_attempts": 3,
    "daemon_recover_blocked": True,
    "daemon_recover_failed": False,
    "daemon_replay_protection": True,
}


def recovery_policy(runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy = dict(DEFAULT_RECOVERY_POLICY)
    if isinstance(runtime_config, Mapping):
        for key in policy:
            if key in runtime_config:
                policy[key] = runtime_config[key]
    attempts = policy["daemon_recovery_max_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise ValueError("invalid_daemon_recovery_max_attempts")
    for key in policy:
        if key != "daemon_recovery_max_attempts" and not isinstance(policy[key], bool):
            raise ValueError(f"invalid_{key}")
    return policy


def normalize_recovery_state(state: Mapping[str, Any], *, now: Any = None) -> tuple[dict[str, Any], bool]:
    value = deepcopy(dict(state))
    defaults = {
        "recovery_status": "not_required", "recovery_attempts": 0,
        "recovery_failures": 0, "last_recovery_at": None,
        "last_recovery_result": None, "previous_daemon_status": None,
        "iteration_phase": "idle", "iteration_checkpoint": {},
        "last_completed_loop_iteration": 0,
        "last_scheduler_completed_iteration": 0,
        "last_replanning_completed_iteration": 0,
        "last_published_event_iteration": 0,
        "last_published_event_topic": None, "last_published_event_id": None,
    }
    changed = False
    for key, default in defaults.items():
        if key not in value:
            value[key] = deepcopy(default)
            changed = True
    if changed:
        value["updated_at"] = time_text(now)
    return value, changed


def validate_iteration_checkpoint(state: Mapping[str, Any]) -> list[str]:
    phase = state.get("iteration_phase")
    checkpoint = state.get("iteration_checkpoint")
    if phase not in ITERATION_PHASES:
        return ["invalid_iteration_phase"]
    if not isinstance(checkpoint, Mapping):
        return ["invalid_iteration_checkpoint"]
    if phase == "idle":
        return []
    loop = checkpoint.get("loop_iteration")
    if isinstance(loop, bool) or not isinstance(loop, int) or loop < 1:
        return ["invalid_checkpoint_loop_iteration"]
    if loop != state.get("loop_iteration"):
        return ["checkpoint_loop_iteration_mismatch"]
    return []


def recovery_decision(state: Mapping[str, Any], runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy = recovery_policy(runtime_config)
    status = state.get("daemon_status")
    reasons: list[str] = []
    recoverable = status in RECOVERABLE_DAEMON_STATUSES
    if status == "blocked" and not policy["daemon_recover_blocked"]:
        recoverable = False; reasons.append("blocked_recovery_disabled")
    if status == "failed" and not policy["daemon_recover_failed"]:
        recoverable = False; reasons.append("failed_recovery_disabled")
    if state.get("stop_requested"):
        recoverable = False; reasons.append("stop_requested")
    if state.get("pause_requested") or status == "paused":
        recoverable = False; reasons.append("operator_paused")
    if isinstance(state.get("failure"), Mapping) and state["failure"].get("critical") is True:
        recoverable = False; reasons.append("critical_failure")
    if not policy["daemon_recovery_enabled"]:
        recoverable = False; reasons.append("recovery_disabled")
    exhausted = int(state.get("recovery_attempts") or 0) >= policy["daemon_recovery_max_attempts"]
    if exhausted:
        recoverable = False; reasons.append("recovery_attempts_exhausted")
    checkpoint_reasons = validate_iteration_checkpoint(state)
    if checkpoint_reasons:
        recoverable = False; reasons.extend(checkpoint_reasons)
    return {"required": status in RECOVERABLE_DAEMON_STATUSES, "recoverable": recoverable,
            "recovery_attempts_exhausted": exhausted, "checkpoint_valid": not checkpoint_reasons,
            "reasons": reasons, "policy": policy}


def recovery_event_payload(state: Mapping[str, Any], recovery_result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fields = ("daemon_id", "previous_daemon_status", "recovery_status", "recovery_attempts",
              "recovery_failures", "iteration_phase", "loop_iteration",
              "last_completed_loop_iteration", "last_scheduler_completed_iteration",
              "last_replanning_completed_iteration", "last_published_event_iteration")
    payload = {key: deepcopy(state.get(key)) for key in fields}
    payload["recovery_result"] = deepcopy(dict(recovery_result)) if isinstance(recovery_result, Mapping) else None
    return payload


__all__ = ["DEFAULT_RECOVERY_POLICY", "ITERATION_PHASES", "RECOVERY_STATUSES",
           "RECOVERABLE_DAEMON_STATUSES", "normalize_recovery_state", "recovery_decision",
           "recovery_event_payload", "recovery_policy", "validate_iteration_checkpoint"]
