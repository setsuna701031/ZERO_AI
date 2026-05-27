from __future__ import annotations

from core.runtime.autonomous_repair_loop import (
    AutonomousRepairState,
    assert_repair_loop_preserves_lineage,
    assert_repair_loop_terminal,
    apply_repair_action,
    decide_repair_commit_or_rollback,
    diagnose_runtime_failure,
    get_repair_loop,
    observe_runtime_failure,
    propose_repair_action,
    resume_after_repair,
    run_autonomous_repair_loop,
    stabilize_repair_loop,
    verify_repair_action,
)
from core.runtime.runtime_recovery_freeze import (
    create_recovery_attempt,
    handoff_terminal_failure_to_autonomous_repair,
    record_recovery_requires_human_review,
    record_recovery_terminal_failure,
)
from core.runtime.runtime_transaction_registry import create_transaction, get_transaction


def test_observe_creates_observed_state() -> None:
    loop = observe_runtime_failure(_failure())

    assert loop.final_state is AutonomousRepairState.OBSERVED
    assert loop.loop_id.startswith("repair_loop:")


def test_diagnose_creates_diagnosis() -> None:
    loop = diagnose_runtime_failure(observe_runtime_failure(_failure()), {"failure_class": "syntax_error"})

    assert loop.final_state is AutonomousRepairState.DIAGNOSED
    assert loop.diagnosis["failure_class"] == "syntax_error"


def test_propose_repair_creates_repair_proposed_state() -> None:
    loop = propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure())), {"strategy_id": "patch_syntax"})

    assert loop.final_state is AutonomousRepairState.REPAIR_PROPOSED
    assert loop.repair_strategy["strategy_id"] == "patch_syntax"


def test_apply_repair_requires_authority_and_transaction() -> None:
    loop = propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure())))
    blocked = apply_repair_action(loop, authority={})

    assert blocked.final_state is AutonomousRepairState.BLOCKED
    assert blocked.terminal is True

    applied = apply_repair_action(loop, authority=_authority())
    assert applied.final_state is AutonomousRepairState.REPAIR_APPLIED
    assert applied.transaction_refs


def test_verify_success_leads_commit_or_stabilized() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority(), verification={"ok": True, "verification_ok": True})

    assert loop.committed is True
    assert loop.stabilized is True
    assert loop.final_state is AutonomousRepairState.STABILIZED


def test_verify_failure_leads_rollback_or_failed_terminal() -> None:
    loop = observe_runtime_failure(_failure())
    loop = diagnose_runtime_failure(loop)
    loop = propose_repair_action(loop)
    loop = apply_repair_action(loop, authority=_authority())
    loop = verify_repair_action(loop, {"ok": False, "reason": "still_failing"})

    assert loop.final_state in {AutonomousRepairState.ROLLED_BACK, AutonomousRepairState.FAILED_TERMINAL}
    assert loop.rolled_back or loop.terminal


def test_requires_human_review_stops_loop() -> None:
    loop = run_autonomous_repair_loop(
        _failure(),
        authority=_authority(),
        diagnosis={"requires_human_review": True, "reason": "unsafe_repair"},
    )

    assert loop.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW
    assert loop.terminal is True


def test_blocked_recovery_does_not_continue_autonomous_repair() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:block-autonomous")
    attempt = record_recovery_requires_human_review(attempt, "unsafe_recovery")

    result = handoff_terminal_failure_to_autonomous_repair(attempt, authority=_authority())

    assert result["state"] == "requires_human_review"
    assert result["reason"] == "requires_human_review_stops_autonomous_repair"


def test_repair_loop_preserves_source_transaction() -> None:
    source = create_transaction(
        task_id="task-source-repair",
        step_id="step-source-repair",
        trace_id="trace-source-repair",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/source-repair.txt"],
    )
    before = source.to_dict()
    loop = run_autonomous_repair_loop(_failure(transaction_id=source.transaction_id), authority=_authority())

    assert get_transaction(source.transaction_id).to_dict() == before
    assert assert_repair_loop_preserves_lineage(loop) is True


def test_repair_loop_has_evidence_lineage() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority())

    assert loop.evidence_refs
    assert len(loop.evidence_refs) >= 5


def test_repair_loop_terminal_state_is_explicit() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority())

    assert assert_repair_loop_terminal(loop) is True


def test_repair_loop_result_is_queryable_stable() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority())
    queried = get_repair_loop(loop.loop_id)

    assert queried.loop_id == loop.loop_id
    assert queried.normalized_digest == loop.normalized_digest


def _failure(**overrides):
    return {
        "task_id": "task-autonomous",
        "step_id": "step-autonomous",
        "trace_id": "trace-autonomous",
        "failure_id": "failure-autonomous",
        "transaction_id": "runtime_tx:source-autonomous",
        "replay_run_id": "replay_run:source-autonomous",
        "recovery_attempt_id": "runtime_recovery:source-autonomous",
        **overrides,
    }


def _authority():
    return {
        "task_id": "task-autonomous",
        "step_id": "step-autonomous",
        "authority_source": "execution_gateway",
        "runtime_session": "session-autonomous",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": "trace-autonomous",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
