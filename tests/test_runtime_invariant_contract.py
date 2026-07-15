from __future__ import annotations

from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_overview_projection_contract_required_fields_are_stable(tmp_path):
    _, _, operations = make_goal(tmp_path); value = operations.overview().to_dict()
    required = {"contract", "version", "projection_version", "projection_kind", "snapshot_identity", "snapshot_fingerprint", "projection_fingerprint", "source_fingerprints", "source_manifest", "total_goal_count", "active_goal_count", "completed_goal_count", "waiting_approval_goal_count", "active_mission_count", "runtime_mission_budget", "remaining_mission_capacity", "daemon_status", "goal_summaries"}
    assert value["contract"] == "zero.agent.goal_operations.v1"
    assert value["version"] == "1.0"
    assert value["projection_version"] == "goal-operations-projection-v1"
    assert value["projection_kind"] == "overview"
    assert required <= set(value)
