from __future__ import annotations

from typing import Any, Dict, List, Optional


class AgentState:
    """
    ZERO Agent State

    用來記錄：
    - 當前任務
    - 計畫
    - 已完成步驟
    - 失敗步驟
    - 上一步結果
    - 變數 / context
    """

    def __init__(self) -> None:
        self.reset()

    # =========================
    # Core State
    # =========================

    def reset(self) -> None:
        self.current_task_id: Optional[str] = None
        self.current_plan: Optional[Dict[str, Any]] = None
        self.completed_steps: List[Dict[str, Any]] = []
        self.failed_steps: List[Dict[str, Any]] = []
        self.last_result: Optional[Dict[str, Any]] = None
        self.variables: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {}

    # =========================
    # Task / Plan
    # =========================

    def set_task(self, task_id: Optional[str]) -> None:
        self.current_task_id = task_id

    def set_plan(self, plan: Dict[str, Any]) -> None:
        self.current_plan = plan
        self.completed_steps = []
        self.failed_steps = []

    # =========================
    # Steps
    # =========================

    def add_completed_step(self, step_result: Dict[str, Any]) -> None:
        self.completed_steps.append(step_result)
        self.last_result = step_result

    def add_failed_step(self, step_result: Dict[str, Any]) -> None:
        self.failed_steps.append(step_result)
        self.last_result = step_result

    # =========================
    # Variables / Context
    # =========================

    def set_var(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get_var(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def set_context(self, key: str, value: Any) -> None:
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    # =========================
    # Export
    # =========================

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_task_id": self.current_task_id,
            "completed_steps": len(self.completed_steps),
            "failed_steps": len(self.failed_steps),
            "variables": self.variables,
            "context": self.context,
        }