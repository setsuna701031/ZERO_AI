from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalStatus,
)
from core.runtime.mutation_runtime_pipeline import (
    run_mutation_runtime_pipeline,
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
)


def _session(
    approval_mode: MutationApprovalMode = MutationApprovalMode.AUTO,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
):
    return create_mutation_session(
        intent="Run governed mutation pipeline",
        initiator="test",
        reason="Verify transaction pipeline",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
            max_files_changed=3,
            allow_new_files=True,
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=approval_mode,
        verification=verification,
        sandbox_run_id="sandbox-run-1",
    )


def test_runtime_pipeline_applies_verified_approved_patch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session()

    result = run_mutation_runtime_pipeline(
        session=session,
        relative_paths=["core/runtime/demo.py"],
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        verification_checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            )
        ],
        metadata={"track": "controlled-mutation-sandbox"},
    )

    assert result.completed is True
    assert result.apply_result is not None
    assert result.apply_result.applied is True
    assert target.read_text(encoding="utf-8") == "VERSION = 2\n"

    rollback_file = rollback / "core" / "runtime" / "demo.py"
    assert rollback_file.exists()
    assert rollback_file.read_text(encoding="utf-8") == "VERSION = 1\n"

    assert Path(result.artifact_paths["session"]).exists()
    assert Path(result.artifact_paths["patch_plan"]).exists()
    assert Path(result.artifact_paths["verification"]).exists()
    assert Path(result.artifact_paths["approval"]).exists()
    assert Path(result.artifact_paths["audit"]).exists()
    assert Path(result.artifact_paths["pipeline_result"]).exists()

    audit_data = json.loads(Path(result.artifact_paths["audit"]).read_text(encoding="utf-8"))
    assert audit_data["session_id"] == session.session_id
    assert [event["event_type"] for event in audit_data["events"]] == [
        "mutation.session.created",
        "mutation.patch_plan.created",
        "mutation.verification.completed",
        "mutation.approval.completed",
        "mutation.apply.completed",
    ]


def test_runtime_pipeline_blocks_when_verification_fails(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session()

    with pytest.raises(ValueError):
        run_mutation_runtime_pipeline(
            session=session,
            relative_paths=["core/runtime/demo.py"],
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            verification_checks=[
                MutationVerificationCheck(
                    name="pytest",
                    passed=False,
                )
            ],
        )

    assert not (workspace / "core" / "runtime" / "demo.py").exists()
    assert (reports / "mutation_verification_result.json").exists()
    assert not (reports / "mutation_approval_result.json").exists()
    assert not (reports / "mutation_audit_record.json").exists()


def test_runtime_pipeline_blocks_when_approval_pending(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session(
        approval_mode=MutationApprovalMode.REVIEW_REQUIRED,
    )

    with pytest.raises(ValueError):
        run_mutation_runtime_pipeline(
            session=session,
            relative_paths=["core/runtime/demo.py"],
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            verification_checks=[
                MutationVerificationCheck(
                    name="pytest",
                    passed=True,
                )
            ],
        )

    assert not (workspace / "core" / "runtime" / "demo.py").exists()
    assert (reports / "mutation_verification_result.json").exists()
    assert (reports / "mutation_approval_result.json").exists()
    assert not (reports / "mutation_audit_record.json").exists()


def test_runtime_pipeline_allows_human_required_with_human_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session(
        approval_mode=MutationApprovalMode.HUMAN_REQUIRED,
    )

    result = run_mutation_runtime_pipeline(
        session=session,
        relative_paths=["core/runtime/demo.py"],
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        verification_checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            )
        ],
        approval_decisions=[
            MutationApprovalDecision(
                actor="human:setsuna",
                decision=MutationApprovalStatus.APPROVED,
            )
        ],
    )

    assert result.completed is True
    assert (workspace / "core" / "runtime" / "demo.py").read_text(encoding="utf-8") == "VERSION = 2\n"


def test_runtime_pipeline_dry_run_does_not_modify_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session()

    result = run_mutation_runtime_pipeline(
        session=session,
        relative_paths=["core/runtime/demo.py"],
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        verification_checks=[
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            )
        ],
        dry_run=True,
    )

    assert result.completed is True
    assert result.dry_run is True
    assert result.apply_result is not None
    assert result.apply_result.applied is False
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"