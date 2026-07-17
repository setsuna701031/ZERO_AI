from core.agent.runtime_agent_controller import RuntimeAgentController


NOW = "2026-07-13T00:00:00Z"


def test_recovery_does_not_recreate_completed_planning_artifact(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    entry = controller.add("read README.md", now=NOW); controller.claim_next(now=NOW); controller.process_entry(entry["entry_id"], now=NOW)
    current = controller.show(entry["entry_id"]); before = controller.planning(entry["entry_id"])
    restarted = RuntimeAgentController(workspace_root=tmp_path, state_root=controller.state_root, now=NOW); restarted.recover(now=NOW)
    after = restarted.planning(entry["entry_id"])
    assert before["feedback_id"] == after["feedback_id"]
    assert current["bootstrap_artifact_path"] == restarted.show(entry["entry_id"])["bootstrap_artifact_path"]
