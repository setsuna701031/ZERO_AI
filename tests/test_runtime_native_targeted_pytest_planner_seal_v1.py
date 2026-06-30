from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_git_patch_pipeline import RuntimeNativeGitPatchPipeline
from core.runtime.runtime_native_targeted_pytest_planner import RuntimeNativeTargetedPytestPlanner
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_runtime_native_targeted_pytest_planner_seal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)

    target = tmp_path / "core/runtime/runtime_native_pytest_target.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    (tmp_path / "tests/test_runtime_native_pytest_target_v1.py").write_text(
        "def test_target():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_runtime_native_pytest_target_seal_v1.py").write_text(
        "def test_target_seal():\n    assert True\n",
        encoding="utf-8",
    )

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    patch = RuntimeNativeGitPatchPipeline.with_workspace(
        tmp_path,
        mutation_loop=mutation,
    )

    patch_record = patch.run_mutation_with_patch(
        target_files=["core/runtime/runtime_native_pytest_target.py"],
        mutation_goal="targeted pytest seal",
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_pytest_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_pytest_target.py",
                    "content": "VALUE = 'new'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": target.read_text(encoding="utf-8") == "VALUE = 'new'\n",
            "command": "target content verify",
        },
    )

    planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    plan = planner.plan_for_patch_record(
        patch_record,
        keywords=["pytest", "target"],
    )

    assert patch_record.status == "finalized"
    assert len(plan.commands) == 2
    assert "python -m pytest tests/test_runtime_native_pytest_target_v1.py -q" in plan.commands
    assert "python -m pytest tests/test_runtime_native_pytest_target_seal_v1.py -q" in plan.commands
    assert plan.fallback_commands
    assert planner.health()["plans"] == 1
