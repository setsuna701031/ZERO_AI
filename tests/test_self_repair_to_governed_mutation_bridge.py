from __future__ import annotations

from pathlib import Path

from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)


def _bridge_request() -> dict:
    return {
        "controlled_mutation_bridge": True,
        "mutation_bridge_state": "bridge_ready_for_review",
        "mutation_bridge_reason": "review governed self-repair candidate",
        "mutation_bridge_eligible": True,
        "mutation_bridge_requires_review": True,
        "mutation_bridge_blocked": False,
        "mutation_bridge_lineage": {
            "continuation_cycle_id": "cycle-request",
            "continuation_parent": "cycle-parent",
            "replay_continuity_summary": {"replay_id": "replay-request"},
            "recovery_continuity_summary": {"recovery_id": "recovery-request"},
        },
        "mutation_bridge_enforcement_snapshot": {
            "schema": "runtime_enforcement_decision.v1",
            "classification": "review_required",
            "safe_to_enforce": False,
            "reason": "missing evidence",
        },
        "mutation_bridge_replay_snapshot": {"replay_id": "replay-request"},
        "mutation_bridge_recovery_snapshot": {"recovery_id": "recovery-request"},
        "controlled_mutation_bridge_summary": {
            "state": "bridge_ready_for_review",
            "eligible": True,
            "requires_review": True,
        },
        "bridge_legality": "review_required",
        "bridge_requires_review": True,
        "bridge_terminality": "non_terminal",
        "bridge_verification_required": True,
        "bridge_rollback_required": True,
    }


def _transaction() -> dict:
    return {
        "transaction_id": "runtime_tx_bridge_001",
        "task_id": "task_bridge",
        "proposal_id": "proposal_bridge",
        "state": "committed",
        "committed_mutations": [
            {
                "mutation_id": "mutation_bridge_001",
                "action": "write_file",
                "target_path": "project/bridge.py",
                "raw_mutation": {
                    "op_type": "write_file",
                    "target_path": "project/bridge.py",
                    "content": "print('controlled bridge')\n",
                },
            }
        ],
    }


def test_repair_bridge_accepts_explicit_eligible_controlled_bridge_request() -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        build_controlled_mutation_bridge_request,
    )

    request = build_controlled_mutation_bridge_request(_bridge_request())

    assert request["mutation_bridge_eligible"] is True
    assert request["bridge_requires_review"] is True
    assert request["bridge_verification_required"] is True
    assert request["bridge_rollback_required"] is True
    assert request["bridge_approval_mode"] == "review_required"


def test_terminal_bridge_request_is_rejected() -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        build_controlled_mutation_bridge_request,
    )

    request = _bridge_request()
    request["mutation_bridge_eligible"] = False
    request["mutation_bridge_state"] = "bridge_blocked_terminal"
    request["mutation_bridge_blocked"] = True
    request["bridge_terminality"] = "terminal"

    try:
        build_controlled_mutation_bridge_request(request)
    except ValueError as exc:
        assert "not_eligible" in str(exc) or "terminal" in str(exc)
        return

    raise AssertionError("expected terminal controlled bridge rejection")


def test_repair_bridge_preserves_approval_verification_rollback_metadata(tmp_path: Path) -> None:
    from core.runtime.repair_transaction_execution_bridge import (
        _with_controlled_mutation_bridge_metadata,
        build_controlled_mutation_bridge_request,
        build_executable_repair_transaction,
    )

    request = build_controlled_mutation_bridge_request(_bridge_request())
    executable = _with_controlled_mutation_bridge_metadata(
        build_executable_repair_transaction(_transaction()),
        request,
    )

    metadata = executable["metadata"]
    bridge = metadata["controlled_mutation_bridge"]

    assert request["bridge_approval_mode"] == MutationApprovalMode.REVIEW_REQUIRED.value
    assert request["bridge_verification_mode"] == MutationVerificationRequirement.TARGETED_TESTS.value
    assert bridge["mutation_bridge_eligible"] is True
    assert bridge["bridge_requires_review"] is True
    assert bridge["bridge_verification_required"] is True
    assert bridge["bridge_rollback_required"] is True
    assert metadata["approval_required"] is True
    assert metadata["verification_required"] is True
    assert metadata["rollback_required"] is True
    assert metadata["audit_required"] is True


def test_agent_loop_does_not_auto_mutate_or_auto_approve_bridge_candidate() -> None:
    from core.agent.agent_loop import AgentLoop

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def run_task(self, **_kwargs):
            self.calls += 1
            return {
                "ok": True,
                "status": "running",
                "governed_self_repair": {
                    "governed_self_repair": True,
                    "self_repair_state": "repair_review_required",
                    "self_repair_candidate": True,
                    "self_repair_review_required": True,
                    "self_repair_terminal_block": False,
                    "self_repair_requires_review": True,
                    "self_repair_boundary": {
                        "enforcement_snapshot": _bridge_request()["mutation_bridge_enforcement_snapshot"],
                    },
                    "self_repair_lineage": _bridge_request()["mutation_bridge_lineage"],
                },
            }

    runner = Runner()
    loop = AgentLoop(task_runner=runner)
    normalized = loop._normalize_execution_result(runner.run_task())

    assert runner.calls == 1
    assert normalized["mutation_bridge_eligible"] is True
    assert normalized["requires_review"] is True
    assert normalized["next_action"] == "wait_for_external_event"
    assert normalized.get("auto_approved") is not True
    assert normalized.get("mutation_executed") is not True
