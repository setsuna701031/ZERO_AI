import json
from pathlib import Path

from core.agent.runtime_agent_controller import RuntimeAgentController, save_agent_state
from core.agent.runtime_mission_inbox import save_mission_inbox, update_mission_entry
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


NOW = "2026-07-13T00:00:00+00:00"


def test_selected_before_prepare_recovers_to_pending(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("read README.md", now=NOW); controller.claim_next(now=NOW)
    controller.recover(now=NOW)
    assert controller.show(entry["entry_id"])["status"] == "pending"


def test_waiting_approval_recovery_preserves_same_identity(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("create hello.txt with content hello zero", now=NOW)
    RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=2, now=NOW); waiting = controller.show(entry["entry_id"])
    inbox, _ = update_mission_entry(controller.load_inbox(), entry["entry_id"], status="running", now=NOW); save_mission_inbox(inbox, controller.inbox_path)
    controller.recover(now=NOW); recovered = controller.show(entry["entry_id"])
    assert recovered["status"] == "waiting_for_approval" and recovered["mission_session_id"] == waiting["mission_session_id"]


def test_completed_mission_recovery_never_replays_mutation(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("create hello.txt with content hello zero", now=NOW)
    RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=2, now=NOW); controller.approve(entry["entry_id"], operator_id="operator", now=NOW)
    target = tmp_path / "hello.txt"; before = target.stat().st_mtime_ns
    controller.recover(now=NOW); RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=2, now=NOW)
    assert controller.show(entry["entry_id"])["status"] == "completed" and target.stat().st_mtime_ns == before


def test_identity_mismatch_blocks_safely(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); entry = controller.add("create hello.txt with content hello zero", now=NOW)
    RuntimePersistentAgentLoop(controller).run(max_missions=1, max_iterations=2, now=NOW)
    inbox, _ = update_mission_entry(controller.load_inbox(), entry["entry_id"], status="running", updates={"mission_id": "forged"}, now=NOW); save_mission_inbox(inbox, controller.inbox_path)
    controller.recover(now=NOW)
    assert controller.show(entry["entry_id"])["status"] == "blocked" and not (tmp_path / "hello.txt").exists()


def test_agent_state_fingerprint_mismatch_fails_recovery(tmp_path):
    controller = RuntimeAgentController(workspace_root=tmp_path, now=NOW); raw = json.loads(controller.agent_state_path.read_text(encoding="utf-8")); raw["agent_status"] = "running"; controller.agent_state_path.write_text(json.dumps(raw), encoding="utf-8")
    try: controller.recover(now=NOW)
    except ValueError as exc: assert "fingerprint" in str(exc)
    else: raise AssertionError("tampered agent state must fail safely")

