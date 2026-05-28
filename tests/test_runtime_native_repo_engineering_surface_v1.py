from __future__ import annotations

from core.runtime.runtime_native_repo_engineering_surface import (
    RuntimeNativeRepoEngineeringSurface,
)


def build_repo(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)

    (tmp_path / "core/runtime/runtime_native_scheduler.py").write_text(
        "class RuntimeNativeScheduler:\n    pass\n",
        encoding="utf-8",
    )

    (tmp_path / "core/runtime/runtime_native_execution_dispatch.py").write_text(
        "class RuntimeNativeExecutionDispatch:\n    pass\n",
        encoding="utf-8",
    )

    (tmp_path / "core/runtime/runtime_native_code_mutation_loop.py").write_text(
        "class RuntimeNativeCodeMutationLoop:\n    pass\n",
        encoding="utf-8",
    )

    (tmp_path / "tests/test_runtime_native_scheduler_v1.py").write_text(
        "def test_scheduler():\n    assert True\n",
        encoding="utf-8",
    )


def test_repo_scan_and_impacted_analysis(tmp_path):
    build_repo(tmp_path)

    surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)

    scanned = surface.scan_repository()

    assert "core/runtime/runtime_native_scheduler.py" in scanned
    assert "core/runtime/runtime_native_code_mutation_loop.py" in scanned

    impacted = surface.impacted_file_analysis(
        goal="runtime mutation scheduler dispatch",
        keywords=["mutation", "dispatch"],
    )

    assert any("mutation" in item for item in impacted)
    assert any("dispatch" in item for item in impacted)


def test_targeted_test_plan(tmp_path):
    build_repo(tmp_path)

    surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)

    targets = surface.targeted_test_plan(
        impacted_files=[
            "core/runtime/runtime_native_scheduler.py",
            "core/runtime/runtime_native_execution_dispatch.py",
        ]
    )

    assert "tests/test_runtime_native_scheduler_v1.py" in targets
    assert "tests/test_runtime_native_scheduler_seal_v1.py" in targets


def test_engineering_task_surface(tmp_path):
    build_repo(tmp_path)

    surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)
    surface.scan_repository()

    task = surface.create_engineering_task(
        goal="runtime-native mutation dispatch engineering task",
        keywords=["mutation", "dispatch"],
    )

    assert task.status == "planned"
    assert len(task.impacted_files) >= 1
    assert len(task.test_targets) >= 1

    summary = surface.engineering_summary()

    assert summary["engineering_tasks"] == 1
