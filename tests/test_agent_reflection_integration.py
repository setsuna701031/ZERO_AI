from __future__ import annotations

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00Z"


def run_one(controller, entry):
    RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=10, now=NOW)
    return controller.show(entry["entry_id"])


def test_read_mutation_and_blocked_missions_create_terminal_reflections(tmp_path):
    (tmp_path / "README.md").write_text("ZERO", encoding="utf-8")
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    read = run_one(controller, controller.add("read README.md", now=NOW))
    assert read["status"] == read["reflection_status"] == "completed"
    assert controller.memory_show(read["experience_id"])["operation_types"] == ["read_file"]

    mutation_entry = controller.add("create hello.txt with content hello zero and then verify it", now=NOW)
    waiting = run_one(controller, mutation_entry)
    assert waiting["status"] == "waiting_for_approval" and waiting["reflection_id"] is None
    completed = controller.approve(mutation_entry["entry_id"], operator_id="operator", now=NOW)
    reflected = controller.reflect(completed["entry_id"])["reflection"]
    assert completed["status"] == "completed" and "create_then_verify" in reflected["reusable_patterns"]
    assert "hello.txt" in controller.memory_show(completed["experience_id"])["target_paths"]

    blocked = run_one(controller, controller.add("create ../outside.txt with content no", now=NOW))
    assert blocked["status"] == "blocked" and blocked["reflection_status"] == "completed"
    assert "path_traversal" in controller.reflect(blocked["entry_id"])["reflection"]["avoid_patterns"]


def test_future_mission_bootstrap_receives_bounded_memory_context(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    first = controller.add("create hello.txt with content hello and then verify it", now=NOW); run_one(controller, first); controller.approve(first["entry_id"], operator_id="operator", now=NOW)
    second = controller.add("create second.txt with content second and then verify it", now=NOW); waiting = run_one(controller, second)
    context = waiting["memory_context_used"]
    assert context["experience_references"] and "create_then_verify" in context["successful_patterns"]
    import json
    artifact = json.loads(open(waiting["bootstrap_artifact_path"], encoding="utf-8").read())
    assert artifact["original_input"] == second["original_input"] and artifact["memory_context"] == context
    assert waiting["status"] == "waiting_for_approval" and not (tmp_path / "second.txt").exists()

