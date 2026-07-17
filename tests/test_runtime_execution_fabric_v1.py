from __future__ import annotations

from core.runtime.runtime_execution_fabric import (
    EXECUTION_STATUS_COMPLETED,
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_RECOVERED,
    EXECUTION_STATUS_RECOVERY_QUEUED,
    RuntimeExecutionFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator


def test_execution_fabric_checkpoint_and_complete(tmp_path):
    fabric = RuntimeExecutionFabric.with_workspace(tmp_path)

    execution = fabric.start_execution(
        source_session_id="session-1",
        task_id="task-1",
        steps=[
            {"type": "noop", "name": "a"},
            {"type": "noop", "name": "b"},
        ],
    )

    assert execution.status == "running"
    assert len(execution.checkpoints) == 1

    fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop", "name": "a"},
        result={"ok": True},
    )
    completed = fabric.complete_execution(
        execution.execution_id,
        result={"ok": True, "final_answer": "done"},
    )

    assert completed.status == EXECUTION_STATUS_COMPLETED
    assert len(completed.checkpoints) == 3
    assert completed.checkpoints[-1].checkpoint_type == "complete"


def test_execution_fabric_failure_to_recovery_to_continuation(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "recovery-exec-1",
            "replay_id": "replay-exec-1",
        },
    )
    fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "fabric",
        recovery_orchestrator=orchestrator,
    )

    execution = fabric.start_execution(
        source_session_id="session-2",
        task_id="task-2",
        steps=[
            {"type": "noop", "name": "a"},
            {"type": "noop", "name": "b"},
            {"type": "noop", "name": "c"},
        ],
    )

    failed = fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop", "name": "a"},
        result={"ok": False, "failed": True, "message": "boom"},
    )
    assert failed.status == EXECUTION_STATUS_FAILED

    queued = fabric.queue_recovery(
        execution.execution_id,
        current_tick=10,
        reason="step failed",
    )
    assert queued.status == EXECUTION_STATUS_RECOVERY_QUEUED
    assert queued.recovery_ticket["source_session_id"] == "session-2"

    continuation = fabric.consume_recovery_and_build_continuation(
        execution.execution_id,
        current_tick=10,
    )

    assert continuation.execution_id == execution.execution_id
    assert continuation.resume_step_index == 1

    recovered = fabric.get_execution(execution.execution_id)
    assert recovered.status == EXECUTION_STATUS_RECOVERED
    assert recovered.replay_ref["replay_id"] == "replay-exec-1"
    assert recovered.continuation_ref["continuation_id"] == continuation.continuation_id


def test_execution_fabric_resume_from_continuation_completes_remaining_steps(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "recovery-exec-2",
            "replay_id": "replay-exec-2",
        },
    )
    fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "fabric",
        recovery_orchestrator=orchestrator,
    )

    execution = fabric.start_execution(
        source_session_id="session-3",
        task_id="task-3",
        steps=[
            {"type": "noop", "name": "a"},
            {"type": "noop", "name": "b"},
        ],
    )
    fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop", "name": "a"},
        result={"ok": False, "failed": True},
    )
    fabric.queue_recovery(execution.execution_id, current_tick=1)
    continuation = fabric.consume_recovery_and_build_continuation(
        execution.execution_id,
        current_tick=1,
    )

    ran_steps = []

    def runner(step, context):
        ran_steps.append(step["name"])
        return {"ok": True, "step": step["name"]}

    completed = fabric.resume_from_continuation(
        continuation.continuation_id,
        runner=runner,
    )

    assert completed.status == EXECUTION_STATUS_COMPLETED
    assert ran_steps == ["b"]
    assert completed.checkpoints[-1].checkpoint_type == "complete"


def test_execution_fabric_persistence_reload(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "fabric",
        recovery_orchestrator=orchestrator,
    )

    execution = fabric.start_execution(
        source_session_id="session-4",
        task_id="task-4",
        steps=[{"type": "noop"}],
    )
    fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop"},
        result={"ok": True},
    )

    reloaded = RuntimeExecutionFabric.with_workspace(
        tmp_path / "fabric",
        recovery_orchestrator=orchestrator,
    )

    loaded = reloaded.get_execution(execution.execution_id)
    assert loaded.execution_id == execution.execution_id
    assert len(loaded.checkpoints) == 2


def test_execution_fabric_recovery_incident_contains_latest_checkpoint(tmp_path):
    fabric = RuntimeExecutionFabric.with_workspace(tmp_path)

    execution = fabric.start_execution(
        source_session_id="session-5",
        task_id="task-5",
        steps=[{"type": "noop"}],
    )
    fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop"},
        result={"ok": False, "failed": True, "message": "failure"},
    )

    incident = fabric.create_recovery_incident(
        execution.execution_id,
        reason="unit failure",
        current_tick=7,
    )

    assert incident["incident_type"] == "runtime_execution_failed"
    assert incident["source_session_id"] == "session-5"
    assert incident["payload"]["latest_checkpoint"]["checkpoint_type"] == "failure"
