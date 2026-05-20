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
from core.runtime.runtime_evidence_chain import validate_runtime_evidence_record
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)


def test_runtime_repair_transaction_lifecycle_executes_through_governed_gateway(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = create_runtime_repair_transaction(
        task_id="task_001",
        proposal_id="proposal_001",
        goal="write governed repair lifecycle file",
        scope_gate={"scope_allowed": True},
    )

    assert transaction["state"] == "created"

    staged = stage_runtime_repair_mutation(
        transaction,
        {
            "op_type": "write_file",
            "target_path": "project/example.py",
            "content": "print('runtime lifecycle governed execution')\n",
        },
    )

    assert staged["state"] == "staged"
    assert len(staged["staged_mutations"]) == 1

    committed = commit_runtime_repair_transaction(staged)

    assert committed["state"] == "committed"
    assert len(committed["committed_mutations"]) == 1

    executable = build_executable_repair_transaction(committed)

    assert executable["status"] == "staged"
    assert executable["operations"] == [
        {
            "op_type": "write_file",
            "target_path": "project/example.py",
            "content": "print('runtime lifecycle governed execution')\n",
        }
    ]

    result = execute_committed_runtime_repair_transaction(
        committed,
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
    assert result.audit_record.metadata["runtime_evidence_id"]
    assert (
        validate_runtime_evidence_record(
            result.audit_record.metadata["runtime_evidence_record"]
        )["ok"]
        is True
    )
    assert result.audit_record.metadata["runtime_audit_metadata"]["session_id"] == result.session_id
    assert result.audit_record.metadata["runtime_audit_metadata"]["execution_session_id"] == result.session_id
    assert result.audit_record.metadata["runtime_audit_metadata"]["replay_session_id"]
    assert result.audit_record.metadata["runtime_audit_metadata"]["mutation_request_id"] == (
        f"repair_request:{committed['transaction_id']}"
    )
    assert (
        result.audit_record.metadata["runtime_evidence_record"]["mutation_transaction_id"]
        == committed["transaction_id"]
    )
    assert (
        result.audit_record.metadata["runtime_evidence_record"]["mutation_request_id"]
        == f"repair_request:{committed['transaction_id']}"
    )
    assert (
        result.audit_record.metadata["runtime_evidence_record"]["authority_metadata"][
            "repair_authority_governance"
        ]["scope_allowed"]
        is True
    )
    assert (
        result.audit_record.metadata["runtime_audit_metadata"]["lineage"]["transaction_id"]
        == committed["transaction_id"]
    )
    assert (
        result.audit_record.metadata["runtime_audit_metadata"]["lineage"]["mutation_request_id"]
        == f"repair_request:{committed['transaction_id']}"
    )

    written = workspace / "project" / "example.py"

    assert written.read_text(encoding="utf-8") == (
        "print('runtime lifecycle governed execution')\n"
    )
