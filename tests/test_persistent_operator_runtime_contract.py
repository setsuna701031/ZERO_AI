import json

from core.runtime.operator_checkpoint import (

    OPERATOR_CHECKPOINT_COMPLETED,
    OPERATOR_CHECKPOINT_FAILED,
    OperatorCheckpoint,
)
from core.runtime.operator_session import (
    OPERATOR_SESSION_ABORTED,
    OPERATOR_SESSION_COMPLETED,
    OPERATOR_SESSION_RESUMABLE,
    OPERATOR_SESSION_RUNNING,
    OperatorSession,
)
from core.runtime.persistent_operator import PersistentOperatorRuntime
import pytest

pytestmark = [pytest.mark.contract]



def test_session_can_be_created():
    runtime = PersistentOperatorRuntime()

    session = runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        current_goal="ship persistent operator",
        pending_steps=["step-1", "step-2"],
        metadata={"source": "contract"},
    )

    assert session.session_id == "session-1"
    assert session.task_id == "task-1"
    assert session.status == OPERATOR_SESSION_RUNNING
    assert session.pending_steps == ["step-1", "step-2"]
    assert session.metadata["source"] == "contract"


def test_checkpoint_can_be_recorded():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(session_id="session-1", task_id="task-1")

    checkpoint = runtime.record_checkpoint(
        session_id="session-1",
        checkpoint_id="checkpoint-1",
        step_id="step-1",
        step_type="analysis",
        status="running",
        state_snapshot={"cursor": "step-1"},
        evidence_refs=["evidence-1"],
    )
    session = runtime.get_session("session-1")

    assert checkpoint.checkpoint_id == "checkpoint-1"
    assert checkpoint.state_snapshot == {"cursor": "step-1"}
    assert checkpoint.evidence_refs == ["evidence-1"]
    assert session is not None
    assert session.checkpoint_ids == ["checkpoint-1"]


def test_completed_step_state_is_preserved():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        pending_steps=["step-1", "step-2"],
    )

    session = runtime.mark_step_completed(
        session_id="session-1",
        step_id="step-1",
        checkpoint_id="checkpoint-1",
        evidence_refs=["evidence-1"],
    )
    checkpoint = runtime.get_checkpoint("checkpoint-1")

    assert session.completed_steps == ["step-1"]
    assert session.pending_steps == ["step-2"]
    assert checkpoint is not None
    assert checkpoint.status == OPERATOR_CHECKPOINT_COMPLETED


def test_failed_step_enters_resumable_and_keeps_error():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        pending_steps=["step-1", "step-2"],
    )
    runtime.mark_step_completed(session_id="session-1", step_id="step-1")

    session = runtime.mark_step_failed(
        session_id="session-1",
        step_id="step-2",
        checkpoint_id="checkpoint-failed",
        error="tool timeout",
        state_snapshot={"last_good": "step-1"},
        evidence_refs=["evidence-failed"],
    )
    checkpoint = runtime.get_checkpoint("checkpoint-failed")

    assert session.status == OPERATOR_SESSION_RESUMABLE
    assert session.failed_step == "step-2"
    assert session.last_error == "tool timeout"
    assert session.completed_steps == ["step-1"]
    assert checkpoint is not None
    assert checkpoint.status == OPERATOR_CHECKPOINT_FAILED
    assert checkpoint.error_summary == "tool timeout"


def test_resume_plan_can_be_generated():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        pending_steps=["step-1", "step-2"],
    )
    runtime.mark_step_completed(
        session_id="session-1",
        step_id="step-1",
        checkpoint_id="checkpoint-1",
        evidence_refs=["evidence-1"],
    )
    runtime.mark_step_failed(
        session_id="session-1",
        step_id="step-2",
        checkpoint_id="checkpoint-2",
        error="blocked",
        state_snapshot={"cursor": "step-2"},
        evidence_refs=["evidence-2"],
        resume_hint="retry step-2",
    )

    plan = runtime.build_resume_plan("session-1")
    payload = plan.to_dict()

    assert payload["status"] == "ready"
    assert payload["resume_from_checkpoint_id"] == "checkpoint-2"
    assert payload["resume_from_step_id"] == "step-2"
    assert payload["completed_steps"] == ["step-1"]
    assert payload["evidence_refs"] == ["evidence-1", "evidence-2"]
    assert payload["state_snapshot"] == {"cursor": "step-2"}
    assert payload["resume_hint"] == "retry step-2"


def test_resume_session_does_not_lose_completed_steps():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        pending_steps=["step-1", "step-2"],
    )
    runtime.mark_step_completed(session_id="session-1", step_id="step-1")
    runtime.mark_step_failed(
        session_id="session-1",
        step_id="step-2",
        checkpoint_id="checkpoint-2",
        error="blocked",
    )

    assert runtime.can_resume("session-1") is True
    plan = runtime.resume_session("session-1")
    resumed = runtime.get_session("session-1")

    assert plan.completed_steps == ["step-1"]
    assert resumed is not None
    assert resumed.status == OPERATOR_SESSION_RUNNING
    assert resumed.completed_steps == ["step-1"]
    assert resumed.resume_count == 1
    assert resumed.metadata["resume_plans"][0]["resume_from_step_id"] == "step-2"


def test_complete_session_closes_terminal_state():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(session_id="session-1", task_id="task-1")

    session = runtime.complete_session("session-1")

    assert session.status == OPERATOR_SESSION_COMPLETED
    assert session.failed_step is None
    assert session.last_error == ""
    assert runtime.can_resume("session-1") is False


def test_abort_session_closes_terminal_state():
    runtime = PersistentOperatorRuntime()
    runtime.start_session(session_id="session-1", task_id="task-1")

    session = runtime.abort_session("session-1", reason="operator stopped")

    assert session.status == OPERATOR_SESSION_ABORTED
    assert session.last_error == "operator stopped"
    assert runtime.can_resume("session-1") is False


def test_session_and_checkpoint_json_roundtrip():
    session = OperatorSession(
        session_id="session-1",
        task_id="task-1",
        status=OPERATOR_SESSION_RESUMABLE,
        completed_steps=["step-1"],
        pending_steps=["step-2"],
        failed_step="step-2",
        last_error="blocked",
        checkpoint_ids=["checkpoint-1"],
        resume_count=2,
        metadata={"k": "v"},
    )
    checkpoint = OperatorCheckpoint(
        checkpoint_id="checkpoint-1",
        session_id="session-1",
        task_id="task-1",
        step_id="step-2",
        step_type="execute",
        status=OPERATOR_CHECKPOINT_FAILED,
        state_snapshot={"cursor": "step-2"},
        evidence_refs=["evidence-1"],
        error_summary="blocked",
        resume_hint="retry",
    )

    loaded_session = OperatorSession.from_dict(json.loads(json.dumps(session.to_dict())))
    loaded_checkpoint = OperatorCheckpoint.from_dict(json.loads(json.dumps(checkpoint.to_dict())))

    assert loaded_session.to_dict() == session.to_dict()
    assert loaded_checkpoint.to_dict() == checkpoint.to_dict()


def test_session_and_checkpoint_can_be_saved_and_restored(tmp_path):
    runtime = PersistentOperatorRuntime(storage_dir=tmp_path)
    runtime.start_session(
        session_id="session-1",
        task_id="task-1",
        pending_steps=["step-1"],
    )
    runtime.mark_step_failed(
        session_id="session-1",
        step_id="step-1",
        checkpoint_id="checkpoint-1",
        error="blocked",
        evidence_refs=["evidence-1"],
    )

    restored = PersistentOperatorRuntime(storage_dir=tmp_path)
    session = restored.get_session("session-1")
    checkpoint = restored.get_checkpoint("checkpoint-1")
    plan = restored.build_resume_plan("session-1")

    assert session is not None
    assert session.status == OPERATOR_SESSION_RESUMABLE
    assert checkpoint is not None
    assert checkpoint.evidence_refs == ["evidence-1"]
    assert plan.resume_from_checkpoint_id == "checkpoint-1"
