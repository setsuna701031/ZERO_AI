from __future__ import annotations

import json
from pathlib import Path

from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalStatus,
)
from core.runtime.mutation_gateway import MutationGatewayRequest, run_governed_mutation
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck


def test_gateway_passes_operations_and_sandbox_files_through_pipeline(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    scope = MutationScope(
        allowed_paths=("core",),
        max_files_changed=3,
        allow_new_files=True,
    )

    request = MutationGatewayRequest(
        intent="test governed operation flow",
        initiator="test",
        reason="verify operations and sandbox_files flow through gateway pipeline",
        relative_paths=("core/example.py",),
        scope=scope,
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        operations=(
            {
                "op_type": "write_file",
                "target_path": "core/example.py",
                "content": "print('hello from governed mutation')\n",
            },
        ),
        sandbox_files={
            "core/example.py": "print('hello from sandbox file')\n",
        },
        risk_level=MutationRiskLevel.LOW,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
        verification_checks=(
            MutationVerificationCheck(
                name="unit-test-check",
                passed=True,
                details="synthetic verification check passed",
            ),
        ),
        approval_decisions=(
            MutationApprovalDecision(
                actor="unit-test",
                decision=MutationApprovalStatus.APPROVED,
                reason="synthetic approval",
            ),
        ),
        dry_run=False,
        metadata={"test_case": "operations_flow"},
    )

    result = run_governed_mutation(request)

    assert result.completed is True
    assert result.apply_result is not None
    assert result.apply_result.applied is True
    assert result.apply_result.applied_paths == ("core/example.py",)

    written = workspace / "core" / "example.py"
    assert written.read_text(encoding="utf-8") == "print('hello from sandbox file')\n"

    patch_plan_path = reports / "mutation_patch_plan.json"
    patch_plan = json.loads(patch_plan_path.read_text(encoding="utf-8"))

    assert patch_plan["sandbox_files"] == {
        "core/example.py": "print('hello from sandbox file')\n"
    }

    assert patch_plan["items"][0]["operation"] == "write_file"

    assert patch_plan["items"][0]["operation_payload"]["content"] == (
        "print('hello from governed mutation')\n"
    )

    assert patch_plan["metadata"]["test_case"] == "operations_flow"