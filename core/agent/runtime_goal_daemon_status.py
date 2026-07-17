from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping
from core.agent.runtime_goal_daemon_fairness import EXCLUDED_GOAL_STATUSES
from core.agent.runtime_goal_daemon_state import CONTRACT, VERSION, GoalDaemonStatus

def build_goal_daemon_status(state: Mapping[str, Any], goals: list[Mapping[str, Any]]) -> GoalDaemonStatus:
    counts = {status: sum(goal.get("goal_status") == status for goal in goals) for status in ("waiting_for_approval", "ready", "blocked")}
    value = {"contract": CONTRACT, "version": VERSION, "daemon_id": state["daemon_id"], "daemon_status": state["daemon_status"], "running": state["daemon_status"] == "running", "last_cycle_identity": state.get("last_cycle_id"), "last_cycle_timestamp": state.get("last_cycle_timestamp"), "cycle_count": state["cycle_count"], "active_goal_count": sum(goal.get("goal_status") not in EXCLUDED_GOAL_STATUSES for goal in goals), "waiting_approval_count": counts["waiting_for_approval"], "ready_goal_count": counts["ready"], "blocked_goal_count": counts["blocked"], "last_error": deepcopy(state.get("last_error")), "configuration_fingerprint": state["configuration_fingerprint"]}
    return GoalDaemonStatus(value)

__all__ = ["build_goal_daemon_status"]
