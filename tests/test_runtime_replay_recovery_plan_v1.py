from core.runtime.runtime_replay_engine import (
    RuntimeReplayIntegrityRecord,
    RuntimeReplaySession,
)
from core.runtime.runtime_replay_recovery_bridge import (
    RuntimeReplayRecoveryBridge,
)
from core.runtime.runtime_replay_recovery_plan import (
    RECOVERY_PLAN_STATUS_NOT_REQUIRED,
    RECOVERY_PLAN_STATUS_READY,
    RuntimeReplayRecoveryPlanBuilder,
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


def test_recovery_plan_not_required_for_recoverable_replay():
    bridge = RuntimeReplayRecoveryBridge()
    builder = RuntimeReplayRecoveryPlanBuilder()

    decision = bridge.evaluate_replay(
        _replay(replay_id="replay-ok")
    )

    plan = builder.build_plan(decision)
    payload = plan.to_dict()

    assert payload["status"] == RECOVERY_PLAN_STATUS_NOT_REQUIRED
    assert payload["recoverable"] is True
    assert payload["steps"] == []


def test_recovery_plan_created_for_integrity_incident():
    bridge = RuntimeReplayRecoveryBridge()
    builder = RuntimeReplayRecoveryPlanBuilder()

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
            replay_id="replay-integrity-fail",
            integrity_records=[integrity],
        )
    )

    plan = builder.build_plan(decision)
    payload = plan.to_dict()

    assert payload["status"] == RECOVERY_PLAN_STATUS_READY
    assert payload["recoverable"] is False
    assert payload["incident_required"] is True
    assert payload["repair_candidate"] is True
    assert len(payload["steps"]) == 3
    assert payload["steps"][0]["step_type"] == "collect_runtime_incident"
    assert payload["steps"][1]["step_type"] == "prepare_runtime_repair_candidate"
    assert payload["steps"][2]["step_type"] == "require_runtime_recovery_review"


def test_recovery_plan_created_for_deterministic_continuity_break():
    bridge = RuntimeReplayRecoveryBridge()
    builder = RuntimeReplayRecoveryPlanBuilder()

    decision = bridge.evaluate_replay(
        _replay(
            replay_id="replay-continuity-break",
            continuity_verified=False,
            review_required=True,
            continuity_break="missing_parent_lineage",
        )
    )

    plan = builder.build_plan(decision)
    payload = plan.to_dict()

    assert payload["status"] == RECOVERY_PLAN_STATUS_READY
    assert payload["reason"] == "deterministic_replay_failed"
    assert payload["steps"][0]["payload"]["incident_payload"]["reason"] == "deterministic_replay_failed"