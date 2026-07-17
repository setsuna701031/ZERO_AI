from __future__ import annotations

from pathlib import Path

import pytest

from core.tasks.task_paths import TaskPathManager


def test_ensure_workspace_is_idempotent_with_existing_directories(tmp_path: Path) -> None:
    manager = TaskPathManager(workspace_root=str(tmp_path / "workspace"))

    manager.ensure_workspace()
    manager.ensure_workspace()

    assert Path(manager.workspace_root).is_dir()
    assert Path(manager.tasks_root).is_dir()
    assert Path(manager.shared_root).is_dir()
    assert Path(manager.runtime_root).is_dir()
    assert Path(manager.logs_root).is_dir()
    assert Path(manager.memory_root).is_dir()
    assert Path(manager.knowledge_root).is_dir()
    assert Path(manager.cache_root).is_dir()


def test_ensure_workspace_reports_file_collision(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cache_file = workspace / "cache"
    cache_file.write_text("not a directory", encoding="utf-8")

    manager = TaskPathManager(workspace_root=str(workspace))

    with pytest.raises(FileExistsError):
        manager.ensure_workspace()


def test_ensure_task_paths_is_idempotent(tmp_path: Path) -> None:
    manager = TaskPathManager(workspace_root=str(tmp_path / "workspace"))

    first = manager.ensure_task_paths("task_safe_mkdir")
    second = manager.ensure_task_paths("task_safe_mkdir")

    assert first["task_dir"] == second["task_dir"]
    assert Path(first["task_dir"]).is_dir()
    assert Path(first["sandbox_dir"]).is_dir()
