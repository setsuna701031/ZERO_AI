from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00+00:00"


def test_loop_is_bounded_by_max_missions_and_priority(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8"); (tmp_path / "LICENSE").write_text("y", encoding="utf-8")
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    low = controller.add("read LICENSE", priority="low", now=NOW); high = controller.add("read README.md", priority="high", now=NOW)
    result = RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=5, now=NOW)
    assert result["selected_entry_ids"] == [high["entry_id"]] and controller.show(low["entry_id"])["status"] == "pending"


def test_waiting_approval_does_not_stop_unrelated_read_only(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    mutation = controller.add("create hello.txt with content hello zero", priority="high", now=NOW)
    read = controller.add("read README.md", priority="normal", now=NOW)
    result = RuntimePersistentAgentLoop(controller).run(max_missions=2, max_iterations=4, now=NOW)
    assert result["selected_entry_ids"] == [mutation["entry_id"], read["entry_id"]]
    assert controller.show(mutation["entry_id"])["status"] == "waiting_for_approval" and controller.show(read["entry_id"])["status"] == "completed"


def test_idle_exit_and_completed_not_replayed(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("read README.md", now=NOW)
    loop = RuntimePersistentAgentLoop(controller); first = loop.run(max_missions=1, max_iterations=2, now=NOW); second = loop.run(max_missions=1, max_iterations=2, now=NOW)
    assert first["selected_entry_ids"] == [entry["entry_id"]] and second["selected_entry_ids"] == [] and second["stopped_reason"] == "idle"


def test_pause_and_stop_prevent_selection(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); controller.add("read README.md", now=NOW); loop = RuntimePersistentAgentLoop(controller)
    controller.pause(now=NOW); assert loop.run(max_missions=1, max_iterations=1, now=NOW)["stopped_reason"] == "pause_requested"
    controller.resume(now=NOW); controller.stop(now=NOW); assert loop.run(max_missions=1, max_iterations=1, now=NOW)["stopped_reason"] == "stop_requested"


def test_each_processed_iteration_persists_checkpoint(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); controller.add("read README.md", now=NOW)
    RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=2, now=NOW)
    state = controller.load_state(); assert state["loop_iteration"] == 1 and len(state["checkpoints"]) == 1


def test_stop_on_blocked_includes_waiting_for_approval(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    first = controller.add("create hello.txt with content hello zero", priority="high", now=NOW); second = controller.add("read README.md", now=NOW)
    result = RuntimePersistentAgentLoop(controller).run(max_missions=2, max_iterations=4, stop_on_blocked=True, now=NOW)
    assert result["stopped_reason"] == "stop_on_blocked" and result["selected_entry_ids"] == [first["entry_id"]]
    assert controller.show(second["entry_id"])["status"] == "pending"
