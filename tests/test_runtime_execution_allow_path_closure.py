from __future__ import annotations

import pytest

from core.runtime.runtime_execution_planner import (
    RuntimeExecutionPlanRejected,
    RuntimeExecutionPlanner,
)


def test_runtime_execution_planner_accepts_target_inside_allow_path() -> None:
    planner = RuntimeExecutionPlanner()

    plan = planner.create_plan(
        "runtime_execution_allow_path_ok",
        [
            {
                "operation": "mutation.write",
                "target_file": "core/runtime/controlled_mutation_sandbox_executor.py",
            }
        ],
        allow_paths=["core/runtime/controlled_mutation_sandbox_executor.py"],
    )

    assert plan.allow_paths == ["core/runtime/controlled_mutation_sandbox_executor.py"]
    assert plan.transactions[0].steps[0].target_paths == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]


def test_runtime_execution_planner_rejects_target_outside_allow_path() -> None:
    planner = RuntimeExecutionPlanner()

    with pytest.raises(RuntimeExecutionPlanRejected):
        planner.create_plan(
            "runtime_execution_allow_path_blocked",
            [
                {
                    "operation": "mutation.write",
                    "target_file": "core/runtime/audit_log.py",
                }
            ],
            allow_paths=["core/runtime/controlled_mutation_sandbox_executor.py"],
        )