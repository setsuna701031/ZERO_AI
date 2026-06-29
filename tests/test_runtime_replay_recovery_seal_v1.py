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
    REPLAY_RECOVERY_SEAL_RECOVERABLE,
    REPLAY_RECOVERY_SEAL_REVIEW_REQUIRED,
    RuntimeReplayRecoverySealBuilder,
)
import pytest

pytestmark = [pytest.mark.contract]



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


def test_replay_recovery_seal_marks_recoverable_execution():
    bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()

    decision = bridge.evaluate_replay(
        _replay(replay_id="replay-ok")
    )
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)

    seal = seal_builder.build_seal(execution_result)
    payload = seal.to_dict()

    assert payload["seal_status"] == REPLAY_RECOVERY_SEAL_RECOVERABLE
    assert payload["recoverable"] is True
    assert payload["review_required"] is False
    assert payload["failed"] is False
    assert payload["replay_id"] == "replay-ok"


def test_replay_recovery_seal_marks_review_required_execution():
    bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()

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
            replay_id="replay-review",
            integrity_records=[integrity],
        )
    )
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)

    seal = seal_builder.build_seal(execution_result)
    payload = seal.to_dict()

    assert payload["seal_status"] == REPLAY_RECOVERY_SEAL_REVIEW_REQUIRED
    assert payload["recoverable"] is False
    assert payload["review_required"] is True
    assert payload["failed"] is False
    assert payload["replay_id"] == "replay-review"


def test_replay_recovery_seal_accepts_dict_payload():
    seal_builder = RuntimeReplayRecoverySealBuilder()

    seal = seal_builder.build_seal(
        {
            "execution_id": "exec-1",
            "recovery_id": "recovery::replay-dict",
            "source_session_id": "replay-dict",
            "status": "completed",
            "recovery_chain_status": "verified",
            "continuation_decision": "ready_for_continuation",
            "action_results": [],
        }
    )

    payload = seal.to_dict()

    assert payload["seal_status"] == REPLAY_RECOVERY_SEAL_RECOVERABLE
    assert payload["replay_id"] == "replay-dict"