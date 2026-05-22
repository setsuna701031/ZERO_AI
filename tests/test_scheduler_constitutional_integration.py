from __future__ import annotations

from pathlib import Path


def _constitutional_step_result() -> dict:
    snapshot = {
        "schema": "runtime_enforcement_decision.v1",
        "mode": "dry_run",
        "classification": "block_recommended",
        "safe_to_enforce": True,
        "reason": "sealed state is terminal",
        "would_block": True,
        "blocked": False,
    }
    metadata = {
        "constitutional_activation": True,
        "constitutional_activation_mode": "selective_activation",
        "constitutional_activation_reason": "sealed_resurrection_attempt",
        "constitutional_blocked": True,
        "constitutional_enforcement_snapshot": snapshot,
        "constitutional_continuity_status": "block_recommended",
    }
    return {
        "ok": False,
        "blocked": True,
        "error_type": "constitutionally_blocked",
        "runtime_execution_result": {
            "ok": False,
            "blocked": True,
            "metadata": metadata,
        },
    }


def test_scheduler_detects_constitutional_blocked_result(tmp_path: Path) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    task = {"task_id": "task-constitutional", "status": "running", "retry_count": 0}
    runner_result = {
        "ok": False,
        "status": "failed",
        "last_step_result": _constitutional_step_result(),
    }

    enriched = scheduler_module._zero_v7332_mark_constitutional_boundary(
        scheduler,
        task=task,
        runner_result=runner_result,
    )

    assert enriched["status"] == "review_required"
    assert enriched["action"] == "constitutional_blocked"
    assert enriched["constitutional_blocked"] is True
    assert enriched["needs_review"] is True
    assert task["status"] == "review_required"
    assert task["failure_type"] == "constitutional_blocked"


def test_scheduler_does_not_retry_constitutional_block_as_normal_failure(tmp_path: Path) -> None:
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    task = {
        "task_id": "task-no-retry",
        "status": "failed",
        "last_step_result": _constitutional_step_result(),
        "steps": [{"type": "apply_patch"}],
        "current_step_index": 0,
    }

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "constitutional block" in reason


def test_scheduler_preserves_enforcement_snapshot_metadata(tmp_path: Path) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    task = {"task_id": "task-snapshot", "status": "running"}
    result = scheduler_module._zero_v7332_mark_constitutional_boundary(
        scheduler,
        task=task,
        runner_result={"ok": False, "last_step_result": _constitutional_step_result()},
    )

    snapshot = result["constitutional_boundary"]["constitutional_enforcement_snapshot"]
    assert snapshot["schema"] == "runtime_enforcement_decision.v1"
    assert snapshot["classification"] == "block_recommended"
    assert snapshot["safe_to_enforce"] is True


def test_scheduler_normal_success_path_unchanged(tmp_path: Path) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    task = {"task_id": "task-ok", "status": "running"}
    runner_result = {"ok": True, "status": "finished", "last_step_result": {"ok": True}}

    enriched = scheduler_module._zero_v7332_mark_constitutional_boundary(
        scheduler,
        task=task,
        runner_result=runner_result,
    )

    assert enriched == runner_result
    assert task["status"] == "running"


def test_no_ui_tools_app_system_boot_coupling_added() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", root / "services/system_boot.py"]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)

    markers = (
        "_zero_v7332_mark_constitutional_boundary",
        "constitutional_review_required",
        "constitutional_execution_boundary",
    )
    for path in paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
