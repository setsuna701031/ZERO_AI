from __future__ import annotations

from pathlib import Path

from core.runtime.step_executor import StepExecutor


def test_step_executor_dispatches_governed_repair_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    executor = StepExecutor()

    assert executor.has_handler("governed_repair_mutation")

    result = executor.execute_step(
        {
            "id": "governed_repair_mutation_001",
            "type": "governed_repair_mutation",
            "task_id": "task_001",
            "proposal_id": "proposal_001",
            "goal": "write through governed repair mutation handler",
            "mutation": {
                "op_type": "write_file",
                "target_path": "project/example.py",
                "content": "print('step executor governed repair')\n",
            },
            "allowed_roots": ["project"],
            "workspace_root": str(workspace),
            "sandbox_source_root": str(sandbox),
            "rollback_root": str(rollback),
            "report_root": str(reports),
        },
        task={
            "task_id": "task_001",
        },
        context={},
    )

    assert result["ok"] is True

    result_payload = result.get("result")
    assert isinstance(result_payload, dict)

    result_text = str(result_payload)
    assert "governed_repair_mutation" in result_text
    assert "pipeline_result" in result_text

    written = workspace / "project" / "example.py"

    assert written.read_text(encoding="utf-8") == (
        "print('step executor governed repair')\n"
    )