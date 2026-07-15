from __future__ import annotations

from core.operator.runtime_operator_dashboard_actions import OperatorDashboardActionService
from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_action_replay_is_idempotent_and_controller_is_singleton(tmp_path):
    controller, goal, operations = make_goal(tmp_path); creations = []
    def factory(): creations.append(True); return controller
    actions = OperatorDashboardActionService(factory, OperatorDashboardReadService(operations))
    body = {"operator_identity": "release-gate", "confirmation": True, "idempotency_key": "pause-replay"}
    first = actions.execute("pause", goal["goal_id"], body); second = actions.execute("pause", goal["goal_id"], body)
    assert first["idempotent_replay"] is False and second["idempotent_replay"] is True
    assert first["result_fingerprint"] == second["result_fingerprint"]
    assert creations == [True]
