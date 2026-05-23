from core.runtime.runtime_replay_engine import (
    RuntimeReplayIntegrityRecord,
    RuntimeReplaySession,
)
from core.runtime.runtime_replay_recovery_bridge import (
    RECOVERY_STATUS_INCIDENT,
    RECOVERY_STATUS_RECOVERABLE,
    RuntimeReplayRecoveryBridge,
)


def _replay(
    *,
    replay_id="replay-1",
    verified=True,
    continuity_verified=True,
    block_recommended=False,
    review_required=False,
    continuity_break="",
    integrity_records=None,
):
    return RuntimeReplaySession(
        replay_id=replay_id,
        source_session_id="session-1",
        replay_group=None,
        records=[],
        sequence=1,
        payload={},
        metadata={},
        verified=verified,
        integrity_records=list(integrity_records or []),
        canonical_status="replayed",
        review_required=review_required,
        block_recommended=block_recommended,
        continuity_verified=continuity_verified,
        continuity_break=continuity_break,
    )


def test_replay_recovery_bridge_accepts_verified_replay():
    bridge = RuntimeReplayRecoveryBridge()

    decision = bridge.evaluate_replay(
        _replay(replay_id="replay-ok")
    )

    payload = decision.to_dict()

    assert payload["recoverable"] is True
    assert payload["recovery_status"] == RECOVERY_STATUS_RECOVERABLE
    assert payload["incident_required"] is False
    assert payload["repair_candidate"] is False


def test_replay_recovery_bridge_creates_incident_for_integrity_failure():
    bridge = RuntimeReplayRecoveryBridge()

    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    decision = bridge.evaluate_replay(
        _replay(
            replay_id="replay-fail",
            integrity_records=[integrity],
        )
    )

    payload = decision.to_dict()

    assert payload["recoverable"] is False
    assert payload["recovery_status"] == RECOVERY_STATUS_INCIDENT
    assert payload["incident_required"] is True
    assert payload["repair_candidate"] is True
    assert payload["incident_payload"]["reason"] == "integrity_verification_failed"


def test_replay_recovery_bridge_detects_continuity_break():
    bridge = RuntimeReplayRecoveryBridge()

    decision = bridge.evaluate_replay(
        _replay(
            replay_id="replay-review",
            continuity_verified=False,
            review_required=True,
            continuity_break="missing_parent_lineage",
        )
    )

    payload = decision.to_dict()

    assert payload["recoverable"] is False
    assert payload["recovery_status"] == RECOVERY_STATUS_INCIDENT
    assert payload["incident_required"] is True
    assert payload["repair_candidate"] is True
    assert payload["incident_payload"]["reason"] == "deterministic_replay_failed"