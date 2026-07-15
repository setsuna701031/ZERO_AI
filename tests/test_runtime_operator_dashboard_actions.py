from __future__ import annotations

import pytest

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
from core.operator.runtime_operator_dashboard_actions import OperatorDashboardActionService
from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from tests.goal_operations_test_support import GOAL_TEXT, NOW, make_goal, make_waiting_goal


def payload(key="action-1", **extra):
    return {"operator_identity": "test-operator", "confirmation": True, "idempotency_key": key, **extra}


def test_goal_actions_use_runtime_controller_and_are_idempotent(tmp_path):
    controller, goal, operations = make_goal(tmp_path)
    actions = OperatorDashboardActionService(controller, OperatorDashboardReadService(operations))
    first = actions.execute("pause", goal["goal_id"], payload())
    replay = actions.execute("pause", goal["goal_id"], payload())
    assert first["runtime_result"]["goal_status"] == "paused"
    assert replay["idempotent_replay"] is True
    resumed = actions.execute("resume", goal["goal_id"], payload("action-2"))
    assert resumed["runtime_result"]["goal_status"] in {"ready", "running"}


def test_action_validation_occurs_before_lazy_controller_creation(tmp_path):
    _, goal, operations = make_goal(tmp_path); called = []
    actions = OperatorDashboardActionService(lambda: called.append(True), OperatorDashboardReadService(operations))
    with pytest.raises(ValueError, match="confirmation"): actions.execute("pause", goal["goal_id"], {"operator_identity": "op", "confirmation": False, "idempotency_key": "x"})
    assert called == []


def test_lazy_controller_factory_creates_singleton_once_per_dashboard_process(tmp_path):
    controller, goal, operations = make_goal(tmp_path); calls = []
    def factory():
        calls.append("created")
        return controller
    actions = OperatorDashboardActionService(factory, OperatorDashboardReadService(operations))
    actions.execute("pause", goal["goal_id"], payload("singleton-pause"))
    actions.execute("resume", goal["goal_id"], payload("singleton-resume"))
    assert calls == ["created"]
    assert actions.controller is controller


def test_read_only_and_terminal_actions_fail_closed(tmp_path):
    controller, goal, operations = make_goal(tmp_path); reads = OperatorDashboardReadService(operations)
    with pytest.raises(ValueError, match="read_only"): OperatorDashboardActionService(controller, reads, enabled=False).execute("pause", goal["goal_id"], payload())
    controller.cancel(goal["goal_id"])
    with pytest.raises(ValueError, match="terminal"): OperatorDashboardActionService(controller, reads).execute("pause", goal["goal_id"], payload("terminal"))


@pytest.mark.parametrize("action,expected", (("stop", "stopped"), ("cancel", "cancelled"), ("replan", "ready")))
def test_remaining_goal_actions_delegate_to_controller(tmp_path, action, expected):
    root = tmp_path / action; root.mkdir()
    controller, goal, operations = make_goal(root)
    actions = OperatorDashboardActionService(controller, OperatorDashboardReadService(operations))
    extra = {"reason": "operator requested bounded replan"} if action == "replan" else {}
    result = actions.execute(action, goal["goal_id"], payload(f"{action}-once", **extra))
    assert result["runtime_result"]["goal_status"] == expected


@pytest.mark.parametrize("decision", ("approve", "deny"))
def test_approval_actions_preserve_entry_session_and_scope(tmp_path, decision):
    root = tmp_path / decision; root.mkdir()
    controller = RuntimeGoalController(workspace_root=root)
    goal = controller.create(GOAL_TEXT)
    controller.run(goal["goal_id"], max_milestones=1, max_missions=1)
    operations = GoalOperationsService(GoalOperationsConfig(str(root), state_root=str(controller.agent_state_root)))
    reads = OperatorDashboardReadService(operations); item = reads.pending_approvals()["pending_approvals"][0]
    entry_before = controller.agent.show(item["entry_id"]); entry_ids_before = [entry["entry_id"] for entry in controller.agent.list()]
    body = payload(f"{decision}-once", goal_id=item["goal_id"], milestone_id=item["milestone_id"], entry_id=item["entry_id"], expected_scope_fingerprint=item["fingerprint"])
    if decision == "deny": body["reason"] = "operator rejected requested scope"
    result = OperatorDashboardActionService(controller, reads).execute(decision, item["approval_or_proposal_id"], body)
    entry_after = controller.agent.show(item["entry_id"])
    assert result["action"] == decision
    assert [entry["entry_id"] for entry in controller.agent.list()] == entry_ids_before
    assert entry_after["mission_id"] == entry_before["mission_id"]
    assert entry_after["mission_session_id"] == entry_before["mission_session_id"]
    assert item["requested_scope"]


def test_approval_ttl_uses_shared_reference_time_not_wall_clock(tmp_path):
    controller, _, operations = make_waiting_goal(tmp_path)
    reads = OperatorDashboardReadService(operations); item = reads.pending_approvals()["pending_approvals"][0]
    body = payload("reference-time-approve", goal_id=item["goal_id"], milestone_id=item["milestone_id"], entry_id=item["entry_id"], expected_scope_fingerprint=item["fingerprint"])
    result = OperatorDashboardActionService(controller, reads, time_provider=lambda: NOW).execute("approve", item["approval_or_proposal_id"], body)
    assert result["runtime_result"]["goal_status"] in {"running", "ready", "completed", "partially_completed"}
