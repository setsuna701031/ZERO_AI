from __future__ import annotations

from pathlib import Path

from core.runtime.governed_repair_execution import execute_governed_repair_transaction
from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalStatus,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)


def test_execute_governed_repair_transaction_writes_through_gateway(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "repair_tx_governed_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "dry_run": False,
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/example.py",
                "content": "print('governed repair execution')\n",
            }
        ],
    }

    result = execute_governed_repair_transaction(
        transaction,
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
    )

    assert result.completed is True
    assert result.apply_result is not None
    assert result.apply_result.applied is True
    assert result.apply_result.applied_paths == ("project/example.py",)

    written = workspace / "project" / "example.py"
    assert written.read_text(encoding="utf-8") == "print('governed repair execution')\n"


def test_execute_governed_repair_transaction_blocks_failed_preflight(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "repair_tx_blocked_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "../outside.py",
                "content": "bad",
            }
        ],
    }

    try:
        execute_governed_repair_transaction(
            transaction,
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            allowed_roots=("project",),
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.NONE,
        )
    except ValueError as exc:
        assert "repair_transaction_preflight_failed" in str(exc)
        return

    raise AssertionError("expected preflight failure")