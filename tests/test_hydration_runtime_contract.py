from __future__ import annotations

from pathlib import Path

from core.tasks.scheduler import Scheduler


def _make_scheduler(tmp_path: Path) -> Scheduler:
    return Scheduler(workspace_dir=str(tmp_path / "workspace"))


def test_hydrate_preserves_basic_task_identity_and_status(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = {
        "task_id": "hydrate_contract_basic",
        "task_name": "hydrate_contract_basic",
        "goal": "hydrate contract basic task",
        "status": "queued",
        "steps": [{"type": "noop"}],
        "current_step_index": 0,
        "execution_log": [{"event": "before_hydrate"}],
    }

    hydrated = scheduler._hydrate_task_from_workspace(task)

    assert isinstance(hydrated, dict)
    assert hydrated["task_id"] == "hydrate_contract_basic"
    assert hydrated["task_name"] == "hydrate_contract_basic"
    assert hydrated["status"] == "queued"
    assert hydrated["goal"] == "hydrate contract basic task"
    assert hydrated["execution_log"] == [{"event": "before_hydrate"}]


def test_hydrate_handles_missing_workspace_files_without_dropping_runtime_fields(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    missing_task_dir = tmp_path / "workspace" / "tasks" / "missing_task"

    task = {
        "task_id": "missing_task",
        "task_name": "missing_task",
        "goal": "missing workspace files should not break hydration",
        "status": "running",
        "task_dir": str(missing_task_dir),
        "plan_file": str(missing_task_dir / "plan.json"),
        "runtime_state_file": str(missing_task_dir / "runtime_state.json"),
        "trace_file": str(missing_task_dir / "trace.json"),
        "steps": [],
        "results": [],
        "step_results": [],
        "execution_log": [],
    }

    hydrated = scheduler._hydrate_task_from_workspace(task)

    assert isinstance(hydrated, dict)
    assert hydrated["task_id"] == "missing_task"
    assert hydrated["status"] == "running"
    assert isinstance(hydrated.get("steps"), list)
    assert isinstance(hydrated.get("results"), list)
    assert isinstance(hydrated.get("step_results"), list)
    assert isinstance(hydrated.get("execution_log"), list)


def test_hydrate_backfills_public_fields(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = {
        "task_id": "public_fields_task",
        "task_name": "public_fields_task",
        "goal": "hydrate should refresh public fields",
        "status": "finished",
        "steps": [{"type": "write_file"}],
        "current_step_index": 1,
        "results": [{"text": "done"}],
        "step_results": [{"text": "done"}],
        "execution_log": [{"ok": True}],
    }

    hydrated = scheduler._hydrate_task_from_workspace(task)

    assert isinstance(hydrated, dict)
    assert hydrated["status"] == "finished"
    assert hydrated.get("steps_total") == 1
    assert hydrated.get("current_step_index") == 1
    assert "public_snapshot" in hydrated
    assert isinstance(hydrated["public_snapshot"], dict)
    assert hydrated["public_snapshot"].get("task_id") == "public_fields_task"


def test_hydrate_runtime_state_can_resume_run_next_tick_when_not_blocked(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_dir = tmp_path / "workspace" / "tasks" / "resume_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    runtime_state_file = task_dir / "runtime_state.json"
    runtime_state_file.write_text(
        """{
  "status": "waiting",
  "next_action": "run_next_tick",
  "active_blocker_count": 0,
  "blockers": [],
  "requires_review": false,
  "steps": [{"type": "noop"}],
  "current_step_index": 0,
  "results": [],
  "step_results": [],
  "execution_log": []
}
""",
        encoding="utf-8",
    )

    task = {
        "task_id": "resume_task",
        "task_name": "resume_task",
        "goal": "resume task",
        "status": "waiting",
        "runtime_state_file": str(runtime_state_file),
        "task_dir": str(task_dir),
        "steps": [],
    }

    hydrated = scheduler._hydrate_task_from_workspace(task)

    assert isinstance(hydrated, dict)
    assert hydrated["task_id"] == "resume_task"
    assert hydrated["status"] == "running"
    assert hydrated["next_action"] == "run_next_tick"
    assert hydrated["active_blocker_count"] == 0
    assert hydrated["blocked_reason"] == ""
    assert hydrated["waiting_reason"] == ""


def test_hydrate_does_not_resume_when_blocker_is_active(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_dir = tmp_path / "workspace" / "tasks" / "blocked_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    runtime_state_file = task_dir / "runtime_state.json"
    runtime_state_file.write_text(
        """{
  "status": "waiting",
  "next_action": "run_next_tick",
  "active_blocker_count": 1,
  "blockers": [{"status": "pending", "reason": "manual approval"}],
  "requires_review": false,
  "steps": [{"type": "noop"}],
  "current_step_index": 0
}
""",
        encoding="utf-8",
    )

    task = {
        "task_id": "blocked_task",
        "task_name": "blocked_task",
        "goal": "blocked task",
        "status": "waiting",
        "runtime_state_file": str(runtime_state_file),
        "task_dir": str(task_dir),
        "steps": [],
    }

    hydrated = scheduler._hydrate_task_from_workspace(task)

    assert isinstance(hydrated, dict)
    assert hydrated["task_id"] == "blocked_task"
    assert hydrated["status"] == "waiting"
    assert hydrated["next_action"] == "run_next_tick"
    assert hydrated["active_blocker_count"] == 1
    assert isinstance(hydrated.get("blockers"), list)
    assert hydrated["blockers"]
