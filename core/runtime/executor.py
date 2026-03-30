from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json


class Executor:
    """
    Executor
    負責執行 Planner 產生的 Plan
    """

    def __init__(self, workspace_root: Path | str = "workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # Public
    # =========================================================

    def execute_plan(
        self,
        task_name: str,
        plan: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """
        執行整個 Plan
        """
        steps: List[Dict[str, Any]] = plan.get("steps", [])
        results: List[Dict[str, Any]] = []

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        for index, step in enumerate(steps, start=1):
            result = self._execute_step(task_name, index, step)
            results.append(result)

        return {
            "task_name": task_name,
            "iteration": iteration,
            "results": results,
            "success": True,
        }

    # =========================================================
    # Internal
    # =========================================================

    def _execute_step(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        模擬執行步驟（之後會接 Tool）
        """
        step_result = {
            "step": step_index,
            "action": step.get("action"),
            "status": "done",
            "output": f"Executed step {step_index}",
        }

        # 存 step 結果
        task_dir = self.workspace_root / task_name
        step_file = task_dir / f"step_{step_index:02d}.json"

        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(step_result, f, indent=2, ensure_ascii=False)

        return step_result