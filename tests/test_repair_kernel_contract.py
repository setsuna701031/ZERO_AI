from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.tasks.scheduler import Scheduler


def _make_scheduler(tmp_path: Path) -> Scheduler:
    return Scheduler(workspace_dir=str(tmp_path / "workspace"))


def _base_failed_task(step_type: str = "write_file") -> Dict[str, Any]:
    return {
        "task_id": "repair_contract_task",
        "task_name": "repair_contract_task",
        "goal": "repair contract task",
        "status": "failed",
        "replan_count": 0,
        "max_replans": 3,
        "last_error": "recoverable failure",
        "steps": [{"type": step_type}],
        "current_step_index": 0,
        "last_step_result": {
            "step": {"type": step_type},
            "ok": False,
            "error": "recoverable failure",
        },
    }


def test_repair_kernel_rejects_non_repairable_status(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("write_file")
    task["status"] = "running"

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "status not repairable" in reason


def test_repair_kernel_rejects_exhausted_replan_budget(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("write_file")
    task["replan_count"] = 3
    task["max_replans"] = 3

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "replan limit reached" in reason


def test_repair_kernel_rejects_unsupported_step_type(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("unknown_step")

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "step type not repairable" in reason


def test_repair_kernel_rejects_hard_failure_text(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("write_file")
    task["last_error"] = "file not found"

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "hard failure" in reason


def test_repair_kernel_accepts_recoverable_write_file_failure(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("write_file")
    task["last_error"] = "assertion mismatch"

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is True
    assert reason == ""


def test_repair_kernel_accepts_recoverable_command_failure(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("command")
    task["last_error"] = "command returned nonzero exit code"

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is True
    assert reason == ""


def test_repair_kernel_routes_verify_failures_through_verify_policy(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = _base_failed_task("verify")
    task["last_error"] = "verification failed"

    repairable, reason = scheduler._is_repairable_failure(task)

    assert isinstance(repairable, bool)
    assert isinstance(reason, str)

    if repairable:
        assert reason == ""
    else:
        assert "verify failure" in reason
