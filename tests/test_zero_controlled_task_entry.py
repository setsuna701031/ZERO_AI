from __future__ import annotations

from core.runtime.execution_gateway import safe_subprocess_run
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_replay_engine import RuntimeReplayEngine


def test_zero_controlled_task_entry_success_path() -> None:
    task = {
        "task_id": "zero_controlled_task_smoke_success",
        "intent": "run controlled gateway smoke command",
        "allow_paths": ["workspace"],
    }

    session_manager = RuntimeExecutionSessionManager()
    session = session_manager.create_session(
        session_id=task["task_id"],
        lifecycle_id="zero_controlled_task_lifecycle_success",
        payload=task,
        metadata={
            "entrypoint": "zero_controlled_task_entry",
            "controlled_task": True,
        },
    )
    session_manager.start_session(session_id=session.session_id)

    result = safe_subprocess_run(
        ["python", "-c", "print(123)"],
        timeout=10,
        allow_paths=task["allow_paths"],
        metadata={
            "task_id": task["task_id"],
            "controlled_task": True,
            "entrypoint": "zero_controlled_task_entry",
        },
    )

    assert result["ok"] is True
    assert result["metadata"].get("execution_outcome_finalized") is True
    assert result["metadata"].get("execution_outcome_verification_state") == "verified"
    assert result["metadata"].get("runtime_frozen") is False

    replay_engine = RuntimeReplayEngine(session_manager=session_manager)
    replay = replay_engine.replay_session(
        replay_id="zero_controlled_task_replay_success",
        source_session_id=session.session_id,
        metadata={
            "entrypoint": "zero_controlled_task_entry",
            "controlled_task": True,
        },
    )

    integrity = replay_engine.record_execution_result_integrity(
        original_execution_id="zero_controlled_task_original_success",
        replay_execution_id=replay.replay_id,
        original_result=result,
        replay_result=result,
    )
    updated = replay_engine.attach_integrity_record(replay.replay_id, integrity)

    assert integrity.integrity_verified is True
    assert updated.verified is True
    assert updated.canonical_status == "replayed"
    assert updated.review_required is True
    assert updated.block_recommended is False


def test_zero_controlled_task_entry_boundary_block_path() -> None:
    task = {
        "task_id": "zero_controlled_task_smoke_blocked",
        "intent": "prove controlled gateway blocks out-of-bound target",
        "allow_paths": ["workspace"],
    }

    session_manager = RuntimeExecutionSessionManager()
    session = session_manager.create_session(
        session_id=task["task_id"],
        lifecycle_id="zero_controlled_task_lifecycle_blocked",
        payload=task,
        metadata={
            "entrypoint": "zero_controlled_task_entry",
            "controlled_task": True,
        },
    )
    session_manager.start_session(session_id=session.session_id)

    result = safe_subprocess_run(
        ["python", "-c", "print(123)", "core/runtime/execution_gateway.py"],
        timeout=10,
        allow_paths=task["allow_paths"],
        metadata={
            "task_id": task["task_id"],
            "controlled_task": True,
            "entrypoint": "zero_controlled_task_entry",
        },
    )

    assert result["ok"] is False
    assert result["metadata"].get("execution_outcome_finalized") is True
    assert result["metadata"].get("execution_outcome_state") == "failed"
    assert result["metadata"].get("runtime_frozen") is True
    assert result["metadata"].get("blocked_reason") == "target_path_outside_allow_paths"

    replay_engine = RuntimeReplayEngine(session_manager=session_manager)
    replay = replay_engine.replay_session(
        replay_id="zero_controlled_task_replay_blocked",
        source_session_id=session.session_id,
        metadata={
            "entrypoint": "zero_controlled_task_entry",
            "controlled_task": True,
        },
    )

    integrity = replay_engine.record_execution_result_integrity(
        original_execution_id="zero_controlled_task_original_blocked",
        replay_execution_id=replay.replay_id,
        original_result=result,
        replay_result={
            **result,
            "ok": True,
        },
    )
    updated = replay_engine.attach_integrity_record(replay.replay_id, integrity)

    assert integrity.integrity_verified is False
    assert updated.verified is False
    assert updated.canonical_status == "failed"
    assert updated.review_required is True
    assert updated.block_recommended is True
