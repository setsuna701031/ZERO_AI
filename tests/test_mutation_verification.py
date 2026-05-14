from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_patch_apply import create_patch_plan
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.mutation_verification import (
    MutationVerificationCheck,
    MutationVerificationStatus,
    enforce_verification_result,
    read_verification_result,
    verify_patch_plan,
    write_verification_result,
)


def _session(
    verification: MutationVerificationRequirement,
):
    return create_mutation_session(
        intent="Verify mutation",
        initiator="test",
        reason="Verify governance enforcement",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.REVIEW_REQUIRED,
        verification=verification,
        sandbox_run_id="sandbox-run-1",
    )


def test_verification_passes_when_all_checks_pass() -> None:
    session = _session(
        MutationVerificationRequirement.TARGETED_TESTS
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
            MutationVerificationCheck(
                name="scope_validation",
                passed=True,
            ),
        ],
    )

    assert result.status == MutationVerificationStatus.PASSED
    assert "passed" in result.summary.lower()


def test_verification_fails_when_check_fails() -> None:
    session = _session(
        MutationVerificationRequirement.TARGETED_TESTS
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=False,
                details="2 tests failed",
            ),
        ],
    )

    assert result.status == MutationVerificationStatus.FAILED
    assert "pytest" in result.summary


def test_verification_fails_when_checks_missing() -> None:
    session = _session(
        MutationVerificationRequirement.FULL_TEST_SUITE
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[],
    )

    assert result.status == MutationVerificationStatus.FAILED


def test_manual_review_blocks_verification() -> None:
    session = _session(
        MutationVerificationRequirement.MANUAL_REVIEW
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
    )

    assert result.status == MutationVerificationStatus.BLOCKED


def test_none_verification_auto_passes() -> None:
    session = _session(
        MutationVerificationRequirement.NONE
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
    )

    assert result.status == MutationVerificationStatus.PASSED


def test_enforce_verification_result_blocks_failed_result() -> None:
    session = _session(
        MutationVerificationRequirement.TARGETED_TESTS
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=False,
            ),
        ],
    )

    with pytest.raises(ValueError):
        enforce_verification_result(result)


def test_enforce_verification_result_allows_passed_result() -> None:
    session = _session(
        MutationVerificationRequirement.TARGETED_TESTS
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
        ],
    )

    enforce_verification_result(result)


def test_write_and_read_verification_result(
    tmp_path: Path,
) -> None:
    session = _session(
        MutationVerificationRequirement.TARGETED_TESTS
    )

    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = verify_patch_plan(
        session=session,
        plan=plan,
        checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
        ],
    )

    path = write_verification_result(result, tmp_path)
    loaded = read_verification_result(path)

    assert loaded.session_id == result.session_id
    assert loaded.status == result.status
    assert loaded.checks[0].name == "pytest"