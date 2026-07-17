from pathlib import Path

from tests.goal_operations_test_support import make_waiting_goal

def test_waiting_reference_chain_has_entry_mission_session_and_integrity(tmp_path):
    _, goal, service = make_waiting_goal(tmp_path); value = service.inspect(goal["goal_id"]).to_dict(); chains = value["reference_integrity_result"]["chains"]
    active = next(chain for chain in chains if chain.get("entry_status") == "waiting_for_approval")
    assert active["entry_id"] and active["mission_id"] and active["session_id"] and active["integrity"]
    assert not any(key.endswith("_path") for key in active)

def test_missing_session_is_reported_without_repair(tmp_path):
    controller, goal, service = make_waiting_goal(tmp_path); entry = next(item for item in controller.agent.list() if item["status"] == "waiting_for_approval")
    import json
    artifact = json.loads(Path(entry["bootstrap_artifact_path"]).read_text(encoding="utf-8")); session_path = Path(artifact["session_reference"]["path"]); session_path.unlink()
    value = service.inspect(goal["goal_id"]).to_dict(); reasons = [item["reason"] for item in value["reference_integrity_result"]["issues"]]
    assert "missing_or_invalid_session" in reasons and not session_path.exists()

def test_pending_approval_projects_proposal_without_mutation(tmp_path):
    from tests.goal_operations_test_support import byte_snapshot
    _, _, service = make_waiting_goal(tmp_path); before = byte_snapshot(tmp_path); value = service.pending_approvals().to_dict()
    assert value["pending_approval_count"] == 1
    assert value["pending_approvals"][0]["current_status"] == "pending"
    assert value["pending_approvals"][0]["approval_or_proposal_id"]
    assert byte_snapshot(tmp_path) == before
