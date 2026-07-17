from __future__ import annotations

from pathlib import Path

from core.runtime.execution_gateway import build_runtime_execution_request
from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.operator_session import OPERATOR_SESSION_RESUMABLE
from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap
from core.runtime.persistent_operator import PersistentOperatorRuntime
from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
from core.runtime.runtime_replay_engine import RuntimeReplayEngine
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime


def _task(tmp_path: Path) -> dict:
    return {
        "task_id": "handoff-task",
        "goal": "prove governed runtime handoff continuity",
        "steps": [
            {"id": "step-complete", "type": "handoff_success", "name": "complete"},
            {"id": "step-fail", "type": "handoff_failure", "name": "fail"},
        ],
        "runtime_state_file": str(tmp_path / "runtime_state.json"),
        "metadata": {"suite": "handoff_continuity"},
    }


def _success_handler(step, task=None, context=None, previous_result=None):
    return {
        "ok": True,
        "message": "step completed",
        "final_answer": "step completed",
        "evidence_refs": ["evidence:step-complete"],
        "result": {
            "seen_operator_session_id": (context or {}).get("operator_session_id"),
        },
    }


def _failure_handler(step, task=None, context=None, previous_result=None):
    return {
        "ok": False,
        "message": "step failed",
        "final_answer": "step failed",
        "evidence_refs": ["evidence:step-fail"],
        "error": {
            "type": "intentional_handoff_failure",
            "message": "step failed",
            "retryable": True,
        },
        "result": {
            "seen_operator_session_id": (context or {}).get("operator_session_id"),
        },
    }


def test_real_task_context_handoff_continuity_through_runtime_executor_recovery_and_replay(tmp_path):
    operator_runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(operator_runtime)
    bootstrap = OperatorSessionBootstrap(operator_bridge=bridge)
    task = _task(tmp_path)
    context = {"enable_operator_session": True}

    bootstrap_result = bootstrap.ensure_session_for_task(task, context=context)
    session_id = bootstrap_result["operator_session_id"]

    assert session_id
    assert task["operator_session_id"] == session_id
    assert task["metadata"]["operator_session_id"] == session_id
    assert context["operator_session_id"] == session_id

    task_runtime = TaskRuntime(workspace_root=str(tmp_path), operator_bridge=bridge)
    initial_state = task_runtime.ensure_runtime_state(task)
    assert initial_state["operator_session_id"] == session_id

    executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    executor.register_handler("handoff_success", _success_handler)
    executor.register_handler("handoff_failure", _failure_handler)

    completed_result = executor.execute_step(
        task["steps"][0],
        task=task,
        context=context,
        step_index=1,
        step_count=2,
    )
    assert completed_result["ok"] is True
    assert completed_result["result"]["result"]["seen_operator_session_id"] == session_id

    advanced = task_runtime.advance_step(task, step_result=completed_result)
    assert advanced["runtime_state"]["operator_session_id"] == session_id

    failed_result = executor.execute_step(
        task["steps"][1],
        task=task,
        context=context,
        step_index=2,
        step_count=2,
        max_attempts=1,
    )
    assert failed_result["ok"] is False
    assert failed_result["result"]["result"]["seen_operator_session_id"] == session_id

    failed = task_runtime.record_step_failure(
        task,
        step=task["steps"][1],
        step_result=failed_result,
        status="running",
    )
    assert failed["runtime_state"]["operator_session_id"] == session_id

    session = operator_runtime.get_session(session_id)
    assert session is not None
    assert session.session_id == session_id
    assert session.completed_steps == ["step-complete"]
    assert session.failed_step == "step-fail"
    assert session.status == OPERATOR_SESSION_RESUMABLE
    assert session.last_error

    checkpoints = operator_runtime.get_session_checkpoints(session_id)
    assert checkpoints
    assert {checkpoint.session_id for checkpoint in checkpoints} == {session_id}
    assert any(
        checkpoint.step_id == "step-complete" and checkpoint.status == "completed"
        for checkpoint in checkpoints
    )
    assert any(
        checkpoint.step_id == "step-fail" and checkpoint.status == "failed"
        for checkpoint in checkpoints
    )

    recovery = RuntimeRecoveryExecutor(operator_bridge=bridge)
    payload = recovery.recovery_resume_payload(session_id)
    assert payload is not None
    assert payload["session_id"] == session_id
    assert payload["failed_step"] == "step-fail"
    assert payload["last_error"]
    assert payload["completed_steps"] == ["step-complete"]
    assert payload["checkpoint_ids"] == session.checkpoint_ids

    replay = RuntimeReplayEngine(operator_bridge=bridge)
    evidence_refs = replay.replay_evidence_refs(session_id)
    flattened = [
        evidence_ref
        for checkpoint_ref in evidence_refs
        for evidence_ref in checkpoint_ref["evidence_refs"]
    ]
    assert "evidence:step-complete" in flattened
    assert "evidence:step-fail" in flattened


def test_operator_session_id_precedence_context_task_metadata_then_bootstrap(tmp_path):
    bootstrap = OperatorSessionBootstrap(operator_runtime=PersistentOperatorRuntime())
    task = {
        "task_id": "priority-task",
        "operator_session_id": "task-session",
        "metadata": {"operator_session_id": "metadata-session"},
    }
    context = {"operator_session_id": "context-session"}
    assert bootstrap.extract_session_id(task=task, context=context) == "context-session"

    context.clear()
    assert bootstrap.extract_session_id(task=task, context=context) == "task-session"

    task.pop("operator_session_id")
    assert bootstrap.extract_session_id(task=task, context=context) == "metadata-session"

    created_task = _task(tmp_path)
    created_context = {"enable_operator_session": True}
    created = bootstrap.ensure_session_for_task(created_task, context=created_context)
    assert created["operator_session_id"]
    assert created_context["operator_session_id"] == created["operator_session_id"]


def test_step_executor_uses_context_session_before_task_session(tmp_path):
    operator_runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(operator_runtime)
    bridge.on_session_start(
        task_id="task",
        goal="context wins",
        pending_steps=[{"id": "step-complete", "type": "handoff_success"}],
        session_id="context-session",
    )
    bridge.on_session_start(
        task_id="task",
        goal="task loses",
        pending_steps=[{"id": "step-complete", "type": "handoff_success"}],
        session_id="task-session",
    )

    executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    executor.register_handler("handoff_success", _success_handler)
    result = executor.execute_step(
        {"id": "step-complete", "type": "handoff_success"},
        task={"operator_session_id": "task-session"},
        context={"operator_session_id": "context-session"},
    )

    assert result["ok"] is True
    assert operator_runtime.get_session("context-session").completed_steps == ["step-complete"]
    assert operator_runtime.get_session("task-session").completed_steps == []


def test_execution_gateway_forwards_optional_operator_session_without_owning_state():
    request = build_runtime_execution_request(
        ["echo", "ok"],
        operator_session_id="session-1",
        context={"operator_session_id": "context-session"},
    )

    assert request.metadata["operator_session_id"] == "session-1"
    assert request.lineage["operator_session_id"] == "session-1"


def test_no_bridge_missing_session_and_scheduler_boundaries_are_safe(tmp_path):
    task = _task(tmp_path)
    context = {}

    runtime = TaskRuntime(workspace_root=str(tmp_path))
    state = runtime.ensure_runtime_state(task)
    assert "operator_session_id" not in state

    executor = StepExecutor(workspace_root=str(tmp_path))
    executor.register_handler("handoff_success", _success_handler)
    result = executor.execute_step(task["steps"][0], task=task, context=context)
    assert result["ok"] is True

    recovery = RuntimeRecoveryExecutor(operator_bridge=OperatorIntegrationBridge(PersistentOperatorRuntime()))
    replay = RuntimeReplayEngine(operator_bridge=OperatorIntegrationBridge(PersistentOperatorRuntime()))
    assert recovery.recovery_resume_payload("missing-session") is None
    assert replay.replay_evidence_refs("missing-session") == []

    scheduler_source = Path("core/runtime/task_scheduler.py").read_text(encoding="utf-8")
    assert "PersistentOperatorRuntime" not in scheduler_source
    assert "OperatorIntegrationBridge" not in scheduler_source
    assert "OperatorSessionBootstrap" not in scheduler_source
    assert "record_checkpoint(" not in scheduler_source
    assert "mark_step_completed(" not in scheduler_source
    assert "mark_step_failed(" not in scheduler_source
