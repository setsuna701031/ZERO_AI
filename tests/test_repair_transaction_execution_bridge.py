from __future__ import annotations

from pathlib import Path

from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)
from core.runtime.repair_transaction_execution_bridge import (
    build_executable_repair_transaction,
    execute_committed_runtime_repair_transaction,
)


def test_build_executable_repair_transaction() -> None:
    transaction = {
        "transaction_id": "runtime_tx_001",
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "state": "committed",
        "committed_mutations": [
            {
                "mutation_id": "mutation_001",
                "action": "write_file",
                "target_path": "project/example.py",
                "raw_mutation": {
                    "op_type": "write_file",
                    "target_path": "project/example.py",
                    "content": "print('bridge')\n",
                },
            }
        ],
    }

    executable = build_executable_repair_transaction(transaction)

    assert executable["transaction_id"] == "runtime_tx_001"
    assert executable["status"] == "staged"

    assert executable["operations"] == [
        {
            "op_type": "write_file",
            "target_path": "project/example.py",
            "content": "print('bridge')\n",
        }
    ]


def test_execute_committed_runtime_repair_transaction(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = {
        "transaction_id": "runtime_tx_exec_001",
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "state": "committed",
        "committed_mutations": [
            {
                "mutation_id": "mutation_001",
                "action": "write_file",
                "target_path": "project/example.py",
                "raw_mutation": {
                    "op_type": "write_file",
                    "target_path": "project/example.py",
                    "content": "print('execution bridge')\n",
                },
            }
        ],
    }

    result = execute_committed_runtime_repair_transaction(
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

    written = workspace / "project" / "example.py"

    assert written.read_text(encoding="utf-8") == (
        "print('execution bridge')\n"
    )


def test_bridge_rejects_non_committed_transaction() -> None:
    transaction = {
        "transaction_id": "runtime_tx_blocked",
        "state": "staged",
        "committed_mutations": [],
    }

    try:
        build_executable_repair_transaction(transaction)
    except ValueError as exc:
        assert "not_committed" in str(exc)
        return

    raise AssertionError("expected non committed transaction rejection")