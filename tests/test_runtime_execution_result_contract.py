from __future__ import annotations

import importlib


def test_runtime_execution_result_is_canonical_immutable_mapping():
    module = importlib.import_module("core.runtime.runtime_execution_result")

    result = module.RuntimeExecutionResult.from_legacy_plan_result(
        execution_id="execution-1",
        execution_start_id="execution_start-1",
        execution_type="plan",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        legacy_result={"success": True, "final_verify_result": {"passed": True}},
        lineage={"request_id": "request-1"},
    )

    assert result.execution_id == "execution-1"
    assert result.execution_start_id == "execution_start-1"
    assert result.status == "succeeded"
    assert result.verified is True
    assert result["success"] is True
    assert result["execution_id"] == "execution-1"
    assert isinstance(result.to_dict(), dict)
    assert not isinstance(result, dict)


def test_executor_returns_runtime_execution_result(tmp_path):
    executor_module = importlib.import_module("core.runtime.executor")
    result_module = importlib.import_module("core.runtime.runtime_execution_result")
    executor = executor_module.Executor(workspace_root=tmp_path)

    result = executor.execute_plan(
        task_name="result_contract",
        plan={
            "steps": [
                {
                    "type": "write_file",
                    "path": "out.txt",
                    "content": "hello",
                }
            ]
        },
        iteration=1,
    )

    assert isinstance(result, result_module.RuntimeExecutionResult)
    assert result.status == "succeeded"
    assert result["success"] is True
    assert result.side_effects
    assert result.side_effects[0].effect_type == "file_mutation"
    assert result.side_effects[0].source_execution_id == result.execution_id
