from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


SAFE_PLANNER_ACTIONS = {
    "inspect_runtime_state",
    "inspect_execution_log",
    "inspect_trace",
    "inspect_result",
    "propose_repair_plan",
    "prepare_code_repair",
}

MUTATING_ACTIONS = {
    "execute_repair",
    "apply_patch",
    "write_file",
    "delete_file",
    "run_shell_command",
    "schedule_task",
    "modify_scheduler",
    "modify_planner",
    "auto_retry",
    "auto_repair",
    "auto_apply_patch",
    "auto_repair_without_confirmation",
}

HIGH_RISK_SCOPES = {
    "core",
    "scheduler",
    "planner",
    "system",
    "unknown",
    "code_execution_review",
}

TERMINAL_NO_REPAIR_MODES = {
    "no_repair",
    "observe_only",
}


def build_runtime_repair_planner_bridge(envelope: Any) -> Dict[str, Any]:
    """Build a read-only bridge payload from repair envelope to planner gate.

    This layer is intentionally side-effect free. It does not create tasks,
    call the planner, schedule repair work, write files, execute tools, or
    mutate the provided envelope. It only decides whether a later planner bridge
    would be allowed to receive a constrained repair intent.
    """
    safe_envelope = envelope if isinstance(envelope, Mapping) else {}

    task_id = _first_nonempty(safe_envelope.get("task_id"))
    status = _first_nonempty(safe_envelope.get("status"), "unknown")
    repair_mode = _first_nonempty(safe_envelope.get("repair_mode"), "manual_review")
    repair_scope = _first_nonempty(safe_envelope.get("repair_scope"), "unknown")
    repair_risk = _first_nonempty(safe_envelope.get("repair_risk"), "high")
    suggestion_type = _first_nonempty(safe_envelope.get("suggestion_type"), "unknown_suggestion")
    requires_confirmation = bool(safe_envelope.get("requires_confirmation", True))
    max_retry = _safe_int(safe_envelope.get("max_retry"), 0)

    allowed_actions = _string_list(safe_envelope.get("allowed_actions"))
    blocked_actions = _string_list(safe_envelope.get("blocked_actions"))
    inspection_targets = _string_list(safe_envelope.get("inspection_targets"))

    repair_intent = _build_repair_intent(
        suggestion_type=suggestion_type,
        repair_mode=repair_mode,
        repair_scope=repair_scope,
        repair_risk=repair_risk,
        allowed_actions=allowed_actions,
        inspection_targets=inspection_targets,
    )

    planner_allowed, reason = _decide_planner_allowed(
        repair_mode=repair_mode,
        repair_scope=repair_scope,
        repair_risk=repair_risk,
        requires_confirmation=requires_confirmation,
        allowed_actions=allowed_actions,
        blocked_actions=blocked_actions,
        max_retry=max_retry,
    )

    return {
        "ok": True,
        "task_id": task_id,
        "status": status,
        "bridge_mode": "read_only_planner_gate",
        "planner_allowed": planner_allowed,
        "requires_confirmation": requires_confirmation,
        "repair_intent": repair_intent,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "inspection_targets": inspection_targets,
        "repair_mode": repair_mode,
        "repair_scope": repair_scope,
        "repair_risk": repair_risk,
        "max_retry": max_retry,
        "reason": reason,
        "human_summary": _build_human_summary(
            planner_allowed=planner_allowed,
            repair_intent=repair_intent,
            repair_scope=repair_scope,
            repair_risk=repair_risk,
            requires_confirmation=requires_confirmation,
            reason=reason,
        ),
        "raw_envelope": freeze_runtime_export(envelope),
    }


def build_runtime_repair_planner_bridges(envelopes: Any) -> List[Dict[str, Any]]:
    """Build bridge payloads for a single envelope or a list of envelopes."""
    if isinstance(envelopes, list):
        return [build_runtime_repair_planner_bridge(item) for item in envelopes]
    return [build_runtime_repair_planner_bridge(envelopes)]


def _build_repair_intent(
    *,
    suggestion_type: str,
    repair_mode: str,
    repair_scope: str,
    repair_risk: str,
    allowed_actions: List[str],
    inspection_targets: List[str],
) -> Dict[str, Any]:
    normalized_allowed = [action for action in allowed_actions if action in SAFE_PLANNER_ACTIONS]
    if not normalized_allowed:
        normalized_allowed = ["inspect_runtime_state", "inspect_trace"]

    intent_type = _resolve_intent_type(suggestion_type, repair_mode, repair_scope)
    return {
        "intent_type": intent_type,
        "source": "runtime_repair_envelope",
        "scope": repair_scope,
        "risk": repair_risk,
        "mode": repair_mode,
        "allowed_actions": normalized_allowed,
        "inspection_targets": inspection_targets or ["runtime_state.json", "trace.json"],
        "mutation_allowed": False,
        "execution_allowed": False,
    }


def _resolve_intent_type(suggestion_type: str, repair_mode: str, repair_scope: str) -> str:
    lowered = " ".join([suggestion_type, repair_mode, repair_scope]).lower()
    if "no_repair" in lowered:
        return "no_repair"
    if "observe" in lowered:
        return "observe_runtime"
    if "python" in lowered or "code" in lowered:
        return "inspect_code_execution_failure"
    if "verification" in lowered or "verify" in lowered:
        return "inspect_verification_failure"
    if "file" in lowered or "path" in lowered:
        return "inspect_file_operation_failure"
    if "block" in lowered:
        return "inspect_blocked_task"
    return "inspect_runtime_failure"


def _decide_planner_allowed(
    *,
    repair_mode: str,
    repair_scope: str,
    repair_risk: str,
    requires_confirmation: bool,
    allowed_actions: List[str],
    blocked_actions: List[str],
    max_retry: int,
) -> tuple[bool, str]:
    lowered_mode = repair_mode.lower()
    lowered_scope = repair_scope.lower()
    lowered_risk = repair_risk.lower()
    blocked = {item.lower() for item in blocked_actions}
    allowed = {item.lower() for item in allowed_actions}

    if lowered_mode in TERMINAL_NO_REPAIR_MODES:
        return False, f"repair mode is {repair_mode}; planner bridge should observe only"

    if lowered_risk in {"critical"}:
        return False, "critical repair risk requires manual handling"

    if lowered_scope in HIGH_RISK_SCOPES and requires_confirmation:
        return False, f"scope {repair_scope} requires confirmation before planner bridge"

    if MUTATING_ACTIONS & allowed:
        return False, "allowed actions include mutating operations; planner bridge blocked"

    if "propose_repair_plan" not in allowed and "prepare_code_repair" not in allowed:
        return False, "no planner-safe repair planning action is allowed"

    if "schedule_task" not in blocked:
        return False, "schedule_task is not blocked; bridge boundary is incomplete"

    if max_retry > 0 and requires_confirmation:
        return False, "retry budget exists but confirmation is required"

    return True, "planner bridge may receive a read-only constrained repair intent"


def _build_human_summary(
    *,
    planner_allowed: bool,
    repair_intent: Mapping[str, Any],
    repair_scope: str,
    repair_risk: str,
    requires_confirmation: bool,
    reason: str,
) -> str:
    state = "allowed" if planner_allowed else "blocked"
    confirmation = "confirmation required" if requires_confirmation else "no confirmation required"
    intent_type = _first_nonempty(repair_intent.get("intent_type"), "repair_intent")
    return (
        f"Planner bridge is {state} for {intent_type}: "
        f"scope={repair_scope}, risk={repair_risk}, {confirmation}. Reason: {reason}."
    )


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        result: List[str] = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
