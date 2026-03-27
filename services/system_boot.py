from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task_runtime import TaskRuntime
from core.workspace import Workspace
from core.tool_registry import ToolRegistry
from core.tasks.scheduler import TaskScheduler


class WorkspaceToolAdapter:
    """
    把 Workspace 包成 TaskRuntime 可用的 tool 介面。
    TaskRuntime 會呼叫 tool.execute(args_dict)
    """

    name = "workspace_tool"

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(args, dict):
            return {
                "success": False,
                "error": "args must be a dict",
            }

        action = str(args.get("action", "")).strip()
        path = str(args.get("path", "")).strip()
        content = args.get("content", "")

        if not action:
            return {
                "success": False,
                "error": "action is required",
            }

        if action == "read_file":
            return self._read_file(path)

        if action == "write_file":
            return self._write_file(path, content)

        if action == "list_files":
            return self._list_files(path)

        return {
            "success": False,
            "error": f"unknown action: {action}",
        }

    def _read_file(self, relative_path: str) -> Dict[str, Any]:
        if not relative_path:
            return {
                "success": False,
                "error": "path is required",
            }

        file_path = self.workspace_root / relative_path
        if not file_path.exists():
            return {
                "success": False,
                "error": f"file not found: {file_path}",
            }

        try:
            text = file_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "path": str(file_path),
                "content": text,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def _write_file(self, relative_path: str, content: Any) -> Dict[str, Any]:
        if not relative_path:
            return {
                "success": False,
                "error": "path is required",
            }

        file_path = self.workspace_root / relative_path

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(str(content or ""), encoding="utf-8")
            return {
                "success": True,
                "path": str(file_path),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def _list_files(self, relative_dir: str) -> Dict[str, Any]:
        target_dir = self.workspace_root if not relative_dir else (self.workspace_root / relative_dir)

        if not target_dir.exists():
            return {
                "success": False,
                "error": f"path not found: {target_dir}",
            }

        try:
            files = [
                str(p.relative_to(self.workspace_root))
                for p in target_dir.rglob("*")
                if p.is_file()
            ]
            return {
                "success": True,
                "files": files,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }


_ZERO_SYSTEM: "ZeroSystem | None" = None


def bootstrap_system(workspace_root: str = "E:/zero_ai/workspace") -> Dict[str, Any]:
    """
    每次都建立新的 boot 物件，不保留舊 cache。

    目的：
    1. 避免你改完 code 後，仍吃到舊的 tool_registry / task_runtime
    2. scheduler 每次跑 task 時，都拿到乾淨且一致的依賴
    3. health 可直接反映當下 boot 狀態
    """
    workspace_root_path = Path(workspace_root).resolve()

    workspace = Workspace(base_dir=str(workspace_root_path))

    tool_registry = ToolRegistry(
        workspace_root=str(workspace_root_path),
        project_root=str(ROOT),
    )

    workspace_tool = WorkspaceToolAdapter(workspace_root=workspace_root_path)
    tool_registry.register_tool("workspace_tool", workspace_tool)

    task_runtime = TaskRuntime(
        workspace_root=workspace_root_path,
        task_manager=workspace,
        tool_registry=tool_registry,
    )

    return {
        "workspace_root": str(workspace_root_path),
        "workspace": workspace,
        "tool_registry": tool_registry,
        "workspace_tool": workspace_tool,
        "task_runtime": task_runtime,
        "task_manager": workspace,
    }


def _normalize_runtime_result(result: Any, fallback_task_name: str) -> Dict[str, Any]:
    if isinstance(result, dict):
        data = result.get("data", {})
        task_name = str(result.get("task_name", "")).strip()

        if not task_name and isinstance(data, dict):
            task_name = str(data.get("task_name", "")).strip()

        if not task_name:
            task_name = fallback_task_name

        return {
            "success": bool(result.get("success", False)),
            "task_name": task_name,
            "summary": str(result.get("summary", "")),
            "error": str(result.get("error", "") or ""),
        }

    if isinstance(result, str):
        return {
            "success": True,
            "task_name": fallback_task_name,
            "summary": result,
            "error": "",
        }

    return {
        "success": False,
        "task_name": fallback_task_name,
        "summary": "",
        "error": "runtime returned invalid result",
    }


def scheduler_task_launcher_factory(workspace_root: str):
    def scheduler_task_launcher(goal: str, queue_task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            boot = bootstrap_system(workspace_root=workspace_root)
            task_runtime = boot["task_runtime"]
            workspace = boot["workspace"]
            tool_registry = boot["tool_registry"]

            created = workspace.create_task(task_name=goal, description=goal)
            if not isinstance(created, dict) or not created.get("ok"):
                return {
                    "success": False,
                    "task_name": "",
                    "summary": "",
                    "error": f"workspace.create_task failed: {created}",
                }

            task_id = str(created.get("task_id", "")).strip()
            if not task_id:
                return {
                    "success": False,
                    "task_name": "",
                    "summary": "",
                    "error": "workspace.create_task did not return task_id",
                }

            task_info = {
                "task_name": task_id,
                "goal": goal,
                "source_task_name": str(queue_task.get("source_task_name", "")).strip(),
                "priority": queue_task.get("priority", 100),
                "run_mode": str(queue_task.get("run_mode", "normal")).strip(),
                "task_type": str(queue_task.get("task_type", "general")).strip(),
                "metadata": queue_task.get("metadata", {}) or {},
                "queue_task": dict(queue_task),
            }

            runtime_result = task_runtime.run_task(task_info)
            normalized = _normalize_runtime_result(runtime_result, task_id)

            return {
                "success": normalized["success"],
                "task_name": normalized["task_name"],
                "summary": normalized["summary"],
                "error": normalized["error"],
                "debug": {
                    "workspace_root": str(workspace_root),
                    "registered_tools": list(tool_registry.list_tools().keys()),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "task_name": "",
                "summary": "",
                "error": str(e),
            }

    return scheduler_task_launcher


class ZeroSystem:
    def __init__(self, workspace_root: str = "E:/zero_ai/workspace") -> None:
        self.workspace_root = workspace_root
        self.boot = bootstrap_system(workspace_root=self.workspace_root)

        self.scheduler = TaskScheduler(
            workspace_root=self.workspace_root,
            task_launcher=scheduler_task_launcher_factory(self.workspace_root),
        )
        self.queue = self.scheduler.queue

    def start(self) -> Dict[str, Any]:
        return self.scheduler.start()

    def stop(self) -> Dict[str, Any]:
        return self.scheduler.stop()

    def refresh_boot(self) -> Dict[str, Any]:
        self.boot = bootstrap_system(workspace_root=self.workspace_root)
        return {
            "success": True,
            "workspace_root": self.boot.get("workspace_root"),
            "tools": list(self.boot["tool_registry"].list_tools().keys()),
        }

    def health(self) -> Dict[str, Any]:
        self.boot = bootstrap_system(workspace_root=self.workspace_root)

        data = self.scheduler.health()
        data["boot"] = {
            "workspace_root": self.boot.get("workspace_root"),
            "tools": list(self.boot["tool_registry"].list_tools().keys()),
            "task_runtime_has_registry": self.boot.get("task_runtime").tool_registry is not None,
            "task_runtime_registry_tools": list(
                getattr(self.boot.get("task_runtime").tool_registry, "list_tools", lambda: {})().keys()
            )
            if self.boot.get("task_runtime") is not None and self.boot.get("task_runtime").tool_registry is not None
            else [],
        }
        return data

    def enqueue(
        self,
        goal: str,
        priority: int = 100,
        source_task_name: str = "",
        run_mode: str = "normal",
        task_type: str = "general",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self.scheduler.enqueue(
            goal=goal,
            priority=priority,
            source_task_name=source_task_name,
            run_mode=run_mode,
            task_type=task_type,
            metadata=metadata,
        )

    def queue_list(
        self,
        status: str | None = None,
        limit: int | None = None,
    ) -> Dict[str, Any]:
        return self.scheduler.list_tasks(status=status, limit=limit)

    def queue_get(self, queue_task_id: str) -> Dict[str, Any]:
        return self.scheduler.get_task(queue_task_id)

    def queue_pause(self, queue_task_id: str) -> Dict[str, Any]:
        return self.scheduler.pause_task(queue_task_id)

    def queue_resume(self, queue_task_id: str) -> Dict[str, Any]:
        return self.scheduler.resume_task(queue_task_id)

    def queue_cancel(self, queue_task_id: str) -> Dict[str, Any]:
        return self.scheduler.cancel_task(queue_task_id)

    def queue_reprioritize(self, queue_task_id: str, priority: int) -> Dict[str, Any]:
        return self.scheduler.reprioritize(queue_task_id, priority)


def get_zero_system() -> ZeroSystem:
    global _ZERO_SYSTEM
    if _ZERO_SYSTEM is None:
        _ZERO_SYSTEM = ZeroSystem()
        _ZERO_SYSTEM.start()
    return _ZERO_SYSTEM