
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def bridge_request(*, terminal: bool = False) -> dict[str, Any]:
    return {
        "controlled_mutation_bridge": True,
        "mutation_bridge_state": "bridge_blocked_terminal" if terminal else "bridge_ready_for_review",
        "mutation_bridge_reason": "test bridge",
        "mutation_bridge_eligible": not terminal,
        "mutation_bridge_requires_review": True,
        "mutation_bridge_blocked": terminal,
        "mutation_bridge_lineage": {
            "continuation_cycle_id": "cycle-verified",
            "continuation_parent": "cycle-parent",
            "replay_continuity_summary": {"replay_id": "replay-verified"},
            "recovery_continuity_summary": {"recovery_id": "recovery-verified"},
        },
        "mutation_bridge_enforcement_snapshot": {
            "schema": "runtime_enforcement_decision.v1",
            "classification": "block_recommended" if terminal else "review_required",
            "safe_to_enforce": terminal,
            "reason": "terminal" if terminal else "review",
        },
        "mutation_bridge_replay_snapshot": {"replay_id": "replay-verified"},
        "mutation_bridge_recovery_snapshot": {"recovery_id": "recovery-verified"},
        "controlled_mutation_bridge_summary": {
            "state": "bridge_blocked_terminal" if terminal else "bridge_ready_for_review",
            "eligible": not terminal,
            "requires_review": True,
        },
        "bridge_legality": "blocked" if terminal else "review_required",
        "bridge_requires_review": True,
        "bridge_terminality": "terminal" if terminal else "non_terminal",
        "bridge_verification_required": not terminal,
        "bridge_rollback_required": not terminal,
    }


def transaction() -> dict[str, Any]:
    return {
        "transaction_id": "tx-verified",
        "task_id": "task-verified",
        "proposal_id": "proposal-verified",
        "state": "committed",
    }


@dataclass
class FakeRuntimeResult:
    ok: bool = True
    verification_passed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def successful_result() -> FakeRuntimeResult:
    return FakeRuntimeResult(
        ok=True,
        verification_passed=True,
        metadata={
            "verification_passed": True,
            "verification": {"status": "passed"},
            "rollback_snapshot": {"snapshot_id": "rollback-verified"},
        },
    )


def test_successful_governed_repair_transaction_builds_verified_continuation() -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        build_verified_mutation_continuation_summary,
    )

    summary = build_verified_mutation_continuation_summary(
        successful_result(),
        bridge_request=bridge_request(),
        transaction=transaction(),
    )

    assert summary["verified_mutation_continuation"] is True
    assert summary["verified_mutation_state"] == "constitutional_reentry_allowed"
    assert summary["constitutional_reentry_allowed"] is True
    assert summary["verified_mutation_verification_passed"] is True
    assert summary["verified_mutation_replay_safe"] is True
    assert summary["verified_mutation_rollback_safe"] is True
    assert summary["reentry_legality"] == "allowed"


def test_verified_continuation_metadata_attaches_to_result_object() -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        attach_verified_mutation_continuation_metadata,
    )

    result = successful_result()
    returned = attach_verified_mutation_continuation_metadata(
        result,
        bridge_request=bridge_request(),
        transaction=transaction(),
    )

    assert returned is result
    assert result.metadata["verified_mutation_continuation"] is True
    assert result.metadata["constitutional_reentry_allowed"] is True
    assert result.metadata["verified_mutation_runtime_summary"]["reentry_replay_safe"] is True
