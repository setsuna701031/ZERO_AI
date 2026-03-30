from __future__ import annotations

from pathlib import Path
from typing import Union


class PathManager:
    """
    ZERO Path Manager v1

    職責：
    1. 系統唯一的路徑管理器
    2. 統一 workspace root
    3. 清洗與正規化路徑
    4. 防止 workspace/workspace 重複
    5. 防止路徑跳脫 workspace
    6. 提供 task_xxxx 相關路徑解析

    規則：
    - Planner 不可以碰 workspace
    - AgentLoop 不處理 path
    - Tool 不自行組 workspace path
    - Workspace 只處理 task_id / task 內部結構
    - 只有 PathManager 知道 workspace root 在哪
    """

    def __init__(
        self,
        base_dir: Union[str, Path, None] = None,
        workspace_dir_name: str = "workspace"
    ) -> None:
        if base_dir is None or str(base_dir).strip() == "":
            root = Path.cwd()
        else:
            root = Path(base_dir).resolve()

        # 如果傳進來的已經是 .../workspace，就不要再加一層 workspace
        if root.name == workspace_dir_name:
            self.workspace_root = root
        else:
            self.workspace_root = root / workspace_dir_name

        self.workspace_root.mkdir(parents=True, exist_ok=True)

    # =========================
    # Public API
    # =========================

    def clean_path(self, path: str) -> str:
        """
        清理路徑字串，但不回傳絕對路徑。

        例如：
        - workspace/task_0001/plan.txt -> task_0001/plan.txt
        - /workspace/task_0001/plan.txt -> task_0001/plan.txt
        - \\workspace\\task_0001\\plan.txt -> task_0001/plan.txt
        """
        if not isinstance(path, str):
            path = str(path or "")

        path = path.strip()
        if path == "":
            return ""

        path = path.replace("\\", "/")

        # 去掉開頭的 /
        while path.startswith("/"):
            path = path[1:]

        # 去掉重複的 workspace/
        while path.startswith("workspace/"):
            path = path[len("workspace/"):]

        # 去掉重複斜線
        while "//" in path:
            path = path.replace("//", "/")

        # 去掉開頭的 ./
        while path.startswith("./"):
            path = path[2:]

        return path

    def to_workspace_path(self, path: str = "") -> Path:
        """
        將相對 workspace 路徑轉成 workspace 內部的絕對 Path。
        會自動清洗並檢查是否跳脫 workspace。
        """
        clean = self.clean_path(path)

        if clean == "":
            target = self.workspace_root
        else:
            target = (self.workspace_root / clean).resolve()

        self._assert_within_workspace(target)
        return target

    def ensure_dir(self, path: str = "") -> Path:
        """
        確保目錄存在，回傳絕對 Path。
        """
        full = self.to_workspace_path(path)
        full.mkdir(parents=True, exist_ok=True)
        return full

    def normalize_task_id(self, task_id: str) -> str:
        """
        統一 task_id 格式：
        - 0001 -> task_0001
        - task_0001 -> task_0001
        """
        raw = str(task_id or "").strip()
        if raw == "":
            raise ValueError("task_id cannot be empty.")

        if raw.startswith("task_"):
            return raw

        return f"task_{raw}"

    def task_path(self, task_id: str) -> Path:
        """
        回傳 task 目錄絕對路徑，不重複建立 task_ 前綴。
        """
        normalized_task_id = self.normalize_task_id(task_id)
        return self.to_workspace_path(normalized_task_id)

    def ensure_task_dir(self, task_id: str) -> Path:
        """
        確保 task 目錄存在。
        """
        task_dir = self.task_path(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def task_file(self, task_id: str, relative_path: str) -> Path:
        """
        取得 task 內部檔案絕對路徑。

        範例：
        task_file("task_0001", "plan.txt")
        -> .../workspace/task_0001/plan.txt
        """
        normalized_task_id = self.normalize_task_id(task_id)
        clean_relative = self.clean_path(relative_path)

        if clean_relative == "":
            raise ValueError("relative_path cannot be empty.")

        full = (self.workspace_root / normalized_task_id / clean_relative).resolve()
        self._assert_within_workspace(full)
        return full

    def task_subdir(self, task_id: str, subdir_name: str) -> Path:
        """
        取得 task 子資料夾絕對路徑。
        """
        normalized_task_id = self.normalize_task_id(task_id)
        clean_subdir = self.clean_path(subdir_name)

        if clean_subdir == "":
            raise ValueError("subdir_name cannot be empty.")

        full = (self.workspace_root / normalized_task_id / clean_subdir).resolve()
        self._assert_within_workspace(full)
        return full

    # =========================
    # Internal Helpers
    # =========================

    def _assert_within_workspace(self, target: Path) -> None:
        """
        防止路徑跳脫 workspace。
        """
        workspace_root_resolved = self.workspace_root.resolve()

        try:
            target.relative_to(workspace_root_resolved)
        except ValueError as exc:
            raise ValueError(
                f"Path escapes workspace: {target}"
            ) from exc