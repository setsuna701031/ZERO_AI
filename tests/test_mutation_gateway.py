from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalStatus,
)
from core.runtime.mutation_gateway import (
    MutationGatewayRequest,
    run_governed_mutation,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck


def test_gateway_runs_governed_mutation(tmp_path: Path) -> None:
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

    request = MutationGatewayRequest(
        intent="Gateway mutation",
        initiator="test",
        reason="Verify gateway boundary",
        relative_paths=("core/runtime/demo.py",),
        scope=MutationScope(
            allowed_paths=("core/runtime",),
            max_files_changed=2,
            allow_new_files=True,
        ),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="gateway-run-1",
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
        ),
        metadata={"track": "mutation-gateway"},
    )

    result = run_governed_mutation(request)

    assert result.completed is True
    assert result.apply_result is not None
    assert result.apply_result.applied is True
    assert target.read_text(encoding="utf-8") == "VERSION = 2\n"
    assert (rollback / "core" / "runtime" / "demo.py").exists()
    assert Path(result.artifact_paths["audit"]).exists()


def test_gateway_blocks_failed_verification(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    request = MutationGatewayRequest(
        intent="Gateway mutation",
        initiator="test",
        reason="Verify failed gate",
        relative_paths=("core/runtime/demo.py",),
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        approval_mode=MutationApprovalMode.AUTO,
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=False,
            ),
        ),
    )

    with pytest.raises(ValueError):
        run_governed_mutation(request)

    assert not (workspace / "core" / "runtime" / "demo.py").exists()


def test_gateway_supports_human_required_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    request = MutationGatewayRequest(
        intent="Gateway human approval mutation",
        initiator="test",
        reason="Verify human approval through gateway",
        relative_paths=("core/runtime/demo.py",),
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        approval_mode=MutationApprovalMode.HUMAN_REQUIRED,
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
        ),
        approval_decisions=(
            MutationApprovalDecision(
                actor="human:setsuna",
                decision=MutationApprovalStatus.APPROVED,
            ),
        ),
    )

    result = run_governed_mutation(request)

    assert result.completed is True
    assert (workspace / "core" / "runtime" / "demo.py").exists()


def test_gateway_rejects_empty_relative_paths(tmp_path: Path) -> None:
    request = MutationGatewayRequest(
        intent="Bad gateway request",
        initiator="test",
        reason="Missing paths",
        relative_paths=(),
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
    )

    with pytest.raises(ValueError):
        run_governed_mutation(request)


def test_gateway_dry_run_does_not_modify_workspace(tmp_path: Path) -> None:
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

    request = MutationGatewayRequest(
        intent="Gateway dry run",
        initiator="test",
        reason="Verify dry run boundary",
        relative_paths=("core/runtime/demo.py",),
        scope=MutationScope(
            allowed_paths=("core/runtime",),
        ),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        approval_mode=MutationApprovalMode.AUTO,
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=True,
            ),
        ),
        dry_run=True,
    )

    result = run_governed_mutation(request)

    assert result.completed is True
    assert result.apply_result is not None
    assert result.apply_result.applied is False
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"