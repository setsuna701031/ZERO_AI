from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.agent.runtime_goal_operations import GoalOperationsService


class OperatorDashboardReadService:
    def __init__(self, operations: GoalOperationsService):
        if not isinstance(operations, GoalOperationsService):
            raise TypeError("goal_operations_service_required")
        self.operations = operations

    def overview(self) -> dict[str, Any]:
        return self.operations.overview().to_dict()

    def goal(self, goal_id: str) -> dict[str, Any]:
        return self.operations.inspect(goal_id).to_dict()

    def timeline(self, goal_id: str) -> dict[str, Any]:
        return self.operations.timeline(goal_id).to_dict()

    def health(self) -> dict[str, Any]:
        return self.operations.health().to_dict()

    def pending_approvals(self) -> dict[str, Any]:
        return self.operations.pending_approvals().to_dict()

    def find_approval(self, approval_id: str) -> dict[str, Any]:
        projection = self.pending_approvals()
        found = next((deepcopy(item) for item in projection.get("pending_approvals", [])
                      if item.get("approval_or_proposal_id") == approval_id), None)
        if found is None:
            raise ValueError("approval_not_found")
        return found


__all__ = ["OperatorDashboardReadService"]
