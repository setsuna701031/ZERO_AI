from __future__ import annotations

from core.runtime.step_executor import StepExecutor


def test_step_executor_denies_execution_when_runtime_frozen() -> None:
    executor = StepExecutor()

    result = executor.execute_step(
        step={"type": "read_file", "path": "README.md"},
        context={
            "runtime_freeze": {
                "runtime_frozen": True,
                "reason": "rollback verification mismatch",
                "freeze_id": "freeze-001",
            }
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "runtime_execution_frozen"
    assert result["result"]["action"] == "runtime_execution_frozen"
    assert result["result"]["runtime_freeze_decision"]["runtime_frozen"] is True
    assert result["result"]["runtime_freeze_decision"]["freeze_id"] == "freeze-001"


def test_step_executor_can_disable_freeze_enforcement_for_compatibility() -> None:
    executor = StepExecutor()

    result = executor.execute_step(
        step={"type": "read_file", "path": "README.md"},
        context={
            "runtime_freeze": {
                "runtime_frozen": True,
                "reason": "rollback verification mismatch",
            },
            "enforce_freeze": False,
        },
    )

    assert result["error"]["type"] != "runtime_execution_frozen"
