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
    RuntimeGovernanceClosureBuilder,
)
from core.runtime.runtime_governance_snapshot_v1 import (
    RuntimeGovernanceSnapshotBuilder,
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


def _build_runtime_chain(replay):
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()
    closure_builder = RuntimeGovernanceClosureBuilder()

    decision = replay_bridge.evaluate_replay(replay)
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)
    seal = seal_builder.build_seal(execution_result)
    closure = closure_builder.build_closure(seal)

    return {
        "decision": decision,
        "plan": plan,
        "execution_result": execution_result,
        "seal": seal,
        "closure": closure,
    }


def test_governance_snapshot_builds_ready_runtime_evidence_bundle():
    chain = _build_runtime_chain(
        _replay(replay_id="replay-ok")
    )

    snapshot_builder = RuntimeGovernanceSnapshotBuilder()

    snapshot = snapshot_builder.build_snapshot(
        chain["closure"],
        seal=chain["seal"],
        replay_evidence={
            "deterministic_replay": True,
            "test_scope": "governance_snapshot_v1",
        },
        metadata={
            "stage": "v1",
        },
    )

    payload = snapshot.to_dict()

    assert payload["snapshot_type"] == "runtime_governance_snapshot"
    assert payload["replay_id"] == "replay-ok"
    assert payload["continuation_allowed"] is True
    assert payload["blocked"] is False
    assert payload["classification"] == "governance_ready"
    assert payload["evidence_bundle"]["lineage"]["replay_id"] == "replay-ok"
    assert payload["evidence_bundle"]["lineage"]["seal_id"]
    assert payload["evidence_bundle"]["replay_evidence"]["deterministic_replay"] is True
    assert payload["evidence_bundle"]["metadata"]["stage"] == "v1"


def test_governance_snapshot_builds_review_required_evidence_bundle():
    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    chain = _build_runtime_chain(
        _replay(
            replay_id="replay-review",
            integrity_records=[integrity],
        )
    )

    snapshot_builder = RuntimeGovernanceSnapshotBuilder()

    snapshot = snapshot_builder.build_snapshot(
        chain["closure"],
        seal=chain["seal"],
        replay_evidence={
            "integrity_verified": False,
            "mismatch_reason": "result_hash_mismatch",
        },
    )

    payload = snapshot.to_dict()

    assert payload["replay_id"] == "replay-review"
    assert payload["continuation_allowed"] is False
    assert payload["review_required"] is True
    assert payload["classification"] == "governance_review_required"
    assert payload["evidence_bundle"]["seal_snapshot"]["seal_status"] == "sealed_review_required"
    assert payload["evidence_bundle"]["replay_evidence"]["integrity_verified"] is False


def test_governance_snapshot_accepts_dict_closure_payload():
    snapshot_builder = RuntimeGovernanceSnapshotBuilder()

    snapshot = snapshot_builder.build_snapshot(
        {
            "closure_id": "closure::dict-replay",
            "replay_id": "dict-replay",
            "closure_status": "runtime_blocked",
            "classification": "governance_failed",
            "continuation_allowed": False,
            "review_required": False,
            "blocked": True,
            "reopen_protection": True,
            "governance_evidence": {
                "failed": True,
            },
        },
        seal={
            "seal_id": "seal::dict-replay",
            "recovery_id": "recovery::dict-replay",
            "execution_id": "exec-dict",
            "seal_status": "sealed_failed",
        },
    )

    payload = snapshot.to_dict()

    assert payload["snapshot_id"] == "snapshot::dict-replay"
    assert payload["blocked"] is True
    assert payload["evidence_bundle"]["lineage"]["execution_id"] == "exec-dict"
    assert payload["evidence_bundle"]["governance_evidence"]["failed"] is True