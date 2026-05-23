from core.runtime.runtime_replay_resume_loop import (
    RESUME_LOOP_STATUS_BLOCKED,
    RESUME_LOOP_STATUS_REPLAY_INVALID,
    RESUME_LOOP_STATUS_RESUMED,
    rebuild_runtime_loop_from_replay,
)


def test_replay_resume_loop_recovers_cursor_and_resumes():
    result = rebuild_runtime_loop_from_replay(
        recovery_id="recovery-1",
        source_session_id="session-1",
        runtime_state={
            "status": "failed",
            "current_step_index": 3,
        },
        failure={
            "failure_type": "tool_failure",
        },
        replay_reference={
            "replay_id": "replay-1",
        },
        replay_events=[
            {
                "event_type": "step_started",
                "step_index": 0,
            },
            {
                "event_type": "step_completed",
                "step_index": 0,
            },
            {
                "event_type": "step_started",
                "step_index": 1,
            },
            {
                "event_type": "step_failed",
                "step_index": 1,
            },
        ],
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == RESUME_LOOP_STATUS_RESUMED
    assert payload["resumed"] is True
    assert payload["resume_cursor"] == 1
    assert payload["replay_cursor_patch"]["current_step_index"] == 1
    assert payload["resumed_runtime_state"]["status"] == "running"


def test_replay_resume_loop_blocks_rollback_required_failure():
    result = rebuild_runtime_loop_from_replay(
        recovery_id="recovery-rollback",
        source_session_id="session-rollback",
        runtime_state={
            "status": "failed",
        },
        failure={
            "failure_type": "mutation_failure",
            "rollback_required": True,
        },
        replay_reference={
            "replay_id": "replay-rollback",
        },
        replay_events=[
            {
                "event_type": "mutation_failed",
                "step_index": 2,
            },
        ],
    )

    payload = result.to_dict()

    assert payload["status"] == RESUME_LOOP_STATUS_BLOCKED
    assert payload["resumed"] is False
    assert payload["resume_cursor"] == 2


def test_replay_resume_loop_detects_invalid_replay_reconstruction():
    result = rebuild_runtime_loop_from_replay(
        recovery_id="recovery-invalid",
        source_session_id="session-invalid",
        runtime_state={
            "status": "failed",
        },
        failure={
            "failure_type": "runtime_failure",
        },
        replay_reference={},
        replay_events=[],
    )

    payload = result.to_dict()

    assert payload["status"] == RESUME_LOOP_STATUS_REPLAY_INVALID
    assert payload["resumed"] is False


def test_replay_resume_loop_preserves_runtime_snapshot():
    state = {
        "status": "failed",
        "current_step_index": 5,
    }

    result = rebuild_runtime_loop_from_replay(
        recovery_id="recovery-state",
        source_session_id="session-state",
        runtime_state=state,
        failure={
            "failure_type": "tool_failure",
        },
        replay_reference={
            "replay_id": "replay-state",
        },
        replay_events=[
            {
                "event_type": "step_failed",
                "step_index": 3,
            },
        ],
    )

    assert result.resumed is True
    assert state["status"] == "failed"
    assert result.resumed_runtime_state["status"] == "running"


def test_replay_resume_loop_rebuilds_cursor_from_failure_event():
    result = rebuild_runtime_loop_from_replay(
        recovery_id="recovery-cursor",
        source_session_id="session-cursor",
        runtime_state={
            "status": "failed",
        },
        failure={
            "failure_type": "tool_failure",
        },
        replay_reference={
            "replay_id": "replay-cursor",
        },
        replay_events=[
            {
                "event_type": "step_started",
                "step_index": 0,
            },
            {
                "event_type": "step_completed",
                "step_index": 0,
            },
            {
                "event_type": "tool_failed",
                "step_index": 4,
            },
        ],
    )

    assert result.resume_cursor == 4
    assert result.replay_cursor_patch["current_step_index"] == 4
