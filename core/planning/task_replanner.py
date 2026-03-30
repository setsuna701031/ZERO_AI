# core/task_replanner.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.planner import Planner


class TaskReplanner:
    """
    Runtime Task Replanner

    用途：
    - 給目前這套 Task OS / Scheduler / StepExecutor 使用
    - 當 step reflection 回傳 decision = replan 時
      重新生成 plan.json，並重置 runtime_state.json

    注意：
    - 這不是舊版 verification-oriented replanner
    - 舊版 replanner.py 保留
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.planner = Planner(workspace_dir=self.workspace_dir)

    # =========================================================
    # Public API
    # =========================================================

    def replan(
        self,
        *,
        goal: str,
        task_dir: str,
        plan_file: str,
        runtime_file: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        重建 plan.json，並把 runtime_state.json 重置為可重新執行狀態
        """

        steps = self.planner.build_and_save_plan(
            goal=goal,
            task_dir=task_dir,
            plan_file=plan_file,
        )

        runtime_state = self._default_runtime_state()
        runtime_state["total_steps"] = len(steps)
        runtime_state["replanned"] = True
        runtime_state["replan_reason"] = reason
        runtime_state["replan_count"] = int(self._read_old_replan_count(runtime_file)) + 1

        self._save_json(runtime_file, runtime_state)

        return {
            "ok": True,
            "replanned": True,
            "reason": reason,
            "step_count": len(steps),
            "plan_file": plan_file,
            "runtime_file": runtime_file,
            "error": None,
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _default_runtime_state(self) -> Dict[str, Any]:
        return {
            "current_step_index": 0,
            "last_finished_step": 0,
            "total_steps": 0,
            "progress_percent": 0,
            "finished": False,
            "step_history": [],
            "last_step_result": None,
            "last_error": None,
            "replanned": False,
            "replan_reason": "",
            "replan_count": 0,
        }

    def _read_old_replan_count(self, runtime_file: str) -> int:
        if not os.path.exists(runtime_file):
            return 0
        try:
            with open(runtime_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return int(data.get("replan_count", 0))
        except Exception:
            return 0
        return 0

    def _save_json(self, file_path: str, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)