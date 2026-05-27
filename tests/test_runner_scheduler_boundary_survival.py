from __future__ import annotations

from pathlib import Path

from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.operator_session import OPERATOR_SESSION_RESUMABLE
from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap
from core.runtime.persistent_operator import PersistentOperatorRuntime
from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
from core.runtime.runtime_replay_engine import RuntimeReplayEngine
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime


def _operator_stack():
    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bootstrap = OperatorSessionBootstrap(operator_bridge=bridge)
    return runtime, bridge, bootstrap


def _success_handler(step, task=None, context=None, previous_result=None):
    return {
        "ok": True,
        "message": "runner boundary step completed",
        "final_answer": "runner boundary step completed",
        "evidence_refs": [f"evidence:{step.get('id')}:completed"],
        "result": {
            "seen_operator_session_id": (context or {}).get("operator_session_id"),
        },
    }


def _failure_handler(step, task=None, context=None, previous_result=None):
    return {
        "ok": False,
        "message": "runner boundary step failed",
        "final_answer": "runner boundary step failed",
        "evidence_refs": [f"evidence:{step.get('id')}:failed"],
        "error": {
            "type": "runner_boundary_failure",
            "message": "runner boundary step failed",
            "retryable": True,
        },
        "result": {
            "seen_operator_session_id": (context or {}).get("operator_session_id"),
        },
    }


def _write_file_boundary_handler(step, task=None, context=None, previous_result=None):
    if step.get("force_fail"):
        return _failure_handler(step, task=task, context=context, previous_result=previous_result)
    return _success_handler(step, task=task, context=context, previous_result=previous_result)


def _step_executor_authority(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "step_id": "scheduler-boundary",
        "authority_source": "step_executor",
        "execution_authority_endpoint": "step_executor",
        "runtime_session": f"runtime-session:{task_id}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "source": "test"},
        "trace_id": f"trace:{task_id}",
        "authority_status": "allowed",
        "action_type": "execute_or_mutation",
    }


def _task(tmp_path: Path, *, task_id: str, step_type: str) -> dict:
    task_dir = tmp_path / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "prove runner scheduler operator handoff",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [
            {"id": f"{task_id}-complete", "type": step_type, "path": "complete.txt", "content": "ok"},
            {
                "id": f"{task_id}-fail",
                "type": step_type,
                "path": "fail.txt",
                "content": "fail",
                "force_fail": True,
            },
        ],
        "metadata": {"suite": "runner_scheduler_boundary_survival"},
    }


def test_runtime_task_runner_preserves_operator_session_through_runtime_and_executor(tmp_path):
    from core.runtime.task_runner import TaskRunner

    operator_runtime, bridge, bootstrap = _operator_stack()
    task = _task(tmp_path, task_id="runner-task", step_type="runner_success")
    task["steps"][1]["type"] = "runner_failure"
    context = {"enable_operator_session": True}

    bootstrap_result = bootstrap.ensure_session_for_task(task, context=context)
    session_id = bootstrap_result["operator_session_id"]
    assert session_id

    task_runtime = TaskRuntime(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_executor.register_handler("runner_success", _success_handler)
    step_executor.register_handler("runner_failure", _failure_handler)
    runner = TaskRunner(task_runtime=task_runtime, step_executor=step_executor)

    first = runner.run_task_tick(task, current_tick=1)
    assert first["ok"] is True
    assert first["runtime_state"]["operator_session_id"] == session_id

    second = runner.run_task_tick(task, current_tick=2)
    assert second["ok"] is False
    assert second["runtime_state"]["operator_session_id"] == session_id

    session = operator_runtime.get_session(session_id)
    assert session is not None
    assert session.completed_steps == ["runner-task-complete"]
    assert session.failed_step == "runner-task-fail"
    assert session.status == OPERATOR_SESSION_RESUMABLE

    checkpoints = operator_runtime.get_session_checkpoints(session_id)
    assert {checkpoint.session_id for checkpoint in checkpoints} == {session_id}
    assert any(checkpoint.step_id == "runner-task-complete" and checkpoint.status == "completed" for checkpoint in checkpoints)
    assert any(checkpoint.step_id == "runner-task-fail" and checkpoint.status == "failed" for checkpoint in checkpoints)

    recovery_payload = RuntimeRecoveryExecutor(operator_bridge=bridge).recovery_resume_payload(session_id)
    assert recovery_payload is not None
    assert recovery_payload["session_id"] == session_id
    assert recovery_payload["failed_step"] == "runner-task-fail"
    assert recovery_payload["completed_steps"] == ["runner-task-complete"]

    replay_refs = RuntimeReplayEngine(operator_bridge=bridge).replay_evidence_refs(session_id)
    flattened = [ref for checkpoint_ref in replay_refs for ref in checkpoint_ref["evidence_refs"]]
    assert "evidence:runner-task-complete:completed" in flattened
    assert "evidence:runner-task-fail:failed" in flattened


def test_tasks_scheduler_forwards_operator_session_to_step_executor_without_owning_state(tmp_path):
    from core.tasks.scheduler import Scheduler

    operator_runtime, bridge, bootstrap = _operator_stack()
    task = _task(tmp_path, task_id="scheduler-task", step_type="write_file")
    task["execution_authority"] = _step_executor_authority("scheduler-task")
    context = {"enable_operator_session": True}
    bootstrap_result = bootstrap.ensure_session_for_task(task, context=context)
    session_id = bootstrap_result["operator_session_id"]

    step_executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_executor.register_handler("write_file", _write_file_boundary_handler)
    scheduler = Scheduler(workspace_dir=str(tmp_path), step_executor=step_executor, debug=False)

    first = scheduler.run_one_step(task=task, current_tick=1)
    assert first["ok"] is True
    assert task["operator_session_id"] == session_id

    task["current_step_index"] = first["current_step_index"]
    task["status"] = first["status"]
    second = scheduler.run_one_step(task=task, current_tick=2)
    assert second["ok"] is True

    session = operator_runtime.get_session(session_id)
    assert session is not None
    assert session.completed_steps == ["scheduler-task-complete"]
    assert session.failed_step == "scheduler-task-fail"
    assert session.status == OPERATOR_SESSION_RESUMABLE

    failed_checkpoints = [
        checkpoint
        for checkpoint in operator_runtime.get_session_checkpoints(session_id)
        if checkpoint.step_id == "scheduler-task-fail" and checkpoint.status == "failed"
    ]
    assert failed_checkpoints
    assert failed_checkpoints[-1].session_id == session_id

    recovery_payload = RuntimeRecoveryExecutor(operator_bridge=bridge).recovery_resume_payload(session_id)
    assert recovery_payload is not None
    assert recovery_payload["session_id"] == session_id
    assert recovery_payload["failed_step"] == "scheduler-task-fail"

    replay_refs = RuntimeReplayEngine(operator_bridge=bridge).replay_evidence_refs(session_id)
    flattened = [ref for checkpoint_ref in replay_refs for ref in checkpoint_ref["evidence_refs"]]
    assert "evidence:scheduler-task-complete:completed" in flattened
    assert "evidence:scheduler-task-fail:failed" in flattened


def test_no_bridge_missing_session_and_scheduler_static_boundary_are_safe(tmp_path):
    from core.runtime.task_runner import TaskRunner
    from core.tasks.scheduler import Scheduler

    task = _task(tmp_path, task_id="plain-task", step_type="plain_success")
    task["steps"] = [{"id": "plain-step", "type": "plain_success"}]

    step_executor = StepExecutor(workspace_root=str(tmp_path))
    step_executor.register_handler("plain_success", _success_handler)
    runner = TaskRunner(
        task_runtime=TaskRuntime(workspace_root=str(tmp_path)),
        step_executor=step_executor,
    )
    runner_result = runner.run_task_tick(task, current_tick=1)
    assert runner_result["ok"] is True

    scheduler = Scheduler(workspace_dir=str(tmp_path), step_executor=StepExecutor(workspace_root=str(tmp_path)))
    scheduler_task = {
        "task_id": "scheduler-plain",
        "task_name": "scheduler-plain",
        "status": "queued",
        "steps": [{"id": "noop", "type": "noop", "message": "ok"}],
    }
    scheduler_result = scheduler.run_one_step(task=scheduler_task, current_tick=1)
    assert scheduler_result["ok"] is True

    bridge = OperatorIntegrationBridge(PersistentOperatorRuntime())
    assert RuntimeRecoveryExecutor(operator_bridge=bridge).recovery_resume_payload("missing-session") is None
    assert RuntimeReplayEngine(operator_bridge=bridge).replay_evidence_refs("missing-session") == []

    scheduler_source = Path("core/tasks/scheduler.py").read_text(encoding="utf-8")
    banned = [
        "PersistentOperatorRuntime",
        "OperatorIntegrationBridge",
        "OperatorSessionBootstrap",
        "save_to_dir",
        "load_from_dir",
        "record_checkpoint",
        "mark_step_completed",
        "mark_step_failed",
        "operator.checkpoint",
        "operator.session",
    ]
    for token in banned:
        assert token not in scheduler_source
