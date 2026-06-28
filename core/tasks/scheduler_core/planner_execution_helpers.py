from __future__ import annotations

from typing import Any, Dict, Optional

from core.tasks.scheduler_core import planner_gateway_execution_helpers
from core.tasks.scheduler_core import planner_invocation_helpers
from core.tasks.scheduler_core import planner_normalization_helpers


def _call_planner_like(
    self,
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Dict[str, Any],
) -> Any:
    if planner is None:
        return None

    request = {
        "context": context,
        "user_input": user_input,
        "route": route,
        "goal": user_input,
    }
    candidate_calls = planner_invocation_helpers._planner_candidate_calls(
        context,
        user_input,
        route,
    )

    def gateway_adapter(raw_plan: Any) -> Any:
        return planner_gateway_execution_helpers._gateway_first_or_legacy(
            raw_plan,
            request,
            user_input,
        )

    for method in planner_invocation_helpers._iter_planner_methods(planner):
        return planner_invocation_helpers._invoke_planner_method(
            method,
            candidate_calls,
            user_input,
            gateway_adapter,
        )
    return None


def _normalize_external_plan(self, plan: Any) -> Optional[Dict[str, Any]]:
    return planner_normalization_helpers._normalize_external_plan(self, plan)
