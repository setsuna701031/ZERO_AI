from __future__ import annotations

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00Z"


def test_real_read_only_path_converges_once_with_evidence_and_counters(tmp_path):
    (tmp_path / "README.md").write_text("ZERO read evidence", encoding="utf-8")
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    entry = controller.add("read README.md", priority="high", now=NOW)
    first = RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=20, now=NOW)
    completed = controller.show(entry["entry_id"])
    state = controller.load_state()
    assert first["processed"] == [{"entry_id": entry["entry_id"], "status": "completed", "mission_id": completed["mission_id"], "session_id": completed["mission_session_id"]}]
    assert completed["status"] == "completed" and completed["last_result"]["runtime_result"]["read_only"] is True
    assert completed["last_result"]["runtime_result"]["evidence"]
    assert state["missions_started"] == state["missions_completed"] == 1
    assert state["missions_blocked"] == state["missions_failed"] == 0
    assert first["agent_status"] == "idle"

    second = RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=20, now=NOW)
    assert second["selected_entry_ids"] == []
    assert controller.load_state()["missions_completed"] == 1
    assert controller.show(entry["entry_id"])["completed_at"] == completed["completed_at"]

