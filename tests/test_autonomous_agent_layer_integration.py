import json
from pathlib import Path

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00+00:00"


def test_three_mission_priority_approval_and_idempotent_resume(tmp_path):
    (tmp_path / "README.md").write_text("ZERO", encoding="utf-8")
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW)
    high = controller.add("read README.md", priority="high", now=NOW)
    normal = controller.add("建立 hello.txt，內容是 hello zero，然後確認檔案存在", priority="normal", now=NOW)
    low = controller.add("建立 reports 資料夾", priority="low", now=NOW)
    loop = RuntimePersistentAgentLoop(controller)
    first = loop.run(max_missions=3, max_iterations=6, now=NOW)
    assert first["selected_entry_ids"] == [high["entry_id"], normal["entry_id"], low["entry_id"]]
    assert controller.show(high["entry_id"])["status"] == "completed"
    waiting = controller.show(normal["entry_id"]); assert waiting["status"] == "waiting_for_approval"
    assert controller.show(low["entry_id"])["status"] == "waiting_for_approval"
    assert not (tmp_path / "hello.txt").exists() and not (tmp_path / "reports").exists()

    session_id = waiting["mission_session_id"]
    completed = controller.approve(normal["entry_id"], operator_id="operator", now=NOW)
    assert completed["status"] == "completed" and completed["mission_session_id"] == session_id
    target = tmp_path / "hello.txt"; assert target.read_text(encoding="utf-8") == "hello zero"
    before = target.stat().st_mtime_ns
    registry_path = Path(json.loads(Path(completed["bootstrap_artifact_path"]).read_text(encoding="utf-8-sig"))["session_reference"]["path"]).with_name("execution-registry.json")
    count = json.loads(registry_path.read_text(encoding="utf-8-sig"))["completion_count"]
    again = loop.run(max_missions=3, max_iterations=4, now=NOW)
    assert normal["entry_id"] not in again["selected_entry_ids"] and target.stat().st_mtime_ns == before
    assert json.loads(registry_path.read_text(encoding="utf-8-sig"))["completion_count"] == count

