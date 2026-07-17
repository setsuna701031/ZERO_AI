from __future__ import annotations

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_mission_reflection import build_mission_reflection
from core.runtime.runtime_memory_model import build_runtime_activity_experience
from core.runtime.runtime_mission_model import load_mission


NOW = "2026-07-13T00:00:00Z"


def seed_create_experience(controller, tmp_path):
    entry = {"entry_id": "old", "mission_id": "old-m", "mission_session_id": "old-s", "status": "completed", "original_input": "create hello.txt and verify", "normalized_input": "create hello.txt and verify", "workspace_root": str(tmp_path), "attempt_count": 1, "max_attempts": 3, "approval_required": True, "approval_status": "approved", "last_result": {"validation_status": "passed"}, "failure": None}
    artifact = {"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}
    reflection = build_mission_reflection(entry, agent_id="agent", artifact=artifact, now=NOW)
    controller.load_memory().record_experience(build_runtime_activity_experience(reflection, entry=entry, artifact=artifact))


def test_agent_injects_feedback_into_graph_and_preserves_approval(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); seed_create_experience(controller, tmp_path)
    entry = controller.add("create second.txt with content hello second", now=NOW)
    controller.claim_next(now=NOW); prepared = controller.process_entry(entry["entry_id"], now=NOW)
    assert prepared["status"] == "waiting_for_approval"
    assert prepared["planning_feedback_status"] == "created"
    mission = load_mission(controller.planning(entry["entry_id"])["goal_plan_after"] and controller.show(entry["entry_id"])["bootstrap_artifact_path"].replace("bootstrap.json", "mission.json"), check_expiry=False)
    assert [mission["goals"][goal]["natural_operation"] for goal in mission["goal_order"]] == ["create_file", "check_exists"]
    assert not (tmp_path / "second.txt").exists()
    completed = controller.approve(entry["entry_id"], operator_id="operator", now=NOW)
    assert completed["status"] == "completed"
    assert (tmp_path / "second.txt").read_text(encoding="utf-8") == "hello second"
    reflected = controller.reflect(entry["entry_id"])["reflection"]
    assert "create_then_verify" in reflected["planning_recommendations_effective"]
