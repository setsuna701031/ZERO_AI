# core/step_reflection_engine.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List


class StepReflectionEngine:
    """
    Step-level Reflection Engine

    作用：
    - 在每個 step 執行後做即時判斷
    - 決定下一步要 continue / retry / replan / finish / fail

    注意：
    - 這不是舊版 lesson reflection
    - 舊版 reflection_engine.py 保留做「任務完成後的總結」
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)

    # =========================================================
    # Public API
    # =========================================================

    def reflect(
        self,
        *,
        goal: str,
        step: Dict[str, Any],
        step_result: Dict[str, Any],
        runtime_state_file: str,
        plan_file: str,
        log_file: str,
    ) -> Dict[str, Any]:
        runtime_state = self._load_json(runtime_state_file)
        plan = self._load_plan(plan_file)

        current_step_index = int(runtime_state.get("current_step_index", 0))
        total_steps = int(runtime_state.get("total_steps", 0))
        finished = bool(runtime_state.get("finished", False))
        last_error = runtime_state.get("last_error")

        decision = "continue"
        reason = "continue next step"

        # 1. step 本身失敗
        if not bool(step_result.get("ok", False)):
            decision = "retry"
            reason = step_result.get("error") or "step execution failed"
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        tool_result = step_result.get("result", {})
        if not isinstance(tool_result, dict):
            tool_result = {}

        # 2. 工具層回傳失敗
        tool_status = str(tool_result.get("status", "")).strip().lower()
        if tool_status in {"failed", "error"}:
            decision = "retry"
            reason = str(tool_result.get("error", "tool returned failed status"))
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # 3. runtime state 顯示任務已完成
        if finished:
            decision = "finish"
            reason = "runtime_state marked task finished"
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # 4. plan 不存在或為空
        if not plan:
            decision = "replan"
            reason = "plan is empty"
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # 5. 已跑完全部 step
        if total_steps > 0 and current_step_index >= total_steps:
            decision = "finish"
            reason = "all steps completed"
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # 6. last_error 還存在，代表 runtime 沒清乾淨
        if last_error:
            decision = "retry"
            reason = f"runtime still contains error: {last_error}"
            return self._result(
                decision=decision,
                reason=reason,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # 7. 一般正常情況
        return self._result(
            decision=decision,
            reason=reason,
            goal=goal,
            step=step,
            step_result=step_result,
            runtime_state=runtime_state,
        )

    # =========================================================
    # Helpers
    # =========================================================

    def _result(
        self,
        *,
        decision: str,
        reason: str,
        goal: str,
        step: Dict[str, Any],
        step_result: Dict[str, Any],
        runtime_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "decision": decision,   # continue / retry / replan / finish / fail
            "reason": reason,
            "goal": goal,
            "step_action": step.get("action"),
            "current_step_index": runtime_state.get("current_step_index"),
            "last_finished_step": runtime_state.get("last_finished_step"),
            "total_steps": runtime_state.get("total_steps"),
            "progress_percent": runtime_state.get("progress_percent"),
            "finished": runtime_state.get("finished"),
            "last_error": runtime_state.get("last_error"),
            "step_result_ok": step_result.get("ok"),
        }

    def _load_json(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _load_plan(self, file_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(file_path):
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        if isinstance(data, list):
            return data

        if isinstance(data, dict) and isinstance(data.get("steps"), list):
            return data["steps"]

        return []