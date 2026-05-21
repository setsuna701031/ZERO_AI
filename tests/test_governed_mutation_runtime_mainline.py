from __future__ import annotations

from pathlib import Path

from core.runtime.governed_mutation_runtime import run_governed_mutation_runtime
from core.runtime.mutation_gateway import (
    MutationGatewayRequest,
    run_governed_mutation_mainline,
)
from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck


def test_governed_runtime_mainline_applies_verifies_and_persists_evidence(
    tmp_path: Path,
) -> None:
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

    result = run_governed_mutation_runtime(
        MutationGatewayRequest(
            intent="Update runtime demo",
            initiator="test",
            reason="verify governed mainline closure",
            relative_paths=("core/runtime/demo.py",),
            scope=MutationScope(allowed_paths=("core/runtime",)),
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(
                MutationVerificationCheck(name="pytest", passed=True, details="ok"),
            ),
        )
    )

    payload = result.to_dict()

    assert payload["executed"] is True
    assert payload["blocked"] is False
    assert payload["failed"] is False
    assert payload["verified"] is True
    assert payload["rolled_back"] is False
    assert payload["recovered"] is False
    assert payload["evidence"]["stdout"] == "ok"
    assert payload["impacted_files"] == ["core/runtime/demo.py"]
    assert payload["rollback_snapshot"]["rollback_paths"] == ["core/runtime/demo.py"]
    assert Path(payload["artifact_paths"]["evidence"]).exists()
    assert payload["runtime_execution_result"]["verification_passed"] is True
    assert target.read_text(encoding="utf-8") == "VERSION = 2\n"


def test_governed_runtime_mainline_rolls_back_failed_verification(
    tmp_path: Path,
) -> None:
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

    result = run_governed_mutation_runtime(
        MutationGatewayRequest(
            intent="Update runtime demo",
            initiator="test",
            reason="verify governed rollback closure",
            relative_paths=("core/runtime/demo.py",),
            scope=MutationScope(allowed_paths=("core/runtime",)),
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(
                MutationVerificationCheck(name="pytest", passed=False, details="boom"),
            ),
        )
    )

    payload = result.to_dict()

    assert payload["executed"] is True
    assert payload["failed"] is True
    assert payload["verified"] is False
    assert payload["rolled_back"] is True
    assert payload["evidence"]["stderr"] == "boom"
    assert payload["rollback_snapshot"]["restored_paths"] == ["core/runtime/demo.py"]
    assert payload["runtime_execution_result"]["rolled_back"] is True
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"


def test_governed_mutation_gateway_mainline_returns_runtime_execution_result(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    result = run_governed_mutation_mainline(
        MutationGatewayRequest(
            intent="Create runtime demo",
            initiator="test",
            reason="verify canonical gateway mainline result",
            relative_paths=("core/runtime/demo.py",),
            scope=MutationScope(allowed_paths=("core/runtime",)),
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(
                MutationVerificationCheck(name="pytest", passed=True, details="ok"),
            ),
        )
    )

    assert isinstance(result, RuntimeExecutionResult)
    payload = result.to_dict()
    assert payload["executed"] is True
    assert payload["verification_passed"] is True
    assert payload["evidence"]["stdout"] == "ok"
    assert payload["impacted_files"] == ["core/runtime/demo.py"]
