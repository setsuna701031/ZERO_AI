from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from core.planning.planner import Planner
from core.tasks.scheduler_core.planner_execution_helpers import (
    _call_planner_like as _execution_call_planner_like,
    _normalize_external_plan as _execution_normalize_external_plan,
)


def _should_force_deterministic_task_planner(self, goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False

    shared_markers = [
        "workspace/shared/",
        "shared/",
        "workspace\\shared\\",
        "shared\\",
    ]
    verify_markers = [
        " verify ",
        " verifies ",
        " verified ",
        " verify",
        "verifies the file exists",
        "verify the file exists",
        "check that",
        "confirm that",
        "contains",
        "equals",
        "exists",
        "????",
        "check",
        "????",
    ]

    if any(marker in text for marker in shared_markers):
        return True
    return any(marker in text for marker in verify_markers)


def _plan_goal_via_forced_deterministic_planner(self, goal: str) -> Optional[Dict[str, Any]]:
    context = {
        "user_input": goal,
        "workspace": self.workspace_dir,
    }
    route = {
        "mode": "task",
        "task": True,
    }

    planners: List[Any] = []

    agent_loop = getattr(self, "agent_loop", None)
    deterministic_planner = getattr(agent_loop, "planner", None) if agent_loop is not None else None
    if deterministic_planner is not None:
        planners.append(deterministic_planner)

    try:
        planners.append(
            Planner(
                workspace_dir=self.workspace_dir,
                workspace_root=self.workspace_dir,
                debug=bool(getattr(self, "debug", False)),
            )
        )
    except Exception:
        pass

    seen = set()
    unique_planners: List[Any] = []
    for planner in planners:
        if planner is None:
            continue
        pid = id(planner)
        if pid in seen:
            continue
        seen.add(pid)
        unique_planners.append(planner)

    for planner in unique_planners:
        plan = None
        plan_fn = getattr(planner, "plan", None)
        if callable(plan_fn):
            try:
                plan = plan_fn(context=context, user_input=goal, route=route)
            except TypeError:
                try:
                    plan = plan_fn(user_input=goal, context=context, route=route)
                except TypeError:
                    try:
                        plan = plan_fn(goal)
                    except Exception:
                        plan = None
            except Exception:
                plan = None

        if plan is None:
            plan = self._call_planner_like(planner, context=context, user_input=goal, route=route)

        normalized = self._normalize_external_plan(plan)
        if isinstance(normalized, dict):
            steps = normalized.get("steps", [])
            if isinstance(steps, list) and steps:
                return normalized

    return None


def _plan_goal_via_agent_planners(
    self,
    goal: str,
    document_payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    agent_loop = getattr(self, "agent_loop", None)
    if agent_loop is None:
        return None

    planners: List[Any] = []
    llm_planner = getattr(agent_loop, "llm_planner", None)
    deterministic_planner = getattr(agent_loop, "planner", None)

    if llm_planner is not None:
        planners.append(llm_planner)
    if deterministic_planner is not None:
        planners.append(deterministic_planner)

    context = {
        "user_input": goal,
        "workspace": self.workspace_dir,
    }
    route = {
        "mode": "task",
        "task": True,
    }

    if isinstance(document_payload, dict) and document_payload:
        context.update(copy.deepcopy(document_payload))
        route["document_task"] = True

    for planner in planners:
        plan = self._call_planner_like(planner, context=context, user_input=goal, route=route)
        normalized = self._normalize_external_plan(plan)
        if normalized is not None:
            return normalized

    return None


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
