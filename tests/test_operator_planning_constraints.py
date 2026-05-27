from core.operator.operator_planning_constraints import (
    PlanningConstraints,
    apply_planning_constraints,
)


def _sample_plan():
    return {
        "actions": [
            {"target_file": "tests/test_controlled_mutation_execution_closure.py"},
            {"target_file": "core/runtime/execution_gateway.py"},
        ],
        "target_files": [
            "tests/test_controlled_mutation_execution_closure.py",
            "core/runtime/execution_gateway.py",
        ],
        "impacted_files": [
            "tests/test_controlled_mutation_execution_closure.py",
            "core/runtime/execution_gateway.py",
        ],
    }


def test_allow_paths_single_file_filters_everything_else():
    constraints = PlanningConstraints.from_request(
        allow_paths=["tests/test_controlled_mutation_execution_closure.py"],
        user_intent="STRICT SINGLE FILE ONLY tests/test_controlled_mutation_execution_closure.py",
    )

    result = apply_planning_constraints(
        edit_plan=_sample_plan(),
        selected_files=[
            "tests/test_controlled_mutation_execution_closure.py",
            "core/runtime/execution_gateway.py",
        ],
        constraints=constraints,
    )

    assert result.selected_files == ["tests/test_controlled_mutation_execution_closure.py"]
    assert result.edit_plan["target_files"] == ["tests/test_controlled_mutation_execution_closure.py"]
    assert result.edit_plan["impacted_files"] == ["tests/test_controlled_mutation_execution_closure.py"]
    assert [a["target_file"] for a in result.edit_plan["actions"]] == [
        "tests/test_controlled_mutation_execution_closure.py"
    ]
    assert "core/runtime/execution_gateway.py" in result.constraint_filtered_files


def test_test_only_blocks_runtime_implementation():
    constraints = PlanningConstraints.from_request(
        allow_paths=["tests"],
        user_intent="TEST FILE ONLY. DO NOT MODIFY RUNTIME IMPLEMENTATION.",
    )

    result = apply_planning_constraints(
        edit_plan=_sample_plan(),
        selected_files=["core/runtime/execution_gateway.py"],
        constraints=constraints,
    )

    assert result.selected_files == []
    assert all(not f.startswith("core/runtime/") for f in result.edit_plan["target_files"])


def test_block_on_violation_marks_constraint_violation():
    constraints = PlanningConstraints.from_request(
        allow_paths=["tests/test_controlled_mutation_execution_closure.py"],
        user_intent="STRICT SINGLE FILE ONLY tests/test_controlled_mutation_execution_closure.py",
    )

    result = apply_planning_constraints(
        edit_plan=_sample_plan(),
        selected_files=["core/runtime/execution_gateway.py"],
        constraints=constraints,
        block_on_violation=True,
    )

    assert result.constraint_status == "constraint_violation"
    assert result.edit_plan["actions"] == []
    assert result.edit_plan["target_files"] == []
    assert result.selected_files == []


def test_no_allow_paths_keeps_existing_behavior():
    constraints = PlanningConstraints.from_request(user_intent="")
    result = apply_planning_constraints(
        edit_plan=_sample_plan(),
        selected_files=["core/runtime/execution_gateway.py"],
        constraints=constraints,
    )

    assert "core/runtime/execution_gateway.py" in result.selected_files
    assert "core/runtime/execution_gateway.py" in result.edit_plan["target_files"]