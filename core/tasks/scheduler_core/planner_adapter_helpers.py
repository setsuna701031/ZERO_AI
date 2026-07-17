from __future__ import annotations

from typing import Any, Dict, Optional

from core.tasks.scheduler_core.planner_execution_helpers import (
    _call_planner_like as _execution_call_planner_like,
    _normalize_external_plan as _execution_normalize_external_plan,
)
from core.tasks.scheduler_core.planner_policy_helpers import (
    _plan_goal_via_agent_planners as _policy_plan_goal_via_agent_planners,
    _plan_goal_via_forced_deterministic_planner as _policy_plan_goal_via_forced_deterministic_planner,
    _should_force_deterministic_task_planner as _policy_should_force_deterministic_task_planner,
)


def _should_force_deterministic_task_planner(self, goal: str) -> bool:
    return _policy_should_force_deterministic_task_planner(self, goal)


def _plan_goal_via_forced_deterministic_planner(self, goal: str) -> Optional[Dict[str, Any]]:
    return _policy_plan_goal_via_forced_deterministic_planner(self, goal)


def _plan_goal_via_agent_planners(
    self,
    goal: str,
    document_payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    return _policy_plan_goal_via_agent_planners(
        self,
        goal,
        document_payload=document_payload,
    )


def _call_planner_like(
    self,
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Dict[str, Any],
) -> Any:
    return _execution_call_planner_like(
        self,
        planner=planner,
        context=context,
        user_input=user_input,
        route=route,
    )


def _normalize_external_plan(self, plan: Any) -> Optional[Dict[str, Any]]:
    return _execution_normalize_external_plan(self, plan)
