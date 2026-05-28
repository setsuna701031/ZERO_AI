from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_engineering_session import RuntimeNativeEngineeringSession
from core.runtime.runtime_native_git_patch_pipeline import RuntimeNativeGitPatchPipeline
from core.runtime.runtime_native_repo_engineering_surface import RuntimeNativeRepoEngineeringSurface


def test_runtime_native_git_patch_pipeline_seal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "core/runtime/runtime_native_patch_target.py"
    target.write_text("STATE = 'before'\n", encoding="utf-8")

    repo = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)
    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    session = RuntimeNativeEngineeringSession.with_workspace(
        tmp_path,
        repo_surface=repo,
        mutation_loop=mutation,
    )
    pipeline = RuntimeNativeGitPatchPipeline.with_workspace(
        tmp_path,
        mutation_loop=mutation,
        engineering_session=session,
    )

    result = pipeline.run_mutation_with_patch(
        target_files=["core/runtime/runtime_native_patch_target.py"],
        mutation_goal="codex-like patch pipeline seal",
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_patch_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_patch_target.py",
                    "content": "STATE = 'after'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": target.read_text(encoding="utf-8") == "STATE = 'after'\n",
            "command": "targeted patch verification",
        },
    )

    assert result.status == "finalized"
    assert result.mutation_ref["status"] == "finalized"
    assert result.before_snapshots["core/runtime/runtime_native_patch_target.py"].content == "STATE = 'before'\n"
    assert result.after_snapshots["core/runtime/runtime_native_patch_target.py"].content == "STATE = 'after'\n"
    assert "-STATE = 'before'" in result.diffs[0].diff
    assert "+STATE = 'after'" in result.diffs[0].diff
    assert pipeline.health()["counts"]["finalized"] == 1

    pipeline.rollback_patch(result.patch_id)

    assert target.read_text(encoding="utf-8") == "STATE = 'before'\n"
