
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


def test_missing_rollback_snapshot_denies_reentry() -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        build_verified_mutation_continuation_summary,
    )

    result = successful_result()
    result.metadata.pop("rollback_snapshot", None)

    summary = build_verified_mutation_continuation_summary(
        result,
        bridge_request=bridge_request(),
        transaction=transaction(),
    )

    assert summary["constitutional_reentry_allowed"] is False
    assert summary["verified_mutation_state"] == "constitutional_reentry_denied_missing_rollback_snapshot"
    assert summary["reentry_rollback_safe"] is False


def test_scheduler_and_agent_preserve_verified_mutation_reentry_metadata() -> None:
    import core.tasks.scheduler as scheduler_module
    import core.agent.agent_loop as agent_loop_module

    payload = {
        "verified_mutation_state": "constitutional_reentry_allowed",
        "constitutional_reentry_allowed": True,
        "verified_mutation_verification_passed": True,
        "verified_mutation_replay_safe": True,
        "verified_mutation_rollback_safe": True,
        "verified_mutation_runtime_summary": {
            "reentry_legality": "allowed",
            "reentry_requires_review": False,
            "reentry_terminality": "non_terminal",
            "reentry_verification_status": "passed",
            "reentry_replay_safe": True,
            "reentry_rollback_safe": True,
        },
    }

    scheduler_summary = scheduler_module._zero_v7336_verified_mutation_continuation_summary(payload)
    assert scheduler_summary["constitutional_reentry_allowed"] is True
    assert scheduler_summary["reentry_legality"] == "allowed"

    agent_summary = agent_loop_module._zero_v7336_agent_verified_mutation_summary(payload)
    assert agent_summary["constitutional_reentry_allowed"] is True
    assert agent_summary["reentry_terminality"] == "non_terminal"
