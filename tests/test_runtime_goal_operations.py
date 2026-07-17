from tests.goal_operations_test_support import byte_snapshot, make_goal

def test_overview_is_sealed_deterministic_and_read_only(tmp_path):
    controller, goal, service = make_goal(tmp_path); before = byte_snapshot(tmp_path)
    values = [service.overview().to_dict() for _ in range(3)]
    assert values[0] == values[1] == values[2]
    assert values[0]["projection_fingerprint"] and values[0]["snapshot_identity"] and values[0]["snapshot_fingerprint"]
    assert "snapshot_time" not in values[0] and values[0]["total_goal_count"] == 1
    assert values[0]["source_fingerprints"]["goals"][goal["goal_id"]] == goal["goal_fingerprint"]
    from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
    later = GoalOperationsService(GoalOperationsConfig(str(tmp_path), state_root=str(controller.agent_state_root), reference_time="2099-01-01T00:00:00Z")).overview().to_dict()
    assert later["snapshot_fingerprint"] == values[0]["snapshot_fingerprint"]
    assert byte_snapshot(tmp_path) == before

def test_overview_empty_store_does_not_create_state(tmp_path):
    from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
    service = GoalOperationsService(GoalOperationsConfig(str(tmp_path)))
    before = byte_snapshot(tmp_path); value = service.overview().to_dict()
    assert value["total_goal_count"] == 0 and byte_snapshot(tmp_path) == before

def test_inspection_redacts_absolute_paths_and_projects_dependencies(tmp_path):
    _, goal, service = make_goal(tmp_path); value = service.inspect(goal["goal_id"]).to_dict()
    assert value["goal_scope"]["workspace"] == "<workspace-root>"
    assert str(tmp_path.resolve()) not in str(value)
    assert len(value["milestone_dependency_graph"]) == len(goal["milestone_order"])
    assert value["reference_integrity_result"]["integrity"] is True

def test_every_operations_output_uses_sanitize_redact_seal_fingerprint_serialize_pipeline(tmp_path):
    import json
    import pytest
    from core.agent.runtime_goal_operations_snapshot import CONTRACT, VERSION, finalize_projection, serialize_projection, validate_projection
    value = finalize_projection({"contract": CONTRACT, "version": VERSION, "workspace_root": tmp_path, "claim_token": "sensitive", "nested": ("safe",)})
    assert value["workspace_root"] == "<redacted-path>" and value["claim_token"] == "<redacted>" and value["nested"] == ["safe"]
    assert validate_projection(value, CONTRACT) == [] and json.loads(serialize_projection(value)) == value
    value["nested"].append("tampered")
    with pytest.raises(ValueError, match="fingerprint"): serialize_projection(value)
