from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_autonomous_operator_bridge import (
    RuntimeAutonomousOperatorBridge,
)
from core.runtime.runtime_autonomous_sentinel import RuntimeAutonomousSentinel
from core.runtime.runtime_operator_activity_log import RuntimeOperatorActivityLog


def _success(goal: str) -> dict:
    return {
        "ok": True,
        "natural_task": goal,
        "repair_attempted": False,
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_completed": True,
                "validation_passed": True,
                "rollback_completed": False,
                "changed_files": ["zero_probe.txt"],
            }
        },
    }


def _failure(goal: str) -> dict:
    return {
        "ok": False,
        "natural_task": goal,
        "denial_reason": "forced_failure",
        "repair_attempted": True,
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_completed": False,
                "validation_passed": False,
                "rollback_completed": True,
                "changed_files": [],
            }
        },
    }


def test_sentinel_records_completed_activity(tmp_path: Path) -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    bridge.submit("update zero_probe.txt with activity integration")

    activity_log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=1,
        activity_log=activity_log,
    )

    result = sentinel.tick()
    loaded = activity_log.read_all()

    assert result["ok"] is True
    assert result["sentinel_status"] == "completed"
    assert result["activity_recorded"] is True
    assert loaded["record_count"] == 1
    assert loaded["records"][0]["goal"] == (
        "update zero_probe.txt with activity integration"
    )
    assert loaded["records"][0]["status"] == "completed"
    assert loaded["records"][0]["changed_files"] == ["zero_probe.txt"]
    assert loaded["records"][0]["source"] == "runtime_autonomous_sentinel"


def test_sentinel_records_failed_activity_with_rollback(tmp_path: Path) -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_failure)
    bridge.submit("update zero_probe.txt with failed activity")

    activity_log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=1,
        activity_log=activity_log,
    )

    result = sentinel.tick()
    loaded = activity_log.read_all()

    assert result["ok"] is False
    assert result["sentinel_status"] == "failed"
    assert result["activity_recorded"] is True
    assert loaded["record_count"] == 1
    assert loaded["records"][0]["status"] == "rolled_back"
    assert loaded["records"][0]["rollback_completed"] is True
    assert loaded["records"][0]["repair_attempted"] is True


def test_sentinel_skips_activity_for_idle_cycle(tmp_path: Path) -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    activity_log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=1,
        activity_log=activity_log,
    )

    result = sentinel.tick()
    loaded = activity_log.read_all()

    assert result["sentinel_status"] == "idle"
    assert result["activity_recorded"] is False
    assert result["activity_result"]["activity_status"] == "skipped"
    assert loaded["record_count"] == 0


def test_sentinel_run_reports_activity_record_count(tmp_path: Path) -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    bridge.submit("update a.txt with one")
    bridge.submit("update b.txt with two")

    activity_log = RuntimeOperatorActivityLog(tmp_path / "activity.jsonl")
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=5,
        activity_log=activity_log,
    )

    result = sentinel.run()
    loaded = activity_log.read_all()

    assert result["ok"] is True
    assert result["completed_count"] == 2
    assert result["activity_record_count"] == 2
    assert loaded["record_count"] == 2


def test_sentinel_remains_compatible_when_activity_log_disabled() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    bridge.submit("update zero_probe.txt with no activity log")

    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=1,
        activity_log=None,
    )

    result = sentinel.tick()

    assert result["ok"] is True
    assert result["sentinel_status"] == "completed"
    assert result["activity_recorded"] is False
    assert result["activity_result"]["activity_status"] == "disabled"
