from core.runtime.runtime_replay_engine import (
    RuntimeReplayIntegrityRecord,
    RuntimeReplaySession,
)
from core.runtime.runtime_replay_recovery_bridge import (
    RuntimeReplayRecoveryBridge,
)
from core.runtime.runtime_replay_recovery_executor_bridge import (
    RuntimeReplayRecoveryExecutorBridge,
)
from core.runtime.runtime_replay_recovery_plan import (
    RuntimeReplayRecoveryPlanBuilder,
)
from core.runtime.runtime_replay_recovery_seal import (
    RuntimeReplayRecoverySealBuilder,
)
from core.runtime.runtime_governance_closure_v1 import (
    GOVERNANCE_CLOSURE_BLOCKED,
    GOVERNANCE_CLOSURE_READY,
    GOVERNANCE_CLOSURE_REVIEW_REQUIRED,
    RuntimeGovernanceClosureBuilder,
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


def _build_closure(replay):
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()
    closure_builder = RuntimeGovernanceClosureBuilder()

    decision = replay_bridge.evaluate_replay(replay)
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)
    seal = seal_builder.build_seal(execution_result)

    return closure_builder.build_closure(seal)


def test_governance_closure_marks_runtime_ready():
    closure = _build_closure(
        _replay(replay_id="replay-ok")
    )

    payload = closure.to_dict()

    assert payload["closure_status"] == GOVERNANCE_CLOSURE_READY
    assert payload["continuation_allowed"] is True
    assert payload["blocked"] is False
    assert payload["classification"] == "governance_ready"


def test_governance_closure_marks_review_required():
    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    closure = _build_closure(
        _replay(
            replay_id="replay-review",
            integrity_records=[integrity],
        )
    )

    payload = closure.to_dict()

    assert (
        payload["closure_status"]
        == GOVERNANCE_CLOSURE_REVIEW_REQUIRED
    )
    assert payload["continuation_allowed"] is False
    assert payload["review_required"] is True
    assert payload["blocked"] is False


def test_governance_closure_marks_failed_runtime():
    closure_builder = RuntimeGovernanceClosureBuilder()

    closure = closure_builder.build_closure(
        {
            "replay_id": "replay-failed",
            "seal_status": "sealed_failed",
            "recoverable": False,
            "review_required": False,
            "failed": True,
        }
    )

    payload = closure.to_dict()

    assert payload["closure_status"] == GOVERNANCE_CLOSURE_BLOCKED
    assert payload["continuation_allowed"] is False
    assert payload["blocked"] is True
    assert payload["classification"] == "governance_failed"