from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


BLOCKED_PROPOSAL_ACTIONS = {
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
}


def build_runtime_repair_planner_proposal(bridge_gate: Any) -> Dict[str, Any]:
    """Build a read-only planner proposal from a repair planner bridge gate.

    This layer does not enqueue tasks, call the planner, execute tools, write
    files, mutate the supplied bridge gate, or approve any repair. It only
    converts a governed bridge decision into an operator/planner-facing proposal
    payload that a later layer may inspect.

    The proposal is deliberately conservative:
    - if planner_allowed is false, the proposal is blocked;
    - if confirmation is required, the proposal is review_only;
    - mutating and execution actions are always stripped from proposed actions;
    - blocked actions are preserved for auditability.
    """
    safe_gate = bridge_gate if isinstance(bridge_gate, Mapping) else {}

    task_id = _first_nonempty(safe_gate.get("task_id"))
    status = _first_nonempty(safe_gate.get("status"), "unknown")
    planner_allowed = bool(safe_gate.get("planner_allowed", False))
    requires_confirmation = bool(safe_gate.get("requires_confirmation", False))
    reason = _first_nonempty(
        safe_gate.get("reason"),
        safe_gate.get("human_summary"),
        "runtime repair planner proposal generated",
    )

    repair_intent = _mapping_or_empty(safe_gate.get("repair_intent"))
    intent_type = _first_nonempty(
        repair_intent.get("intent_type"),
        safe_gate.get("suggestion_type"),
        "inspect_runtime_failure",
    )
    repair_scope = _first_nonempty(
        repair_intent.get("scope"),
        safe_gate.get("repair_scope"),
        "unknown",
    )
    repair_risk = _first_nonempty(
        repair_intent.get("risk"),
        safe_gate.get("repair_risk"),
        "unknown",
    )
    repair_mode = _first_nonempty(
        repair_intent.get("mode"),
        safe_gate.get("repair_mode"),
        "manual_review",
    )

    allowed_actions = _unique(
        _string_list(safe_gate.get("allowed_actions"))
        + _string_list(repair_intent.get("allowed_actions"))
    )
    blocked_actions = _unique(
        _string_list(safe_gate.get("blocked_actions"))
        + _string_list(repair_intent.get("blocked_actions"))
        + sorted(BLOCKED_PROPOSAL_ACTIONS)
    )
    inspection_targets = _unique(
        _string_list(safe_gate.get("inspection_targets"))
        + _string_list(repair_intent.get("inspection_targets"))
    )

    proposed_actions = [
        action
        for action in allowed_actions
        if action not in BLOCKED_PROPOSAL_ACTIONS and action not in blocked_actions
    ]

    proposal_allowed = bool(planner_allowed and proposed_actions and not _is_hard_blocked(safe_gate))

    proposal_mode = _resolve_proposal_mode(
        proposal_allowed=proposal_allowed,
        requires_confirmation=requires_confirmation,
        repair_mode=repair_mode,
    )

    return {
        "ok": True,
        "task_id": task_id,
        "status": status,
        "proposal_type": "runtime_repair_planner_proposal",
        "proposal_mode": proposal_mode,
        "proposal_allowed": proposal_allowed,
        "planner_allowed": planner_allowed,
        "requires_confirmation": requires_confirmation,
        "repair_intent": {
            "intent_type": intent_type,
            "source": _first_nonempty(repair_intent.get("source"), "runtime_repair_planner_bridge"),
            "scope": repair_scope,
            "risk": repair_risk,
            "mode": repair_mode,
            "mutation_allowed": bool(repair_intent.get("mutation_allowed", False)),
            "execution_allowed": bool(repair_intent.get("execution_allowed", False)),
        },
        "proposed_actions": proposed_actions,
        "blocked_actions": blocked_actions,
        "inspection_targets": inspection_targets,
        "reason": reason,
        "human_summary": _build_human_summary(
            proposal_allowed=proposal_allowed,
            proposal_mode=proposal_mode,
            intent_type=intent_type,
            repair_scope=repair_scope,
            repair_risk=repair_risk,
            requires_confirmation=requires_confirmation,
            reason=reason,
        ),
        "raw_bridge_gate": freeze_runtime_export(bridge_gate),
    }


def build_runtime_repair_planner_proposals(bridge_gates: Any) -> List[Dict[str, Any]]:
    """Build proposals for a single bridge gate or a list of bridge gates."""
    if isinstance(bridge_gates, list):
        return [build_runtime_repair_planner_proposal(item) for item in bridge_gates]
    return [build_runtime_repair_planner_proposal(bridge_gates)]


def _resolve_proposal_mode(
    *,
    proposal_allowed: bool,
    requires_confirmation: bool,
    repair_mode: str,
) -> str:
    if not proposal_allowed:
        return "blocked"
    if requires_confirmation:
        return "review_only"
    if _safe_lower(repair_mode) in {"observe_only", "no_repair"}:
        return "observe_only"
    return "proposal_only"


def _is_hard_blocked(gate: Mapping[str, Any]) -> bool:
    if bool(gate.get("execution_allowed", False)):
        return True
    if bool(gate.get("mutation_allowed", False)):
        return True
    bridge_mode = _safe_lower(gate.get("bridge_mode"))
    if bridge_mode and bridge_mode not in {"read_only_planner_gate", "proposal_only", "review_only"}:
        return True
    return False


def _build_human_summary(
    *,
    proposal_allowed: bool,
    proposal_mode: str,
    intent_type: str,
    repair_scope: str,
    repair_risk: str,
    requires_confirmation: bool,
    reason: str,
) -> str:
    if not proposal_allowed:
        return (
            f"Planner proposal is blocked for {intent_type}: "
            f"scope={repair_scope}, risk={repair_risk}. Reason: {reason}."
        )

    confirmation = "requires confirmation" if requires_confirmation else "does not require confirmation"
    return (
        f"Planner proposal is available for {intent_type}: mode={proposal_mode}, "
        f"scope={repair_scope}, risk={repair_risk}, {confirmation}."
    )


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _safe_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
