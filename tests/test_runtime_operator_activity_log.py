from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_operator_activity_log import (
    RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
    RuntimeOperatorActivityLog,
)


def test_activity_log_records_completed_mutation(tmp_path: Path) -> None:
    log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    result = log.append(
        goal="update zero_probe.txt with activity log works",
        task_id="task-1",
        result={
            "ok": True,
            "repair_attempted": False,
            "operator_result": {
                "controlled_mutation_result": {
                    "ok": True,
                    "changed_files": ["zero_probe.txt"],
                    "rollback_completed": False,
                }
            },
        },
    )
    assert result["schema"] == RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA
    assert result["ok"] is True
    assert result["record"]["status"] == "completed"
    assert result["record"]["changed_files"] == ["zero_probe.txt"]


def test_activity_log_records_rollback_and_repair(tmp_path: Path) -> None:
    log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    result = log.append(
        goal="update zero_probe.txt with broken data force validation failure",
        result={
            "ok": False,
            "repair_attempted": True,
            "operator_result": {
                "controlled_mutation_result": {
                    "ok": False,
                    "changed_files": [],
                    "rollback_completed": True,
                    "denial_reason": "console_filesystem_mutation_incomplete",
                }
            },
        },
    )
    assert result["record"]["status"] == "rolled_back"
    assert result["record"]["rollback_completed"] is True
    assert result["record"]["repair_attempted"] is True


def test_activity_log_reads_multiple_records(tmp_path: Path) -> None:
    log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    log.append(goal="update a.txt with one", result={"ok": True})
    log.append(goal="update b.txt with two", result={"ok": False})
    loaded = log.read_all()
    assert loaded["record_count"] == 2
    assert loaded["records"][0]["goal"] == "update a.txt with one"
    assert loaded["records"][1]["goal"] == "update b.txt with two"


def test_activity_log_empty_state(tmp_path: Path) -> None:
    log = RuntimeOperatorActivityLog(tmp_path / "missing.jsonl")
    loaded = log.read_all()
    assert loaded["activity_status"] == "empty"
    assert loaded["record_count"] == 0
    assert loaded["records"] == []


def test_activity_log_rejects_empty_goal(tmp_path: Path) -> None:
    log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    result = log.append(goal="", result={"ok": True})
    assert result["ok"] is False
    assert result["activity_status"] == "denied"
    assert result["denial_reason"] == "goal_required"
