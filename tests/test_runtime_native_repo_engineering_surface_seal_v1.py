from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_repo_engineering_surface import RuntimeNativeRepoEngineeringSurface
import pytest

pytestmark = [pytest.mark.contract]




def test_runtime_native_repo_engineering_surface_seal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)

    (tmp_path / "core/runtime/runtime_native_scheduler.py").write_text(
        "class RuntimeNativeScheduler:\n    pass\n",
        encoding="utf-8",
    )

    (tmp_path / "core/runtime/runtime_native_code_mutation_loop.py").write_text(
        "class RuntimeNativeCodeMutationLoop:\n    pass\n",
        encoding="utf-8",
    )

    surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)

    scanned = surface.scan_repository()

    assert len(scanned) >= 2

    task = surface.create_engineering_task(
        goal="codex-like runtime-native engineering mutation task",
        keywords=["mutation", "runtime"],
    )

    assert task.status == "planned"
    assert len(task.impacted_files) >= 1
    assert len(task.test_targets) >= 1

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    result = mutation.run_mutation(
        goal="runtime-native engineering repo mutation",
        plan_fn=lambda goal, context: {
            "impacted_files": task.impacted_files,
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/generated_runtime_surface.py",
                    "content": "RUNTIME_NATIVE_ENGINEERING_SURFACE = True\n",
                }
            ],
        },
    )

    assert result.status == "finalized"
    assert (tmp_path / "core/runtime/generated_runtime_surface.py").exists()
