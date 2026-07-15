from __future__ import annotations
from copy import deepcopy
from typing import Any

from core.agent.runtime_goal_daemon_fairness import EXCLUDED_GOAL_STATUSES

def progress_goal(controller: Any, goal_id: str, *, mission_budget: int, replan_budget: int, now: Any = None) -> dict[str, Any]:
    recovered = controller.recover(goal_id, now=now); run_result = None; replanned = False
    if recovered["goal_status"] != "waiting_for_approval" and mission_budget > 0 and recovered["goal_status"] not in EXCLUDED_GOAL_STATUSES:
        run_result = controller.run(goal_id, max_milestones=1, max_missions=mission_budget, max_iterations=max(2, mission_budget * 4), idle_exit=True, now=now)
        current = controller.show(goal_id)
        if current["goal_status"] in {"blocked", "failed"} and replan_budget > 0 and current["replan_count"] < current["max_replans"]:
            controller.replan(goal_id, reason="goal_daemon_bounded_failure_replan", now=now); replanned = True
    current = controller.show(goal_id); processed = list((run_result or {}).get("processed_entry_ids") or [])
    return {"goal_id": goal_id, "post_goal_fingerprint": current["goal_fingerprint"], "goal_status": current["goal_status"], "run_result": deepcopy(run_result), "processed_entry_ids": processed, "mission_started_count": len(processed), "replanned": replanned, "recovered": True}

__all__ = ["progress_goal"]
