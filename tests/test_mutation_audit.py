from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_approval import evaluate_approval
from core.runtime.mutation_audit import (
    build_mutation_audit_record,
    create_audit_event,
    event_types,
    read_audit_record,
    write_audit_record,
)
from core.runtime.mutation_patch_apply import MutationPatchApplyResult, create_patch_plan
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.mutation_verification import MutationVerificationCheck, verify_patch_plan


def _session():
    return create_mutation_session(
        intent="Audit governed mutation",
        initiator="test",
        reason="Verify mutation audit event chain",
        scope=MutationScope(allowed_paths=("core/runtime",)),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
    )


def test_create_audit_event_requires_type() -> None:
    with pytest.raises(ValueError):
        create_audit_event(
            event_type="",
            session_id="session-1",
        )


def test_build_audit_record_contains_governance_events() -> None:
    session = _session()

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
                passed=True,
            )
        ],
    )

    approval = evaluate_approval(
        session=session,
        verification=verification,
    )

    apply_result = MutationPatchApplyResult(
        session_id=session.session_id,
        applied=True,
        applied_paths=("core/runtime/demo.py",),
        skipped_paths=(),
        rollback_paths=("core/runtime/demo.py",),
        report_path="reports/mutation_patch_apply_report.json",
    )

    record = build_mutation_audit_record(
        session=session,
        patch_plan=plan,
        verification=verification,
        approval=approval,
        apply_result=apply_result,
        metadata={"track": "controlled-mutation-sandbox"},
    )

    assert record.session_id == session.session_id
    assert event_types(record) == (
        "mutation.session.created",
        "mutation.patch_plan.created",
        "mutation.verification.completed",
        "mutation.approval.completed",
        "mutation.apply.completed",
    )
    assert record.metadata["track"] == "controlled-mutation-sandbox"


def test_write_and_read_audit_record(tmp_path: Path) -> None:
    session = _session()
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    record = build_mutation_audit_record(
        session=session,
        patch_plan=plan,
    )

    path = write_audit_record(record, tmp_path)
    loaded = read_audit_record(path)

    assert loaded.session_id == record.session_id
    assert event_types(loaded) == (
        "mutation.session.created",
        "mutation.patch_plan.created",
    )


def test_audit_rejects_session_mismatch() -> None:
    session_a = _session()
    session_b = create_mutation_session(
        intent="Other mutation",
        initiator="test",
        reason="Mismatch",
        scope=MutationScope(allowed_paths=("core/runtime",)),
    )

    plan_b = create_patch_plan(
        session=session_b,
        relative_paths=["core/runtime/demo.py"],
    )

    with pytest.raises(ValueError):
        build_mutation_audit_record(
            session=session_a,
            patch_plan=plan_b,
        )


def test_audit_accepts_extra_events_for_same_session() -> None:
    session = _session()

    extra = create_audit_event(
        event_type="mutation.custom.note",
        session_id=session.session_id,
        payload={"note": "manual checkpoint"},
    )

    record = build_mutation_audit_record(
        session=session,
        extra_events=[extra],
    )

    assert event_types(record) == (
        "mutation.session.created",
        "mutation.custom.note",
    )