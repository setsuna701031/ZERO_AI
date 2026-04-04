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

    決策原則：
    1. 若 runtime 已經 finished -> finish
    2. 若 runtime 已經 failed/cancelled/timeout -> fail
    3. 若 plan 為空：
       - 還能 replan -> replan
       - 否則 -> fail
    4. 若所有 step 已完成 -> finish
    5. 若 step 失敗：
       - 先 retry
       - retry 不行再 replan
       - replan 也不行才 fail
    6. 若 step 成功但 runtime 還殘留 last_error：
       - 保守 continue，不要因為舊錯誤殘留又重複 replan
    7. 正常情況 -> continue
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
        plan_steps = self._load_plan(plan_file)

        current_step_index = self._as_int(runtime_state.get("current_step_index"), 0)
        steps_total = self._as_int(
            runtime_state.get("steps_total"),
            len(plan_steps),
        )
        status = self._safe_str(runtime_state.get("status")).lower()
        last_error = self._safe_str(runtime_state.get("last_error"))
        replan_count = self._as_int(runtime_state.get("replan_count"), 0)
        max_replans = self._as_int(runtime_state.get("max_replans"), 1)
        retry_count = self._as_int(runtime_state.get("retry_count"), 0)
        max_retries = self._as_int(runtime_state.get("max_retries"), 0)
        failure_type = self._safe_str(runtime_state.get("failure_type")).lower()

        step_ok = self._extract_step_ok(step_result)
        tool_result = step_result.get("result", {})
        if not isinstance(tool_result, dict):
            tool_result = {}

        tool_status = self._safe_str(tool_result.get("status")).lower()
        tool_error = self._extract_error_text(step_result)

        # -----------------------------------------------------
        # 1. terminal runtime 狀態
        # -----------------------------------------------------
        if status == "finished":
            return self._result(
                decision="finish",
                reason="runtime_state marked finished",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        if status in {"failed", "cancelled", "timeout"}:
            return self._result(
                decision="fail",
                reason=f"runtime_state already terminal: {status}",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # -----------------------------------------------------
        # 2. plan 缺失
        # -----------------------------------------------------
        if not plan_steps:
            if replan_count < max_replans:
                return self._result(
                    decision="replan",
                    reason="plan is empty",
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                )

            return self._result(
                decision="fail",
                reason="plan is empty and replan limit reached",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # -----------------------------------------------------
        # 3. 已完成所有 steps
        # -----------------------------------------------------
        if steps_total > 0 and current_step_index >= steps_total:
            return self._result(
                decision="finish",
                reason="all steps completed",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # -----------------------------------------------------
        # 4. step / tool 失敗
        #    新順序：retry -> replan -> fail
        # -----------------------------------------------------
        step_failed = (not step_ok) or (tool_status in {"failed", "error"})

        if step_failed:
            if self._should_retry(
                retry_count=retry_count,
                max_retries=max_retries,
                failure_type=failure_type,
                step_result=step_result,
                tool_result=tool_result,
            ):
                return self._result(
                    decision="retry",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                )

            if self._should_replan(
                replan_count=replan_count,
                max_replans=max_replans,
            ):
                return self._result(
                    decision="replan",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                )

            return self._result(
                decision="fail",
                reason=tool_error,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # -----------------------------------------------------
        # 5. step 成功，但 runtime 還殘留舊錯誤
        #    這裡不要再重複 replan，避免成功 step 被舊狀態干擾
        # -----------------------------------------------------
        if last_error:
            return self._result(
                decision="continue",
                reason=f"step ok but runtime still contains error: {last_error}",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
            )

        # -----------------------------------------------------
        # 6. 正常情況
        # -----------------------------------------------------
        return self._result(
            decision="continue",
            reason="continue next step",
            goal=goal,
            step=step,
            step_result=step_result,
            runtime_state=runtime_state,
        )

    # =========================================================
    # Decision helpers
    # =========================================================

    def _should_retry(
        self,
        *,
        retry_count: int,
        max_retries: int,
        failure_type: str,
        step_result: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> bool:
        if max_retries <= 0:
            return False

        if retry_count >= max_retries:
            return False

        retryable_failure_types = {
            "",
            "tool_error",
            "transient_error",
            "timeout",
            "temporary",
        }

        if failure_type not in retryable_failure_types:
            return False

        result_retryable = step_result.get("retryable")
        if isinstance(result_retryable, bool):
            return result_retryable

        tool_retryable = tool_result.get("retryable")
        if isinstance(tool_retryable, bool):
            return tool_retryable

        return True

    def _should_replan(
        self,
        *,
        replan_count: int,
        max_replans: int,
    ) -> bool:
        if max_replans <= 0:
            return False

        if replan_count >= max_replans:
            return False

        return True

    def _extract_step_ok(self, step_result: Dict[str, Any]) -> bool:
        if "ok" in step_result:
            return self._as_bool(step_result.get("ok"))

        status = self._safe_str(step_result.get("status")).lower()
        if status in {"ok", "success", "completed", "done"}:
            return True
        if status in {"failed", "error"}:
            return False

        return False

    def _extract_error_text(self, step_result: Dict[str, Any]) -> str:
        tool_result = step_result.get("result", {})
        if not isinstance(tool_result, dict):
            tool_result = {}

        return (
            self._safe_str(tool_result.get("error"))
            or self._safe_str(tool_result.get("stderr"))
            or self._safe_str(step_result.get("error"))
            or self._safe_str(step_result.get("message"))
            or "step execution failed"
        )

    # =========================================================
    # Result builder
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
            "decision": decision,  # continue / retry / replan / finish / fail
            "reason": reason,
            "goal": goal,
            "step_type": step.get("type"),
            "step_action": step.get("action") or step.get("type"),
            "current_step_index": runtime_state.get("current_step_index"),
            "steps_total": runtime_state.get("steps_total"),
            "status": runtime_state.get("status"),
            "last_error": runtime_state.get("last_error"),
            "failure_type": runtime_state.get("failure_type"),
            "retry_count": runtime_state.get("retry_count"),
            "max_retries": runtime_state.get("max_retries"),
            "replan_count": runtime_state.get("replan_count"),
            "max_replans": runtime_state.get("max_replans"),
            "step_result_ok": step_result.get("ok"),
        }

    # =========================================================
    # Helpers
    # =========================================================

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
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict) and isinstance(data.get("steps"), list):
            return [item for item in data["steps"] if isinstance(item, dict)]

        return []

    def _safe_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "ok"}
        if isinstance(value, (int, float)):
            return value != 0
        return False

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default