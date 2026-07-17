from __future__ import annotations

import pytest

from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from tests.goal_operations_test_support import byte_snapshot, make_goal


def test_read_service_delegates_to_goal_operations_without_mutation(tmp_path):
    _, goal, operations = make_goal(tmp_path)
    service = OperatorDashboardReadService(operations)
    before = byte_snapshot(tmp_path)
    overview = service.overview(); inspection = service.goal(goal["goal_id"]); timeline = service.timeline(goal["goal_id"]); health = service.health(); approvals = service.pending_approvals()
    assert overview["contract"] == "zero.agent.goal_operations.v1"
    assert inspection["goal_identity"] == goal["goal_id"]
    assert timeline["goal_id"] == goal["goal_id"]
    assert "checks" in health and "pending_approvals" in approvals
    assert byte_snapshot(tmp_path) == before


def test_read_service_missing_resources_fail_closed(tmp_path):
    _, _, operations = make_goal(tmp_path); service = OperatorDashboardReadService(operations)
    with pytest.raises(ValueError, match="goal_not_found"): service.goal("missing")
    with pytest.raises(ValueError, match="approval_not_found"): service.find_approval("missing")
