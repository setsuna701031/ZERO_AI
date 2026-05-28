from __future__ import annotations

from core.runtime.runtime_native_autonomous_repair_chain import RuntimeNativeAutonomousRepairChain
from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_git_patch_pipeline import RuntimeNativeGitPatchPipeline
from core.runtime.runtime_native_targeted_pytest_planner import RuntimeNativeTargetedPytestPlanner


def test_runtime_native_autonomous_repair_chain_seal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)

    target = tmp_path / "core/runtime/runtime_native_repair_target.py"
    target.write_text("STATE = 'old'\n", encoding="utf-8")

    (tmp_path / "tests/test_runtime_native_repair_target_v1.py").write_text(
        "def test_repair_target():\n    assert True\n",
        encoding="utf-8",
    )

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    pytest_planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    patch = RuntimeNativeGitPatchPipeline.with_workspace(tmp_path, mutation_loop=mutation)

    chain = RuntimeNativeAutonomousRepairChain.with_workspace(
        tmp_path,
        mutation_loop=mutation,
        pytest_planner=pytest_planner,
        patch_pipeline=patch,
    )

    result = chain.run_repair_chain(
        goal="autonomous repair chain seal",
        initial_plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_repair_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_repair_target.py",
                    "content": "STATE = 'broken'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": target.read_text(encoding="utf-8") == "STATE = 'fixed'\n",
            "command": "python -m pytest tests/test_runtime_native_repair_target_v1.py -q",
            "stderr": "assert failed" if target.read_text(encoding="utf-8") != "STATE = 'fixed'\n" else "",
        },
        repair_plan_fn=lambda record, attempt: {
            "impacted_files": ["core/runtime/runtime_native_repair_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_repair_target.py",
                    "content": "STATE = 'fixed'\n",
                }
            ],
        },
        max_retries=2,
    )

    assert result.status == "finalized"
    assert result.final_result["ok"] is True
    assert len(result.attempts) == 2
    assert result.final_pytest_plan["commands"] == [
        "python -m pytest tests/test_runtime_native_repair_target_v1.py -q"
    ]
    assert target.read_text(encoding="utf-8") == "STATE = 'fixed'\n"
    assert chain.health()["counts"]["finalized"] == 1
