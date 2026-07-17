from __future__ import annotations

from pathlib import Path

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00Z"


def completed_controller(tmp_path):
    (tmp_path / "README.md").write_text("ZERO", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("read README.md", now=NOW); RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=10, now=NOW); return controller, entry["entry_id"]


def test_recovery_repairs_missing_reflection_without_duplicate_experience_or_event(tmp_path):
    controller, entry_id = completed_controller(tmp_path); entry = controller.show(entry_id); Path(entry["reflection_path"]).unlink()
    before_count = len(controller.load_memory().experience_records())
    controller.recover(now=NOW); repaired = controller.show(entry_id)
    controller.recover(now=NOW)
    assert Path(repaired["reflection_path"]).is_file() and len(controller.load_memory().experience_records()) == before_count == 1
    from core.runtime.runtime_event_bus import load_event_bus_state
    bus = load_event_bus_state(controller.event_bus_path); topics = [bus["events"][key]["topic"] for key in bus["event_order"]]
    assert topics.count("agent.entry.experience_recorded") == 1


def test_memory_write_failure_does_not_reverse_completed_mission(tmp_path):
    (tmp_path / "README.md").write_text("ZERO", encoding="utf-8"); controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    bad_path = tmp_path / "memory-directory"; bad_path.mkdir(); controller.activity_memory_path = bad_path
    entry = controller.add("read README.md", now=NOW); RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=10, now=NOW); result = controller.show(entry["entry_id"])
    assert result["status"] == "completed" and result["reflection_status"] == "failed"
    assert result["reflection_error"]

