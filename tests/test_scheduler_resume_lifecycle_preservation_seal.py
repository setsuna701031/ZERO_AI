from __future__ import annotations

import copy
from pathlib import Path

from core.runtime.task_runtime import TaskRuntime
from core.session.engineering_session_state_machine import EngineeringSessionStateMachine
from core.session.engineering_session_validator import EngineeringSessionValidator
from core.tasks.scheduler import Scheduler
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def _lifecycle_payload() -> dict:
    transition = EngineeringSessionStateMachine().build_transition_record(
        from_state="created",
        to_state="active",
        reason="plan accepted",
        trigger="planning_complete",
        evidence={"plan_id": "plan-1"},
        source="planner",
        session_id="session-preserved",
        task_id="task-preserved",
        created_at="2026-06-11T00:00:00+00:00",
    )
    return {
        "lifecycle": {"schema": "zero.lifecycle.v1", "state": "running"},
        "lifecycle_state": "running",
        "engineering_session_state": {
            "schema": "zero.engineering_session_state_machine.v1",
            "session_state": "active",
        },
        "transition_history": [copy.deepcopy(transition)],
        "last_transition": copy.deepcopy(transition),
        "session_id": "session-preserved",
        "task_id": "task-preserved",
        "operator_session_id": "operator-session-preserved",
        "operator_runtime_id": "operator-runtime-preserved",
        "evidence": {"plan_id": "plan-1"},
        "reason": "plan accepted",
        "trigger": "planning_complete",
        "source": "planner",
        "schema": "zero.lifecycle.payload.v1",
        "timestamp": "2026-06-11T00:00:00+00:00",
    }


def _task(tmp_path: Path, *, with_lifecycle: bool = True) -> dict:
    task = {
        "task_id": "task-preserved",
        "task_name": "task-preserved",
        "goal": "preserve lifecycle payload",
        "status": "failed",
        "steps": [],
        "task_dir": str(tmp_path / "tasks" / "task-preserved"),
        "runtime_state_file": str(tmp_path / "tasks" / "task-preserved" / "runtime_state.json"),
    }
    if with_lifecycle:
        task.update(_lifecycle_payload())
    return task


def test_runtime_state_resume_preserves_complete_lifecycle_payload(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    expected = _lifecycle_payload()
    saved = runtime.save_runtime_state(task, runtime.ensure_runtime_state(task))
    loaded = runtime.load_runtime_state(task)

    for key, value in expected.items():
        if key == "operator_session_id":
            continue
        assert loaded[key] == value
        assert saved[key] == value
    assert loaded["operator_session_id"] == expected["operator_session_id"]


def test_scheduler_terminal_resume_compact_preserves_runtime_state_and_task(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    runtime.save_runtime_state(task, runtime.ensure_runtime_state(task))
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=runtime)

    result = scheduler.run_one_step(copy.deepcopy(task), current_tick=2)

    assert result["action"] == "terminal_skip"
    assert result["runtime_state"]["engineering_session_state"]["session_state"] == "active"
    assert result["runtime_state"]["session_id"] == "session-preserved"
    assert result["runtime_state"]["task_id"] == "task-preserved"
    assert result["runtime_state"]["transition_history"] == _lifecycle_payload()["transition_history"]
    assert result["runtime_state"]["last_transition"] == _lifecycle_payload()["last_transition"]
    assert result["runtime_state"]["evidence"] == {"plan_id": "plan-1"}
    assert result["runtime_state"]["reason"] == "plan accepted"
    assert result["runtime_state"]["trigger"] == "planning_complete"
    assert result["runtime_state"]["source"] == "planner"
    assert result["runtime_state"]["schema"] == "zero.lifecycle.payload.v1"
    assert result["runtime_state"]["timestamp"] == "2026-06-11T00:00:00+00:00"
    assert result["lifecycle_payload_preservation"]["preserved"] is True
    assert result["lifecycle_payload_preservation"]["warning"] == ""
    assert result["task"]["engineering_session_state"] == _lifecycle_payload()["engineering_session_state"]


def test_scheduler_hydration_does_not_overwrite_durable_lifecycle_payload(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    durable = runtime.ensure_runtime_state(task)
    durable["engineering_session_state"]["session_state"] = "blocked"
    durable["lifecycle_state"] = "blocked"
    runtime.save_runtime_state(task, durable)
    inbound = copy.deepcopy(task)
    inbound["engineering_session_state"]["session_state"] = "active"
    inbound["lifecycle_state"] = "running"
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=runtime)

    hydrated = scheduler._hydrate_task_from_workspace(inbound)

    assert hydrated["engineering_session_state"]["session_state"] == "blocked"
    assert hydrated["lifecycle_state"] == "blocked"
    assert hydrated["transition_history"] == durable["transition_history"]


def test_explicit_continuation_preserves_payload_and_reopens_failed_runtime(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    runtime.save_runtime_state(task, runtime.ensure_runtime_state(task))
    continuation = copy.deepcopy(task)
    continuation["status"] = "queued"
    continuation["next_action"] = "run_next_tick"
    continuation["requires_review"] = False
    continuation["blockers"] = []
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=runtime)

    hydrated = scheduler._hydrate_task_from_workspace(continuation)

    assert hydrated["status"] == "running"
    assert hydrated["engineering_session_state"] == task["engineering_session_state"]
    assert hydrated["transition_history"] == task["transition_history"]


def test_missing_lifecycle_payload_reports_warning_without_fake_history(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path, with_lifecycle=False)
    runtime.save_runtime_state(task, runtime.ensure_runtime_state(task))
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=runtime)

    result = scheduler.run_one_step(task, current_tick=2)

    assert result["lifecycle_payload_preservation"]["preserved"] is False
    assert result["lifecycle_payload_preservation"]["warning"] == "missing_lifecycle_payload"
    assert "transition_history" not in result["runtime_state"]
    assert "engineering_session_state" not in result["runtime_state"]


def test_preserved_last_transition_remains_valid_for_next_transition(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    runtime.save_runtime_state(task, runtime.ensure_runtime_state(task))
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=runtime)
    result = scheduler.run_one_step(task, current_tick=2)
    last = result["runtime_state"]["last_transition"]
    next_record = EngineeringSessionStateMachine().build_transition_record(
        from_state=last["to_state"],
        to_state="blocked",
        reason="dependency unavailable",
        trigger="dependency_check",
        evidence={"dependency": "service"},
        source="scheduler_resume",
        session_id=last["session_id"],
        task_id=last["task_id"],
        created_at="2026-06-11T01:00:00+00:00",
    )

    assert EngineeringSessionValidator().validate(next_record).accepted is True


def test_continuation_boundary_identity_changes_when_step_payload_changes(tmp_path: Path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runtime=TaskRuntime(workspace_root=str(tmp_path)))
    task = {
        "task_id": "task-boundary",
        "status": "running",
        "current_step_index": 0,
        "steps": [{"id": "step-1", "type": "inspect", "force_fail": True}],
    }
    first = scheduler._run_step_via_task_runner(task=task, step=task["steps"][0])
    changed_step = copy.deepcopy(task["steps"][0])
    changed_step.pop("force_fail")
    second = scheduler._run_step_via_task_runner(task=task, step=changed_step)

    first_task = first.get("task", {})
    second_task = second.get("task", {})
    assert first_task.get("task_id") == second_task.get("task_id") == "task-boundary"
    assert first_task.get("scheduler_boundary_id") != second_task.get("scheduler_boundary_id")
