from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_git_patch_pipeline import RuntimeNativeGitPatchPipeline
from core.runtime.runtime_native_targeted_pytest_planner import RuntimeNativeTargetedPytestPlanner


def build_repo(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)

    (tmp_path / "core/runtime/runtime_native_scheduler.py").write_text(
        "class RuntimeNativeScheduler:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_runtime_native_scheduler_v1.py").write_text(
        "def test_scheduler():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_runtime_native_scheduler_seal_v1.py").write_text(
        "def test_scheduler_seal():\n    assert True\n",
        encoding="utf-8",
    )


def test_pytest_planner_maps_impacted_runtime_file(tmp_path):
    build_repo(tmp_path)

    planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)

    plan = planner.plan_for_impacted_files(
        impacted_files=["core/runtime/runtime_native_scheduler.py"],
        keywords=["scheduler"],
    )

    assert plan.commands == [
        "python -m pytest tests/test_runtime_native_scheduler_v1.py -q",
        "python -m pytest tests/test_runtime_native_scheduler_seal_v1.py -q",
    ]
    assert len(plan.targets) >= 2
    assert plan.targets[0].exists is True


def test_pytest_planner_from_mutation_record(tmp_path):
    build_repo(tmp_path)

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    result = mutation.run_mutation(
        goal="update scheduler",
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_scheduler.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_scheduler.py",
                    "content": "class RuntimeNativeScheduler:\n    value = 1\n",
                }
            ],
        },
    )

    planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    plan = planner.plan_for_mutation_record(result, keywords=["scheduler"])

    assert "python -m pytest tests/test_runtime_native_scheduler_v1.py -q" in plan.commands
    assert plan.metadata["mutation_id"] == result.mutation_id


def test_pytest_planner_from_patch_record(tmp_path):
    build_repo(tmp_path)

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    patch = RuntimeNativeGitPatchPipeline.with_workspace(
        tmp_path,
        mutation_loop=mutation,
    )

    patch_record = patch.run_mutation_with_patch(
        target_files=["core/runtime/runtime_native_scheduler.py"],
        mutation_goal="patch scheduler",
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_scheduler.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_scheduler.py",
                    "content": "class RuntimeNativeScheduler:\n    value = 2\n",
                }
            ],
        },
    )

    planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    plan = planner.plan_for_patch_record(patch_record, keywords=["scheduler"])

    assert plan.metadata["patch_id"] == patch_record.patch_id
    assert "python -m pytest tests/test_runtime_native_scheduler_v1.py -q" in plan.commands


def test_pytest_planner_persists(tmp_path):
    build_repo(tmp_path)

    planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    plan = planner.plan_for_impacted_files(
        impacted_files=["core/runtime/runtime_native_scheduler.py"],
    )

    reloaded = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)

    assert reloaded.get_plan(plan.plan_id).plan_id == plan.plan_id
