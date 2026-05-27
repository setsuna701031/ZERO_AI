from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.operator_session import (
    OPERATOR_SESSION_COMPLETED,
    OPERATOR_SESSION_RESUMABLE,
    OPERATOR_SESSION_RUNNING,
)
from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap
from core.runtime.persistent_operator import PersistentOperatorRuntime
from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
from core.runtime.runtime_replay_engine import RuntimeReplayEngine


def _long_task(tmp_path):
    return {
        "task_id": "survival-task",
        "goal": "complete a persistent survival loop",
        "steps": [
            {"id": "step_1", "type": "fake_success", "name": "first"},
            {"id": "step_2", "type": "fake_success", "name": "second"},
            {"id": "step_3", "type": "fake_failure_then_resume", "name": "third"},
            {"id": "step_4", "type": "fake_success", "name": "fourth"},
        ],
        "runtime_state_file": str(tmp_path / "task_runtime_state.json"),
        "metadata": {"kind": "survival_smoke"},
    }


def _record_fake_success(bridge, session_id, step, evidence_ref, message):
    return bridge.on_step_completed(
        session_id,
        step,
        result={
            "ok": True,
            "message": message,
            "evidence_refs": [evidence_ref],
        },
    )


def _record_fake_failure(bridge, session_id, step, evidence_ref, message):
    return bridge.on_step_failed(
        session_id,
        step,
        error={"type": "intentional_failure", "message": message},
        evidence_refs=[evidence_ref],
        resume_hint="retry step_3 after reload",
    )


def test_operator_runtime_survives_failure_reload_resume_and_complete(tmp_path):
    storage_dir = tmp_path / "operator_runtime"
    runtime = PersistentOperatorRuntime(storage_dir=storage_dir)
    bridge = OperatorIntegrationBridge(runtime)
    bootstrap = OperatorSessionBootstrap(operator_bridge=bridge)
    task = _long_task(tmp_path)
    context = {"enable_operator_session": True}

    bootstrap_result = bootstrap.ensure_session_for_task(task, context=context)
    session_id = bootstrap_result["operator_session_id"]

    assert session_id
    assert task["operator_session_id"] == session_id
    assert context["operator_session_id"] == session_id

    _record_fake_success(
        bridge,
        session_id,
        task["steps"][0],
        "evidence:step_1:success",
        "step 1 completed",
    )
    _record_fake_success(
        bridge,
        session_id,
        task["steps"][1],
        "evidence:step_2:success",
        "step 2 completed",
    )

    session_after_two = runtime.get_session(session_id)
    assert session_after_two is not None
    assert session_after_two.completed_steps == ["step_1", "step_2"]
    assert session_after_two.status == OPERATOR_SESSION_RUNNING

    _record_fake_failure(
        bridge,
        session_id,
        task["steps"][2],
        "evidence:step_3:failed",
        "step 3 failed intentionally",
    )

    failed_session = runtime.get_session(session_id)
    assert failed_session is not None
    assert failed_session.status == OPERATOR_SESSION_RESUMABLE
    assert failed_session.failed_step == "step_3"
    assert failed_session.completed_steps == ["step_1", "step_2"]
    assert failed_session.last_error == "step 3 failed intentionally"
    assert "step_3" in failed_session.pending_steps

    failed_checkpoints = [
        checkpoint
        for checkpoint in runtime.get_session_checkpoints(session_id)
        if checkpoint.step_id == "step_3" and checkpoint.status == "failed"
    ]
    assert failed_checkpoints
    assert failed_checkpoints[-1].evidence_refs == ["evidence:step_3:failed"]

    exported = runtime.save_to_dir(storage_dir)
    assert exported["sessions"][0]["session_id"] == session_id

    reloaded_runtime = PersistentOperatorRuntime.load_from_dir(storage_dir)
    reloaded_bridge = OperatorIntegrationBridge(reloaded_runtime)
    reloaded_recovery = RuntimeRecoveryExecutor(operator_bridge=reloaded_bridge)
    reloaded_replay = RuntimeReplayEngine(operator_bridge=reloaded_bridge)

    reloaded_session = reloaded_runtime.get_session(session_id)
    assert reloaded_session is not None
    assert reloaded_session.session_id == session_id
    assert reloaded_session.completed_steps == ["step_1", "step_2"]
    assert reloaded_session.status == OPERATOR_SESSION_RESUMABLE

    resume_payload = reloaded_recovery.operator_resume_payload(session_id)
    assert resume_payload["session_id"] == session_id
    assert resume_payload["task_id"] == "survival-task"
    assert resume_payload["status"] == OPERATOR_SESSION_RESUMABLE
    assert resume_payload["failed_step"] == "step_3"
    assert resume_payload["last_error"] == "step 3 failed intentionally"
    assert resume_payload["completed_steps"] == ["step_1", "step_2"]
    assert resume_payload["checkpoint_ids"] == reloaded_session.checkpoint_ids
    assert resume_payload["resume_count"] == 0
    assert resume_payload["resume_plan"]["resume_from_step_id"] == "step_3"
    assert resume_payload["resume_plan"]["resume_hint"]

    resume_plan = reloaded_runtime.resume_session(
        session_id,
        metadata={"source": "survival_loop"},
    )
    resumed_session = reloaded_runtime.get_session(session_id)
    assert resume_plan.completed_steps == ["step_1", "step_2"]
    assert resumed_session is not None
    assert resumed_session.resume_count == 1
    assert resumed_session.status == OPERATOR_SESSION_RUNNING

    _record_fake_success(
        reloaded_bridge,
        session_id,
        task["steps"][2],
        "evidence:step_3:success",
        "step 3 replacement completed",
    )
    _record_fake_success(
        reloaded_bridge,
        session_id,
        task["steps"][3],
        "evidence:step_4:success",
        "step 4 completed",
    )

    continued_session = reloaded_runtime.get_session(session_id)
    assert continued_session is not None
    assert continued_session.completed_steps == ["step_1", "step_2", "step_3", "step_4"]
    assert continued_session.failed_step is None

    final_session = reloaded_runtime.complete_session(session_id)
    assert final_session.status == OPERATOR_SESSION_COMPLETED

    replay_refs = reloaded_replay.operator_replay_evidence_refs(session_id)
    flattened_evidence = [
        evidence_ref
        for checkpoint_ref in replay_refs
        for evidence_ref in checkpoint_ref["evidence_refs"]
    ]

    assert "evidence:step_1:success" in flattened_evidence
    assert "evidence:step_2:success" in flattened_evidence
    assert "evidence:step_3:failed" in flattened_evidence
    assert "evidence:step_3:success" in flattened_evidence
    assert "evidence:step_4:success" in flattened_evidence

    final_export = reloaded_runtime.export_state()
    imported_runtime = PersistentOperatorRuntime()
    imported_runtime.import_state(final_export)
    imported_session = imported_runtime.get_session(session_id)
    assert imported_session is not None
    assert imported_session.status == OPERATOR_SESSION_COMPLETED
    assert imported_session.completed_steps == ["step_1", "step_2", "step_3", "step_4"]
