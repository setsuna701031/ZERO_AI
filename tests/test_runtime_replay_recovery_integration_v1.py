from core.runtime.runtime_incident import RuntimeIncidentLayer
from core.runtime.runtime_replay_recovery import (
    REPLAY_RECOVERY_STATUS_BLOCKED,
    REPLAY_RECOVERY_STATUS_CONTINUABLE,
    REPLAY_RECOVERY_STATUS_FAILED,
    reconstruct_runtime_failure_from_replay,
)


def test_replay_recovery_reconstructs_and_verifies_runtime_failure():
    result = reconstruct_runtime_failure_from_replay(
        recovery_id="recovery-1",
        source_session_id="session-1",
        failure={
            "failure_type": "tool_failure",
            "failure_message": "tool crashed",
        },
        replay_reference={
            "replay_id": "replay-1",
        },
        replay_events=[
            {
                "event_type": "step_started",
            },
            {
                "event_type": "step_failed",
            },
        ],
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == REPLAY_RECOVERY_STATUS_CONTINUABLE
    assert payload["verification"]["consistent"] is True
    assert payload["continuation_decision"]["next_action"] == "resume_runtime"


def test_replay_recovery_blocks_rollback_required_failures():
    result = reconstruct_runtime_failure_from_replay(
        recovery_id="recovery-rollback",
        source_session_id="session-rollback",
        failure={
            "failure_type": "mutation_failure",
            "rollback_required": True,
        },
        replay_reference={
            "replay_id": "replay-rollback",
        },
        replay_events=[
            {
                "event_type": "mutation_started",
            },
            {
                "event_type": "mutation_failed",
            },
        ],
    )

    payload = result.to_dict()

    assert payload["status"] == REPLAY_RECOVERY_STATUS_BLOCKED
    assert payload["continuation_decision"]["next_action"] == "wait_for_recovery_approval"


def test_replay_recovery_detects_missing_replay_data():
    result = reconstruct_runtime_failure_from_replay(
        recovery_id="recovery-missing",
        source_session_id="session-missing",
        failure={
            "failure_type": "runtime_failure",
        },
        replay_reference={},
        replay_events=[],
    )

    payload = result.to_dict()

    assert payload["status"] == REPLAY_RECOVERY_STATUS_FAILED
    assert payload["verification"]["consistent"] is False
    assert payload["continuation_decision"]["next_action"] == "inspect_replay_reconstruction"


def test_replay_recovery_integrates_incident_layer():
    incident_layer = RuntimeIncidentLayer()

    result = reconstruct_runtime_failure_from_replay(
        recovery_id="recovery-incident",
        source_session_id="session-incident",
        failure={
            "failure_type": "tool_failure",
        },
        replay_reference={
            "replay_id": "replay-incident",
        },
        replay_events=[
            {
                "incident_id": "incident-1",
                "event_type": "failure",
            },
            {
                "incident_id": "incident-1",
                "event_type": "recovery",
            },
        ],
        incident_layer=incident_layer,
    )

    payload = result.to_dict()

    reconstructed = payload["reconstructed_incident"]

    assert reconstructed["incident_summary"]["has_failure"] is True
    assert reconstructed["incident_summary"]["has_recovery"] is True


def test_replay_recovery_preserves_replay_event_timeline():
    events = [
        {
            "sequence": 1,
            "event_type": "step_started",
        },
        {
            "sequence": 2,
            "event_type": "step_failed",
        },
    ]

    result = reconstruct_runtime_failure_from_replay(
        recovery_id="recovery-events",
        source_session_id="session-events",
        failure={
            "failure_type": "runtime_failure",
        },
        replay_reference={
            "replay_id": "replay-events",
        },
        replay_events=events,
    )

    payload = result.to_dict()

    assert payload["reconstructed_incident"]["timeline"][0]["sequence"] == 1
    assert payload["reconstructed_incident"]["timeline"][1]["sequence"] == 2
