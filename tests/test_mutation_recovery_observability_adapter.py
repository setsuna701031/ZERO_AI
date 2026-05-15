from __future__ import annotations

from pathlib import Path

from core.runtime.mutation_recovery_observability_adapter import (
    MutationRecoveryObservabilityAdapter,
    build_mutation_recovery_observability,
)
from core.runtime.mutation_runtime_pipeline import run_mutation_runtime_pipeline
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.mutation_verification import MutationVerificationCheck


def _session():
    return create_mutation_session(
        intent="Run governed mutation pipeline",
        initiator="test",
        reason="Verify mutation recovery observability adapter",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
            max_files_changed=3,
            allow_new_files=True,
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
    )


def _pipeline_result(tmp_path: Path, *, dry_run: bool):
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

    return run_mutation_runtime_pipeline(
        session=_session(),
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
        dry_run=dry_run,
    )


def test_build_mutation_recovery_observability_ready(tmp_path: Path) -> None:
    payload = build_mutation_recovery_observability(
        _pipeline_result(tmp_path, dry_run=False)
    )

    assert payload["schema"] == MutationRecoveryObservabilityAdapter.SCHEMA
    assert payload["completed"] is True
    assert payload["dry_run"] is False

    summary = payload["operator_summary"]

    assert summary["readiness"] == "ready"
    assert summary["status"] == "ready"


def test_build_mutation_recovery_observability_dry_run(tmp_path: Path) -> None:
    payload = build_mutation_recovery_observability(
        _pipeline_result(tmp_path, dry_run=True)
    )

    assert payload["completed"] is True
    assert payload["dry_run"] is True

    summary = payload["operator_summary"]

    assert summary["readiness"] == "blocked"
    assert "dry_run_only" in summary["blockers"]
