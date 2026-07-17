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
from core.runtime.runtime_constitution_v1 import (
    CONSTITUTION_ILLEGAL,
    CONSTITUTION_LEGAL,
    CONSTITUTION_REVIEW_REQUIRED,
    RuntimeConstitutionV1,
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


def _build_ledger_entry(replay):
    replay_bridge = RuntimeReplayRecoveryBridge()
    plan_builder = RuntimeReplayRecoveryPlanBuilder()
    executor_bridge = RuntimeReplayRecoveryExecutorBridge()
    seal_builder = RuntimeReplayRecoverySealBuilder()
    closure_builder = RuntimeGovernanceClosureBuilder()
    snapshot_builder = RuntimeGovernanceSnapshotBuilder()
    ledger = RuntimeGovernanceLedger()

    decision = replay_bridge.evaluate_replay(replay)
    plan = plan_builder.build_plan(decision)
    execution_result = executor_bridge.execute_plan(plan)
    seal = seal_builder.build_seal(execution_result)
    closure = closure_builder.build_closure(seal)
    snapshot = snapshot_builder.build_snapshot(
        closure,
        seal=seal,
    )

    return ledger.append_snapshot(snapshot)


def test_runtime_constitution_marks_legal_ready_runtime():
    constitution = RuntimeConstitutionV1()

    entry = _build_ledger_entry(
        _replay(replay_id="replay-legal")
    )

    decision = constitution.evaluate_ledger_entry(entry)
    payload = decision.to_dict()

    assert payload["legality"] == CONSTITUTION_LEGAL
    assert payload["legal"] is True
    assert payload["continuation_allowed"] is True
    assert payload["violations"] == []


def test_runtime_constitution_marks_review_required_runtime():
    constitution = RuntimeConstitutionV1()

    integrity = RuntimeReplayIntegrityRecord(
        original_execution_id="exec-a",
        replay_execution_id="exec-b",
        original_result_hash="hash-a",
        replay_result_hash="hash-b",
        integrity_verified=False,
        mismatch_reason="result_hash_mismatch",
    )

    entry = _build_ledger_entry(
        _replay(
            replay_id="replay-review",
            integrity_records=[integrity],
        )
    )

    decision = constitution.evaluate_ledger_entry(entry)
    payload = decision.to_dict()

    assert payload["legality"] == CONSTITUTION_REVIEW_REQUIRED
    assert payload["legal"] is False
    assert payload["review_required"] is True
    assert payload["continuation_allowed"] is False


def test_runtime_constitution_detects_blocked_runtime_reopen():
    constitution = RuntimeConstitutionV1()

    decision = constitution.evaluate_ledger_entry(
        {
            "entry_id": "ledger::bad",
            "replay_id": "replay-bad",
            "closure_id": "closure::bad",
            "snapshot_id": "snapshot::bad",
            "sequence": 1,
            "previous_entry_hash": "genesis",
            "entry_hash": "bad",
            "timestamp": "now",
            "immutable": True,
            "classification": "governance_failed",
            "closure_status": "runtime_blocked",
            "continuation_allowed": True,
            "evidence_bundle": {
                "closure_snapshot": {
                    "blocked": True,
                    "reopen_protection": True,
                },
                "seal_snapshot": {
                    "seal_status": "sealed_failed",
                    "failed": True,
                },
            },
        }
    )

    payload = decision.to_dict()

    assert payload["legality"] == CONSTITUTION_ILLEGAL
    assert payload["illegal"] is True
    assert "blocked_runtime_continuation_allowed" in payload["violations"]
    assert "failed_seal_continuation_allowed" in payload["violations"]


def test_runtime_constitution_verifies_ledger_chain():
    constitution = RuntimeConstitutionV1()
    ledger = RuntimeGovernanceLedger()

    ledger.append_snapshot(
        _build_ledger_entry(
            _replay(replay_id="replay-chain-a")
        ).evidence_bundle["closure_snapshot"]
    )

    result = constitution.evaluate_ledger_chain(ledger)

    assert result["legality"] == CONSTITUTION_LEGAL
    assert result["legal"] is True
    assert result["integrity"]["verified"] is True