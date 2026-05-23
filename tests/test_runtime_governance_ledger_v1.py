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
from core.runtime.runtime_governance_ledger_v1 import (
    RuntimeGovernanceLedger,
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


def _build_snapshot(replay):
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()
    closure_builder = RuntimeGovernanceClosureBuilder()
    snapshot_builder = RuntimeGovernanceSnapshotBuilder()

    decision = replay_bridge.evaluate_replay(replay)
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)
    seal = seal_builder.build_seal(execution_result)
    closure = closure_builder.build_closure(seal)

    return snapshot_builder.build_snapshot(
        closure,
        seal=seal,
    )


def test_governance_ledger_appends_entries():
    ledger = RuntimeGovernanceLedger()

    snapshot_a = _build_snapshot(
        _replay(replay_id="replay-a")
    )

    snapshot_b = _build_snapshot(
        _replay(replay_id="replay-b")
    )

    entry_a = ledger.append_snapshot(snapshot_a)
    entry_b = ledger.append_snapshot(snapshot_b)

    assert entry_a.sequence == 1
    assert entry_b.sequence == 2
    assert entry_b.previous_entry_hash == entry_a.entry_hash
    assert entry_a.immutable is True


def test_governance_ledger_builds_audit_chain():
    ledger = RuntimeGovernanceLedger()

    ledger.append_snapshot(
        _build_snapshot(
            _replay(replay_id="replay-chain")
        )
    )

    chain = ledger.build_audit_chain()

    assert chain["chain_type"] == "runtime_governance_ledger"
    assert chain["entry_count"] == 1
    assert chain["immutable"] is True
    assert chain["latest_entry_hash"]


def test_governance_ledger_verifies_integrity():
    ledger = RuntimeGovernanceLedger()

    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    snapshot = _build_snapshot(
        _replay(
            replay_id="replay-review",
            integrity_records=[integrity],
        )
    )

    ledger.append_snapshot(snapshot)

    verification = ledger.verify_chain_integrity()

    assert verification["verified"] is True
    assert verification["reason"] == "ledger_chain_verified"
    assert verification["entry_count"] == 1


def test_governance_ledger_detects_tampering():
    ledger = RuntimeGovernanceLedger()

    snapshot = _build_snapshot(
        _replay(replay_id="replay-tamper")
    )

    ledger.append_snapshot(snapshot)

    ledger._entries[0] = ledger._entries[0].__class__(
        entry_id=ledger._entries[0].entry_id,
        replay_id=ledger._entries[0].replay_id,
        closure_id=ledger._entries[0].closure_id,
        snapshot_id=ledger._entries[0].snapshot_id,
        sequence=ledger._entries[0].sequence,
        previous_entry_hash=ledger._entries[0].previous_entry_hash,
        entry_hash="tampered",
        timestamp=ledger._entries[0].timestamp,
        immutable=ledger._entries[0].immutable,
        classification=ledger._entries[0].classification,
        closure_status=ledger._entries[0].closure_status,
        continuation_allowed=ledger._entries[0].continuation_allowed,
        evidence_bundle=ledger._entries[0].evidence_bundle,
    )

    verification = ledger.verify_chain_integrity()

    assert verification["verified"] is False
    assert verification["reason"] == "entry_hash_mismatch"