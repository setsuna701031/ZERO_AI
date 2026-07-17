from __future__ import annotations

from core.operator.operator_runner import run_operator_task


def test_operator_allow_path_closure() -> None:
    result = run_operator_task(
        "/operator planner",
        dry_run=True,
        allow_paths=[
            "core/runtime/controlled_mutation_sandbox_executor.py"
        ],
    )

    selected = result["selected_files"]
    assert selected == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]

    edit_plan = result["edit_plan"]

    assert edit_plan["target_files"] == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]

    assert edit_plan["impacted_files"] == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]

    actions = edit_plan["actions"]

    assert len(actions) == 1

    assert actions[0]["target_file"] == (
        "core/runtime/controlled_mutation_sandbox_executor.py"
    )