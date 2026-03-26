from __future__ import annotations

from typing import Any, Dict, Optional

from core.step_executor import DummyStepExecutor
from core.tool_registry import ToolRegistry


class TaskStepExecutorAdapter:
    """
    把 AgentLoop 的 task executor 介面
    轉接到 StepExecutor + ToolRegistry
    """

    def __init__(
        self,
        step_executor: DummyStepExecutor,
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
        """
        AgentLoop 會呼叫這個
        """

        step = self._task_to_step(task)

        result = self.step_executor.execute(step, workspace=self.workspace)

        if not result.get("ok"):
            raise RuntimeError(result.get("message", "step execution failed"))

        message = result.get("message") or "step completed"
        return message

    # ------------------------------------------------------------------
    # task -> step
    # ------------------------------------------------------------------
    def _task_to_step(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        先做最簡單 mapping
        未來可以接 LLM step planner
        """

        title = task.get("title", "")
        task_id = task.get("id", "")

        # 目前先全部當作 workspace demo 動作
        # 之後可以根據 title 解析 action
        return {
            "id": task_id,
            "title": title,
            "index": task.get("meta", {}).get("step_index", 0),
            "tool": "workspace",
            "input": {
                "action": "mkdir",
                "path": "demo_ok",
            },
        }