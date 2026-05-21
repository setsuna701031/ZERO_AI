from __future__ import annotations

from pathlib import Path

from core.runtime.step_executor import StepExecutor
from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.repair_transaction_execution_bridge import (
    execute_committed_runtime_repair_transaction_mainline,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)


def test_runtime_execution_result_normalizes_legacy_step_payload() -> None:
    result = RuntimeExecutionResult.from_runtime_mapping(
        execution_id="runtime_execution:test",
        execution_start_id="execution_start:test",
        execution_type="unit",
        result={
            "ok": True,
            "message": "done",
            "verification": {"ok": True},
            "changed_files": ["core/runtime/demo.py"],
            "rollback_metadata": {"restore_available": True},
        },
    )

    payload = result.to_dict()

    assert payload["executed"] is True
    assert payload["blocked"] is False
    assert payload["failed"] is False
    assert payload["verification_passed"] is True
    assert payload["evidence"]["mutation_summary"]
    assert payload["impacted_files"] == ["core/runtime/demo.py"]
    assert payload["rollback_snapshot"]["restore_available"] is True


def test_step_executor_attaches_canonical_runtime_execution_result(
    tmp_path: Path,
) -> None:
    executor = StepExecutor(workspace_root=str(tmp_path))

    result = executor.execute_step(
        {
            "type": "write_file",
            "path": "shared/out.txt",
            "content": "hello\n",
        },
        task={"task_id": "task_001"},
        step_index=1,
        step_count=1,
    )

    runtime_result = result["runtime_execution_result"]

    assert runtime_result["executed"] is True
    assert runtime_result["failed"] is False
    assert runtime_result["verification_passed"] is True
    assert runtime_result["evidence"]
    assert "rollback_snapshot" in runtime_result


def test_repair_transaction_mainline_returns_runtime_execution_result(
    tmp_path: Path,
) -> None:
    transaction = create_runtime_repair_transaction(
        task_id="task_001",
        proposal_id="proposal_001",
        goal="write repair file through runtime mainline",
        scope_gate={"scope_allowed": True},
    )
    staged = stage_runtime_repair_mutation(
        transaction,
        {
            "op_type": "write_file",
            "target_path": "project/example.py",
            "content": "print('repair mainline')\n",
        },
    )
    committed = commit_runtime_repair_transaction(staged)

    result = execute_committed_runtime_repair_transaction_mainline(
        committed,
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
    )

    assert isinstance(result, RuntimeExecutionResult)
    payload = result.to_dict()
    assert payload["executed"] is True
    assert payload["verification_passed"] is True
    assert payload["impacted_files"] == ["project/example.py"]
    assert payload["evidence"]["mutation_summary"]
