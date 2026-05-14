from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_approval import (
    evaluate_approval,
)
from core.runtime.mutation_audit import (
    build_mutation_audit_record,
    write_audit_record,
)
from core.runtime.mutation_patch_apply import (
    MutationPatchApplyResult,
    create_patch_plan,
)
from core.runtime.mutation_replay import (
    read_replay_timeline,
    reconstruct_mutation_timeline,
    reconstruct_mutation_timeline_from_file,
    replay_event_types,
    write_replay_timeline,
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


def _session():
    return create_mutation_session(
        intent="Replay governed mutation",
        initiator="test",
        reason="Verify replay reconstruction",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
    )


def _audit_record():
    session = _session()

    plan = create_patch_plan(
        session=session,
        relative_paths=[
            "core/runtime/demo.py"
        ],
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
        applied_paths=(
            "core/runtime/demo.py",
        ),
        skipped_paths=(),
        rollback_paths=(
            "core/runtime/demo.py",
        ),
        report_path="reports/apply.json",
    )

    record = build_mutation_audit_record(
        session=session,
        patch_plan=plan,
        verification=verification,
        approval=approval,
        apply_result=apply_result,
    )

    return record


def test_reconstruct_mutation_timeline() -> None:
    record = _audit_record()

    timeline = reconstruct_mutation_timeline(
        record
    )

    assert timeline.session_id == (
        record.session_id
    )

    assert timeline.total_events == 5

    assert replay_event_types(
        timeline
    ) == (
        "mutation.session.created",
        "mutation.patch_plan.created",
        "mutation.verification.completed",
        "mutation.approval.completed",
        "mutation.apply.completed",
    )


def test_replay_timeline_contains_status_summary() -> None:
    record = _audit_record()

    timeline = reconstruct_mutation_timeline(
        record
    )

    verification_step = timeline.steps[2]

    assert (
        verification_step.payload_summary[
            "status"
        ]
        == "passed"
    )

    approval_step = timeline.steps[3]

    assert (
        approval_step.payload_summary[
            "status"
        ]
        == "approved"
    )


def test_write_and_read_replay_timeline(
    tmp_path: Path,
) -> None:
    record = _audit_record()

    timeline = reconstruct_mutation_timeline(
        record
    )

    path = write_replay_timeline(
        timeline,
        tmp_path,
    )

    loaded = read_replay_timeline(path)

    assert loaded.session_id == (
        timeline.session_id
    )

    assert replay_event_types(
        loaded
    ) == replay_event_types(timeline)


def test_reconstruct_timeline_from_audit_file(
    tmp_path: Path,
) -> None:
    record = _audit_record()

    audit_path = write_audit_record(
        record,
        tmp_path,
    )

    timeline = (
        reconstruct_mutation_timeline_from_file(
            audit_path
        )
    )

    assert timeline.total_events == 5


def test_reconstruct_empty_record_fails() -> None:
    session = _session()

    empty_record = build_mutation_audit_record(
        session=session,
    )

    empty_record = type(empty_record)(
        session_id=empty_record.session_id,
        created_at=empty_record.created_at,
        events=(),
        metadata=empty_record.metadata,
    )

    with pytest.raises(ValueError):
        reconstruct_mutation_timeline(
            empty_record
        )