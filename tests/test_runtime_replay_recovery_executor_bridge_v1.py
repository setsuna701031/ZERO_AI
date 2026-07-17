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


def test_executor_bridge_executes_recoverable_chain():
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()

    decision = replay_bridge.evaluate_replay(
        _replay(replay_id="replay-ok")
    )

    plan = plan_builder.build_plan(decision)

    result = executor_bridge.execute_plan(plan)

    payload = result.to_dict()

    assert payload["status"] == "completed"
    assert payload["recovery_chain_status"] == "verified"
    assert payload["continuation_decision"]


def test_executor_bridge_executes_review_required_chain():
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()

    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    decision = replay_bridge.evaluate_replay(
        _replay(
            replay_id="replay-fail",
            integrity_records=[integrity],
        )
    )

    plan = plan_builder.build_plan(decision)

    result = executor_bridge.execute_plan(plan)

    payload = result.to_dict()

    assert payload["status"] in {
        "completed",
        "blocked",
        "failed",
    }

    assert payload["recovery_chain_status"] == "review_required"
    assert payload["action_results"]


def test_executor_bridge_builds_recovery_chain():
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()

    decision = replay_bridge.evaluate_replay(
        _replay(
            replay_id="replay-continuity",
            continuity_verified=False,
            review_required=True,
            continuity_break="missing_parent_lineage",
        )
    )

    plan = plan_builder.build_plan(decision)

    chain = executor_bridge._build_recovery_chain(
        plan=plan,
    )

    assert chain["recovery_id"] == "recovery::replay-continuity"
    assert chain["recovery_plan"]["plan_id"]
    assert chain["verification_result"]["incident_required"] is True
    assert chain["status"] == "review_required"