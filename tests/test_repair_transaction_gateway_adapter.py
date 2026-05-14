from __future__ import annotations

from pathlib import Path

from core.runtime.mutation_session import MutationApprovalMode
from core.runtime.repair_transaction_gateway_adapter import (
    build_gateway_request_from_repair_transaction,
)


def test_build_gateway_request_from_repair_transaction() -> None:
    transaction = {
        "transaction_id": "tx-001",
        "task_id": "task-001",
        "proposal_id": "proposal-001",
        "transaction_status": "staged",
        "dry_run": True,
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "core/example.py",
                "content": "print('hello')\n",
            }
        ],
        "sandbox_files": {
            "core/example.py": "print('sandbox')\n",
        },
    }

    request = build_gateway_request_from_repair_transaction(
        transaction,
        workspace_root="workspace",
        sandbox_source_root="sandbox",
        rollback_root="rollback",
        report_root="reports",
        approval_mode=MutationApprovalMode.AUTO,
    )

    assert request.intent == "governed repair transaction"
    assert request.relative_paths == ("core/example.py",)

    assert request.operations[0]["op_type"] == "write_file"
    assert request.operations[0]["target_path"] == "core/example.py"

    assert request.sandbox_files == {
        "core/example.py": "print('sandbox')\n"
    }

    assert request.scope.allowed_paths == ("core",)

    assert request.metadata["transaction_id"] == "tx-001"
    assert request.metadata["task_id"] == "task-001"
    assert request.metadata["proposal_id"] == "proposal-001"

    assert request.dry_run is True


def test_adapter_rejects_delete_operations() -> None:
    transaction = {
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "core/example.py",
            }
        ]
    }

    try:
        build_gateway_request_from_repair_transaction(
            transaction,
            workspace_root="workspace",
            sandbox_source_root="sandbox",
            rollback_root="rollback",
            report_root="reports",
        )
    except ValueError as exc:
        assert "delete_file" in str(exc)
        return

    raise AssertionError("expected delete_file rejection")


def test_adapter_extracts_staged_patch_operations() -> None:
    transaction = {
        "staged_patch": {
            "target_path": "core/example.py",
        },
        "raw_patch_preview": {
            "diff": "--- a/core/example.py\n+++ b/core/example.py\n+print('patched')\n",
        },
    }

    request = build_gateway_request_from_repair_transaction(
        transaction,
        workspace_root=Path("workspace"),
        sandbox_source_root=Path("sandbox"),
        rollback_root=Path("rollback"),
        report_root=Path("reports"),
    )

    assert request.relative_paths == ("core/example.py",)

    operation = request.operations[0]

    assert operation["op_type"] == "patch_file"
    assert operation["target_path"] == "core/example.py"
    assert "patch" in operation