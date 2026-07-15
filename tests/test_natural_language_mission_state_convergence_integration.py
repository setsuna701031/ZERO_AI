import json
from pathlib import Path

import pytest

from core.runtime.runtime_event_bus import load_event_bus_state
from core.runtime.runtime_goal_execution_registry import load_goal_execution_registry
from core.runtime.runtime_mission_daemon import load_mission_daemon_state
from core.runtime.runtime_mission_execution_approval_flow import execute_approved_mission, review_mission_execution_plan
from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_mission_scheduler import load_mission_scheduler_state
from core.runtime.runtime_mission_session import load_mission_session_state
from core.runtime.runtime_natural_language_mission_bootstrap import NaturalLanguageMissionBootstrap, run_natural_language_mission
from core.runtime.runtime_worker_service import load_worker_state


NOW = "2026-07-13T00:00:00+00:00"
MISSION = "建立 hello.txt，內容是 hello zero，然後確認檔案存在"


def test_create_verify_converges_every_runtime_state_and_resume_is_read_only(tmp_path):
    artifact = run_natural_language_mission(MISSION, workspace_root=tmp_path, now=NOW)
    assert artifact["bootstrap_status"] == "waiting_for_plan_confirmation"
    assert not (tmp_path / "hello.txt").exists()
    review_mission_execution_plan(artifact["artifact_path"], decision="approve", operator_id="operator", now=NOW)
    result = execute_approved_mission(artifact["artifact_path"], operator_id="operator", now=NOW)
    assert result["mission_status"] == result["session_status"] == result["execution_status"] == "completed"
    assert result["completed_goal_count"] == 2 and result["waiting_goal_count"] == 0

    mission = load_mission(artifact["mission_reference"]["path"], check_expiry=False)
    assert mission["completed_goal_ids"] == mission["goal_order"]
    assert not mission["waiting_goal_ids"] and not mission["running_goal_ids"]
    assert not mission["blocked_goal_ids"] and not mission["failed_goal_ids"]
    assert mission["mission_evidence"]["task_completed_successfully"] is True
    assert mission["completed_at"] is not None and mission["failure"] is None

    session = load_mission_session_state(artifact["session_reference"]["path"])
    assert session["session_status"] == "completed" and session["execution_status"] == "completed"
    assert session["failure"] is None and session["completed_at"] is not None
    scheduler = load_mission_scheduler_state(session["scheduler_state_path"])
    worker = load_worker_state(session["worker_state_path"])
    daemon = load_mission_daemon_state(session["daemon_state_path"])
    assert scheduler["scheduler_status"] == worker["worker_status"] == daemon["daemon_status"] == "stopped"
    assert scheduler["completed_missions"] == 1

    registry = load_goal_execution_registry(session["execution_registry_state_path"])
    assert registry["registry_status"] == "closed" and registry["completion_count"] == 2
    assert all(item["execution_status"] == "completed" and item["transaction_status"] == "committed" for item in registry["completion_records"].values())
    bus = load_event_bus_state(session["event_bus_state_path"])
    topics = [bus["events"][event_id]["topic"] for event_id in bus["event_order"]]
    for topic in ("mission_execution.approved", "mission_execution.transaction_completed", "mission_goal.completed", "mission.completed", "mission_session.completed"):
        assert topic in topics

    target = tmp_path / "hello.txt"
    assert target.read_text(encoding="utf-8") == "hello zero"
    before = target.stat().st_mtime_ns
    transaction_count = registry["completion_count"]
    resumed = NaturalLanguageMissionBootstrap().resume(session["session_id"], workspace_root=tmp_path, now=NOW)
    assert resumed["status"] == resumed["session_status"] == "completed"
    assert resumed["mutation_performed"] is False and resumed["replayed"] is False
    assert target.stat().st_mtime_ns == before
    assert load_goal_execution_registry(session["execution_registry_state_path"])["completion_count"] == transaction_count


def test_expired_or_tampered_approval_never_mutates(tmp_path):
    artifact = run_natural_language_mission("create hello.txt with content hello zero", workspace_root=tmp_path, now=NOW)
    review_mission_execution_plan(artifact["artifact_path"], decision="approve", operator_id="operator", now=NOW)
    with pytest.raises(ValueError, match="approval_expired"):
        execute_approved_mission(artifact["artifact_path"], operator_id="operator", now="2026-07-13T02:00:00+00:00")
    assert not (tmp_path / "hello.txt").exists()
    approval_path = Path(artifact["artifact_path"]).with_name("execution-approval.json")
    approval = json.loads(approval_path.read_text(encoding="utf-8")); approval["approved_scope"] = ["other.txt"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError, match="approval_fingerprint_mismatch"):
        execute_approved_mission(artifact["artifact_path"], operator_id="operator", now=NOW)
    assert not (tmp_path / "hello.txt").exists()
