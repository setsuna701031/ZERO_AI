from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalStatus,
    enforce_approval_result,
    evaluate_approval,
    read_approval_result,
    write_approval_result,
)
from core.runtime.mutation_patch_apply import (
    create_patch_plan,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.mutation_verification import (
    MutationVerificationCheck,
    verify_patch_plan,
)


def _session(
    approval_mode: MutationApprovalMode,
):
    return create_mutation_session(
        intent="Approval governance",
        initiator="test",
        reason="Verify approval chain",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=approval_mode,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
    )


def _verification(session):
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    return verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            )
        ],
    )


def test_auto_approval_mode_auto_approves() -> None:
    session = _session(
        MutationApprovalMode.AUTO
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    assert result.status == (
        MutationApprovalStatus.APPROVED
    )


def test_blocked_mode_blocks() -> None:
    session = _session(
        MutationApprovalMode.BLOCKED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    assert result.status == (
        MutationApprovalStatus.BLOCKED
    )


def test_review_required_pending_without_decision() -> None:
    session = _session(
        MutationApprovalMode.REVIEW_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    assert result.status == (
        MutationApprovalStatus.PENDING
    )


def test_review_required_approves_when_review_passes() -> None:
    session = _session(
        MutationApprovalMode.REVIEW_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
        decisions=[
            MutationApprovalDecision(
                actor="reviewer:runtime",
                decision=MutationApprovalStatus.APPROVED,
            )
        ],
    )

    assert result.status == (
        MutationApprovalStatus.APPROVED
    )


def test_review_required_rejects_when_reviewer_rejects() -> None:
    session = _session(
        MutationApprovalMode.REVIEW_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
        decisions=[
            MutationApprovalDecision(
                actor="reviewer:runtime",
                decision=MutationApprovalStatus.REJECTED,
            )
        ],
    )

    assert result.status == (
        MutationApprovalStatus.REJECTED
    )


def test_human_required_needs_human_actor() -> None:
    session = _session(
        MutationApprovalMode.HUMAN_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
        decisions=[
            MutationApprovalDecision(
                actor="reviewer:runtime",
                decision=MutationApprovalStatus.APPROVED,
            )
        ],
    )

    assert result.status == (
        MutationApprovalStatus.PENDING
    )


def test_human_required_accepts_human_approval() -> None:
    session = _session(
        MutationApprovalMode.HUMAN_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
        decisions=[
            MutationApprovalDecision(
                actor="human:setsuna",
                decision=MutationApprovalStatus.APPROVED,
            )
        ],
    )

    assert result.status == (
        MutationApprovalStatus.APPROVED
    )


def test_verification_failure_blocks_approval() -> None:
    session = _session(
        MutationApprovalMode.AUTO
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    verification = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=False,
            )
        ],
    )

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    assert result.status == (
        MutationApprovalStatus.BLOCKED
    )


def test_enforce_approval_result_blocks_non_approved() -> None:
    session = _session(
        MutationApprovalMode.REVIEW_REQUIRED
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    with pytest.raises(ValueError):
        enforce_approval_result(result)


def test_write_and_read_approval_result(
    tmp_path: Path,
) -> None:
    session = _session(
        MutationApprovalMode.AUTO
    )

    verification = _verification(session)

    result = evaluate_approval(
        session=session,
        verification=verification,
    )

    path = write_approval_result(
        result,
        tmp_path,
    )

    loaded = read_approval_result(path)

    assert loaded.session_id == result.session_id
    assert loaded.status == result.status