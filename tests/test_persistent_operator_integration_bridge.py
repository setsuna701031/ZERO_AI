from dataclasses import dataclass

from core.runtime.operator_session import OPERATOR_SESSION_RESUMABLE
from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.persistent_operator import PersistentOperatorRuntime
from tests.authority_test_support import owned_step_executor


@dataclass
class ObjectStep:
    step_id: str
    step_type: str
    name: str = ""


def test_bridge_can_start_session():
    bridge = OperatorIntegrationBridge()

    session = bridge.on_session_start(
        task_id="task-1",
        goal="finish integration",
        pending_steps=[
            {"id": "step-1", "type": "analysis"},
            {"step_id": "step-2", "step_type": "execute"},
        ],
        metadata={"source": "test"},
        session_id="session-1",
    )

    assert session.session_id == "session-1"
    assert session.current_goal == "finish integration"
    assert session.pending_steps == ["step-1", "step-2"]
    assert session.metadata["source"] == "test"


def test_completed_outcome_writes_completed_steps():
    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )

    session = bridge.on_step_completed(
        "session-1",
        {"id": "step-1", "type": "verify"},
        result={"ok": True, "message": "done"},
    )

    assert session.completed_steps == ["step-1"]
    assert session.pending_steps == []


def test_failed_outcome_makes_session_resumable():
    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )

    session = bridge.on_step_failed(
        "session-1",
        {"id": "step-1", "type": "verify"},
        error={"type": "timeout", "message": "tool timeout"},
        resume_hint="retry verify",
    )

    assert session.status == OPERATOR_SESSION_RESUMABLE
    assert session.failed_step == "step-1"
    assert session.last_error == "tool timeout"


def test_checkpoint_contains_evidence_refs():
    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )

    bridge.on_step_started("session-1", {"id": "step-1", "type": "verify"})
    bridge.on_step_completed(
        "session-1",
        {"id": "step-1", "type": "verify"},
        result={"ok": True, "evidence_refs": ["result-evidence"]},
        evidence_refs=["explicit-evidence"],
    )

    checkpoints = runtime.get_session_checkpoints("session-1")

    assert checkpoints[-1].evidence_refs == ["explicit-evidence", "result-evidence"]
    assert checkpoints[-1].state_snapshot["phase"] == "completed"


def test_resume_payload_can_be_generated():
    bridge = OperatorIntegrationBridge()
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )
    bridge.on_step_failed(
        "session-1",
        {"id": "step-1", "type": "verify"},
        error="blocked",
        evidence_refs=["evidence-1"],
    )

    payload = bridge.build_resume_payload("session-1")

    assert payload["kind"] == "operator_resume_payload"
    assert payload["resume_plan"]["resume_from_step_id"] == "step-1"
    assert payload["checkpoint_evidence"][0]["evidence_refs"] == ["evidence-1"]


def test_replay_evidence_refs_can_be_read():
    bridge = OperatorIntegrationBridge()
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )
    bridge.on_step_completed(
        "session-1",
        {"id": "step-1", "type": "verify"},
        evidence_refs=["evidence-1"],
    )

    refs = bridge.replay_evidence_refs("session-1")

    assert refs[0]["kind"] == "operator_checkpoint"
    assert refs[0]["step_id"] == "step-1"
    assert refs[0]["evidence_refs"] == ["evidence-1"]


def test_step_executor_and_task_runtime_init_without_bridge():
    from core.runtime.step_executor import StepExecutor
    from core.runtime.task_runtime import TaskRuntime

    executor = StepExecutor(workspace_root="workspace")
    runtime = TaskRuntime(workspace_root="workspace")

    assert getattr(executor, "operator_bridge", None) is None
    assert getattr(runtime, "operator_bridge", None) is None


def test_dict_and_object_steps_are_supported():
    bridge = OperatorIntegrationBridge()
    dict_step = bridge.normalize_step({"id": "dict-step", "type": "command", "name": "Dict"})
    object_step = bridge.normalize_step(ObjectStep(step_id="object-step", step_type="verify", name="Object"))

    assert dict_step["step_id"] == "dict-step"
    assert dict_step["step_type"] == "command"
    assert object_step["step_id"] == "object-step"
    assert object_step["step_type"] == "verify"


def test_missing_step_id_uses_deterministic_fallback():
    bridge = OperatorIntegrationBridge()
    step = {"type": "verify", "name": "missing id"}

    first = bridge.step_id_for(step)
    second = bridge.step_id_for({"name": "missing id", "type": "verify"})

    assert first == second
    assert first.startswith("step:")


def test_step_executor_optional_bridge_records_outcome():
    from core.runtime.step_executor import StepExecutor

    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "verify-1", "type": "operator_verification"}],
        session_id="session-1",
    )
    executor = owned_step_executor(workspace_root="workspace", operator_bridge=bridge)

    result = executor.execute_step(
        {"id": "verify-1", "type": "operator_verification", "command": "noop"},
        task={"task_id": "task-1", "operator_session_id": "session-1"},
        context={"operator_session_id": "session-1"},
    )
    session = runtime.get_session("session-1")

    assert result["ok"] is True
    assert session is not None
    assert session.completed_steps == ["verify-1"]


def test_recovery_and_replay_optional_helpers_read_bridge_data():
    from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine

    bridge = OperatorIntegrationBridge()
    bridge.on_session_start(
        task_id="task-1",
        goal="goal",
        pending_steps=[{"id": "step-1", "type": "verify"}],
        session_id="session-1",
    )
    bridge.on_step_failed("session-1", {"id": "step-1", "type": "verify"}, "blocked")

    recovery = RuntimeRecoveryExecutor(operator_bridge=bridge)
    replay = RuntimeReplayEngine(operator_bridge=bridge)

    assert recovery.operator_resume_payload("session-1")["resume_plan"]["failed_step"] == "step-1"
    assert replay.operator_replay_evidence_refs("session-1")[0]["step_id"] == "step-1"
