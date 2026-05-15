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
def test_execute_governed_repair_transaction_calls_gate_hook(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "repair_tx_gate_hook_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "dry_run": False,
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/gated.py",
                "content": "print('gate hook passed')\n",
            }
        ],
    }

    calls = []

    def gate_hook(context):
        calls.append(context)
        assert context["transaction"] is transaction
        assert context["preflight"]["ok"] is True
        assert context["apply_plan"]["ready"] is True
        assert context["request"].reason
        return {"ok": True}

    result = execute_governed_repair_transaction(
        transaction,
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
        gate_hook=gate_hook,
    )

    assert len(calls) == 1
    assert result.completed is True
    assert (workspace / "project" / "gated.py").read_text(encoding="utf-8") == "print('gate hook passed')\n"


def test_execute_governed_repair_transaction_blocks_when_gate_hook_blocks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "repair_tx_gate_hook_blocked_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "dry_run": False,
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/blocked.py",
                "content": "print('should not write')\n",
            }
        ],
    }

    def gate_hook(context):
        return {
            "ok": False,
            "error": "blocked by governed repair gate",
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
            gate_hook=gate_hook,
        )
    except ValueError as exc:
        assert "governed_repair_gate_blocked" in str(exc)
        assert "blocked by governed repair gate" in str(exc)
        assert not (workspace / "project" / "blocked.py").exists()
        return

    raise AssertionError("expected governed repair gate to block execution")

def test_execute_governed_repair_mutation_passes_gate_hook_from_api(tmp_path: Path) -> None:
    from core.runtime.governed_repair_api import execute_governed_repair_mutation

    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    calls = []

    def gate_hook(context):
        calls.append(context)
        assert context["preflight"]["ok"] is True
        assert context["apply_plan"]["ready"] is True
        assert context["request"].intent
        return {"ok": True}

    result = execute_governed_repair_mutation(
        task_id="task_api_gate_hook",
        proposal_id="proposal_api_gate_hook",
        goal="api gate hook passthrough",
        mutation={
            "op_type": "write_file",
            "target_path": "project/api_gate.py",
            "content": "print('api gate hook')\n",
        },
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
        gate_hook=gate_hook,
    )

    assert len(calls) == 1
    assert result.completed is True
    assert (workspace / "project" / "api_gate.py").read_text(encoding="utf-8") == "print('api gate hook')\n"

def test_execute_governed_repair_transaction_can_use_runtime_recovery_gate(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "repair_tx_runtime_recovery_gate_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "dry_run": False,
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/runtime_recovery_gate.py",
                "content": "print('runtime recovery gate')\n",
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
        use_runtime_recovery_gate=True,
    )

    assert result.completed is True
    assert (workspace / "project" / "runtime_recovery_gate.py").read_text(
        encoding="utf-8"
    ) == "print('runtime recovery gate')\n"
