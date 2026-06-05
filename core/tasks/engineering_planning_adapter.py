from __future__ import annotations

"""Planning-only boundary for EngineeringGoalRunner runtime requests.

This adapter lets the runtime orchestrator receive an initial goal lifecycle
without running continuation during planning. It owns no runtime loop,
scheduler, execution, or memory persistence responsibility.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_planning_loop import EngineeringPlanningLoop


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


class EngineeringPlanningOnlyAdapter:
    """Persist the initial lifecycle plan without continuation or memory load."""

    def __init__(self, *, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self._memory_store = NoEngineeringMemoryStore()
        self._planning_loop = EngineeringPlanningLoop(repo_root=self.repo_root, memory_store=self._memory_store)

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("engineering_planning_loop_payload_must_be_mapping")

        base_payload = copy.deepcopy(dict(payload))
        task = (
            copy.deepcopy(dict(base_payload.get("package")))
            if isinstance(base_payload.get("package"), Mapping)
            else copy.deepcopy(base_payload)
        )
        goal = _clean_text(task.get("goal") or base_payload.get("goal"), _clean_text(task.get("task_id"), "engineering_goal"))
        package_id = _clean_text(task.get("package_id") or task.get("task_id") or base_payload.get("task_id"), "engineering_goal")
        base_payload.update(
            {
                "task_type": _clean_text(base_payload.get("task_type"), "engineering_task"),
                "engineering_goal_lifecycle": True,
                "goal_id": _clean_text(task.get("goal_id") or base_payload.get("goal_id"), package_id),
                "task_id": package_id,
                "package_id": package_id,
                "goal": goal,
                "mode": _clean_text(task.get("mode") or base_payload.get("mode"), "execute"),
                "approval": bool(task.get("approval") if "approval" in task else base_payload.get("approval", True)),
            }
        )

        plan_event = self._planning_loop._plan_payload(
            base_payload,
            reason="initial_plan",
            lifecycle_state={},
            latest_result={},
            relevant_memory={},
        )
        base_payload["steps"] = copy.deepcopy(plan_event["steps"])
        base_payload["planned_task_buckets"] = copy.deepcopy(plan_event["task_buckets"])
        lifecycle = self._planning_loop._persist_initial_lifecycle(base_payload, plan_event)
        final_state = _clean_text(lifecycle.get("goal_state")).lower()
        return {
            "schema": "zero.engineering_planning_loop.v1",
            "ok": final_state == "completed",
            "mode": "engineering_planning_only_adapter",
            "goal_id": _clean_text(lifecycle.get("goal_id") or base_payload.get("goal_id")),
            "goal_state": final_state,
            "terminal": final_state in {"completed", "blocked", "failed", "cancelled"},
            "planning_events": [plan_event],
            "task_buckets": copy.deepcopy(lifecycle.get("task_buckets", plan_event["task_buckets"])),
            "goal_lifecycle": lifecycle,
            "engineering_goal_lifecycle": copy.deepcopy(lifecycle),
            "continuation_result": {},
            "memory": self._memory_store.load_relevant_memory(goal=goal),
            "adaptive_planning_decisions": [],
            "latest_adaptive_planning_decision": {},
            "replans": [],
            "replan_count": 0,
            "execution_path": {
                "planning_only_boundary": True,
                "orchestrates_only": True,
                "direct_execution": False,
                "sequence": "Planner -> GoalLifecycle",
                "continuation_coordinator_executes": False,
                "adaptive_evaluator_decides_only": True,
                "memory_persistence_owned_here": False,
                "runtime_orchestrator_owned_here": False,
                "scheduler_owned_here": False,
                "existing_aer_path_reused": True,
                "new_execution_path": False,
            },
            "updated_at": time.time(),
        }


class NoEngineeringMemoryStore:
    """No-op memory adapter for fresh goal runtime planning."""

    def load_relevant_memory(self, *, goal: str) -> dict[str, Any]:
        return {
            "schema": "zero.engineering_task.memory_retrieval.v1",
            "goal": _clean_text(goal),
            "records": [],
            "record_count": 0,
            "matches": [],
            "retrieval_methods": [],
            "memory_persistence_owned_here": False,
        }


__all__ = ["EngineeringPlanningOnlyAdapter", "NoEngineeringMemoryStore"]
