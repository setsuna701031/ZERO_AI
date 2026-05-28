from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_git_patch_pipeline import RuntimeNativeGitPatchPipeline


def test_git_patch_pipeline_captures_diff(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    pipeline = RuntimeNativeGitPatchPipeline.with_workspace(tmp_path)

    record = pipeline.create_patch(target_files=["app.py"])
    pipeline.snapshot_before(record.patch_id)

    target.write_text("VALUE = 2\n", encoding="utf-8")

    diffed = pipeline.snapshot_after_and_diff(record.patch_id)

    assert diffed.status == "diffed"
    assert len(diffed.diffs) == 1
    assert "-VALUE = 1" in diffed.diffs[0].diff
    assert "+VALUE = 2" in diffed.diffs[0].diff


def test_git_patch_pipeline_rollback(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("OLD = True\n", encoding="utf-8")

    pipeline = RuntimeNativeGitPatchPipeline.with_workspace(tmp_path)

    record = pipeline.create_patch(target_files=["app.py"])
    pipeline.snapshot_before(record.patch_id)

    target.write_text("OLD = False\n", encoding="utf-8")

    pipeline.snapshot_after_and_diff(record.patch_id)
    rolled = pipeline.rollback_patch(record.patch_id)

    assert rolled.status == "rolled_back"
    assert target.read_text(encoding="utf-8") == "OLD = True\n"


def test_git_patch_pipeline_runs_mutation_with_patch(tmp_path):
    target = tmp_path / "core/runtime/target.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    pipeline = RuntimeNativeGitPatchPipeline.with_workspace(
        tmp_path,
        mutation_loop=mutation,
    )

    result = pipeline.run_mutation_with_patch(
        target_files=["core/runtime/target.py"],
        mutation_goal="patch target",
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/target.py",
                    "content": "VALUE = 'new'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": target.read_text(encoding="utf-8") == "VALUE = 'new'\n",
            "command": "target verify",
        },
    )

    assert result.status == "finalized"
    assert result.mutation_ref["status"] == "finalized"
    assert len(result.diffs) == 1
    assert "+VALUE = 'new'" in result.diffs[0].diff


def test_git_patch_pipeline_persists(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("A = 1\n", encoding="utf-8")

    pipeline = RuntimeNativeGitPatchPipeline.with_workspace(tmp_path)
    record = pipeline.create_patch(target_files=["app.py"])
    pipeline.snapshot_before(record.patch_id)

    reloaded = RuntimeNativeGitPatchPipeline.with_workspace(tmp_path)

    assert reloaded.get_patch(record.patch_id).patch_id == record.patch_id
