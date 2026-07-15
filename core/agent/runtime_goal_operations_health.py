from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.agent.runtime_goal_operations_references import ACTIVE_ENTRY_STATUSES
from core.agent.runtime_goal_operations_snapshot import runtime_budget_projection
from core.agent.runtime_long_horizon_goal import TERMINAL_GOALS

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def stalled_goal(goal: Mapping[str, Any], chains: list[Mapping[str, Any]]) -> tuple[bool, list[str]]:
    if goal.get("goal_status") in TERMINAL_GOALS or goal.get("goal_status") in {"paused", "stopped", "cancelled"}: return False, []
    progress = _mapping(goal.get("progress")); active = any(chain.get("entry_status") in ACTIVE_ENTRY_STATUSES for chain in chains); waiting = bool(progress.get("waiting_approval_milestones")); ready = bool(progress.get("next_ready_milestone_ids")); reasons = []
    if not ready and not active and not waiting: reasons.append("active_goal_has_no_ready_milestone_active_mission_or_approval")
    if int(goal.get("replan_count") or 0) < int(goal.get("max_replans") or 0) and (progress.get("failed_milestones") or progress.get("blocked_milestones")) and not active: reasons.append("failure_has_remaining_replan_budget_without_progression")
    return bool(reasons), reasons

def build_health(sources: Mapping[str, Any], reference_results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    issues = deepcopy(list(sources.get("errors") or [])); warnings = []; stalled = []; orphans = []; duplicates = []; global_owners: dict[tuple[str, str], list[dict[str, str]]] = {}
    budget = runtime_budget_projection(sources)
    if not budget["invariant_satisfied"]: issues.append({"reason": "active_missions_exceed_runtime_budget", "critical": True})
    for goal in sources.get("goals") or []:
        goal_id = str(goal["goal_id"]); refs = reference_results.get(goal_id) or {}; chains = refs.get("chains") or []
        orphans.extend(refs.get("issues") or []); duplicates.extend(refs.get("duplicates") or [])
        for chain in chains:
            for kind, key in (("mission", "mission_id"), ("session", "session_id")):
                if chain.get(key): global_owners.setdefault((kind, str(chain[key])), []).append({"goal_id": goal_id, "entry_id": str(chain.get("entry_id"))})
        is_stalled, reasons = stalled_goal(goal, chains)
        if is_stalled: stalled.append({"goal_id": goal_id, "reasons": reasons})
        if int(goal.get("replan_count") or 0) > int(goal.get("max_replans") or 0): issues.append({"goal_id": goal_id, "reason": "replan_limit_exceeded", "critical": True})
        if goal.get("goal_status") in TERMINAL_GOALS and any(chain.get("entry_status") in ACTIVE_ENTRY_STATUSES for chain in chains): issues.append({"goal_id": goal_id, "reason": "terminal_goal_has_active_mission", "critical": True})
        if goal.get("goal_status") in {"paused", "stopped", "cancelled"} and any(chain.get("entry_status") in {"selected", "preparing", "running"} for chain in chains): warnings.append({"goal_id": goal_id, "reason": "inactive_goal_has_progressing_mission"})
    for (kind, identity), owners in global_owners.items():
        if len({(item["goal_id"], item["entry_id"]) for item in owners}) > 1: duplicates.append({"type": f"duplicate_{kind}_ownership", "identity": identity, "owners": owners})
    unique_duplicates = {str(item): item for item in duplicates}; duplicates = list(unique_duplicates.values())
    issues.extend({**item, "critical": True} for item in orphans + duplicates)
    daemon = _mapping(sources.get("daemon")); daemon_status = daemon.get("daemon_status") or "not_initialized"
    if daemon.get("last_error"): issues.append({"reason": "daemon_last_critical_error", "detail": deepcopy(daemon.get("last_error")), "critical": True})
    critical = any(item.get("critical") for item in issues); degraded = bool(warnings or stalled)
    actions = []
    if orphans: actions.append("review invalid reference")
    if stalled: actions.append("inspect failed milestone")
    if any(_mapping(goal.get("progress")).get("waiting_approval_milestones") for goal in sources.get("goals") or []): actions.append("review approval")
    return {"healthy": not critical and not degraded, "ready": not critical, "degraded": degraded and not critical, "critical": critical, "issues": issues, "warnings": warnings, "checks": {"goal_store": not any(error.get("source") == "goal_store" for error in sources.get("errors") or []), "reference_integrity": not orphans and not duplicates, "runtime_budget_invariant": budget["invariant_satisfied"], "daemon_state": not any(error.get("source") == "goal_daemon" for error in sources.get("errors") or [])}, "runtime_budget_status": budget, "daemon_status": daemon_status, "goal_counts": {"total": len(sources.get("goals") or [])}, "stalled_goals": stalled, "orphan_references": orphans, "duplicate_references": duplicates, "invalid_fingerprints": [item for item in issues if "fingerprint" in str(item)], "unsafe_continuation_reasons": [item.get("reason") or item.get("error") for item in issues if item.get("critical")], "recommended_operator_actions": sorted(set(actions))}

__all__ = ["build_health", "stalled_goal"]
