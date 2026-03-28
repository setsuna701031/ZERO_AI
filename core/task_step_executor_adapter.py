from __future__ import annotations

from typing import Any, Dict, Optional

from core.step_executor import StepExecutor
from core.tool_registry import ToolRegistry


class TaskStepExecutorAdapter:
    """
    Task → Step → StepExecutor
    """

    def __init__(
        self,
        step_executor: StepExecutor,
        tool_registry: ToolRegistry,
        workspace: str = "workspace",
    ) -> None:
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace = workspace

    def execute_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        step = self._task_to_step(task)

        result = self.step_executor.execute(step, workspace=self.workspace)

        if not result.get("ok"):
            raise RuntimeError(result.get("message", "step execution failed"))

        return result.get("message", "step completed")

    def _task_to_step(self, task: Dict[str, Any]) -> Dict[str, Any]:
        title = task.get("title", "")
        task_id = task.get("id", "")

        return {
            "id": task_id,
            "title": title,
            "kind": "tool",
            "tool": "workspace",
            "input": {
                "action": "mkdir",
                "path": "demo_ok",
            },
            "retry": 1,
        }