from __future__ import annotations

from typing import Any, Dict, List, Optional


class Verifier:
    """
    ZERO Verifier / Correction Core

    目前職責：
    1. 檢查 execute_plan 的整體結果
    2. 檢查每個 step result 是否成功
    3. 產出 correction decision
    4. 寫入 verifier / correction trace

    目前先做最小可用版：
    - done / success 視為成功
    - error / failed / fail 視為失敗
    - 如果有任一步失敗，回傳 needs_correction=True
    """

    SUCCESS_STATUSES = {"done", "success", "ok", "passed"}
    FAILURE_STATUSES = {"error", "failed", "fail", "exception"}

    def __init__(self, trace_logger: Optional[Any] = None, debug: bool = False) -> None:
        self.trace_logger = trace_logger
        self.debug = debug

    # =========================================================
    # public
    # =========================================================

    def verify_execution_result(
        self,
        task_name: str,
        execution_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        驗證整個 execution 結果，並做 correction 決策。
        """
        results: List[Dict[str, Any]] = execution_result.get("results", []) or []

        if self.trace_logger is not None:
            self.trace_logger.log_verifier(
                title="verify execution result start",
                message=f"task={task_name}, step_count={len(results)}",
                source="verifier",
                raw={
                    "task_name": task_name,
                    "execution_result": execution_result,
                },
            )

        step_checks: List[Dict[str, Any]] = []
        failed_steps: List[Dict[str, Any]] = []

        for step_result in results:
            check = self.verify_step_result(task_name=task_name, step_result=step_result)
            step_checks.append(check)

            if not check.get("passed", False):
                failed_steps.append(check)

        passed = len(failed_steps) == 0

        if passed:
            correction = {
                "needs_correction": False,
                "action": "pass",
                "reason": "all_steps_passed",
                "failed_steps": [],
            }

            if self.trace_logger is not None:
                self.trace_logger.log_correction(
                    title="correction decision",
                    message="pass",
                    status="success",
                    source="correction",
                    raw=correction,
                )

        else:
            correction = {
                "needs_correction": True,
                "action": "review_failed_steps",
                "reason": "step_failure_detected",
                "failed_steps": failed_steps,
            }

            if self.trace_logger is not None:
                self.trace_logger.log_correction(
                    title="correction decision",
                    message=f"failed_steps={len(failed_steps)}",
                    status="needs_correction",
                    source="correction",
                    raw=correction,
                )

        verify_result = {
            "task_name": task_name,
            "passed": passed,
            "step_checks": step_checks,
            "failed_steps": failed_steps,
            "correction": correction,
        }

        if self.trace_logger is not None:
            self.trace_logger.log_verifier(
                title="verify execution result end",
                message=f"passed={passed}",
                status="success" if passed else "failed",
                source="verifier",
                raw=verify_result,
            )

        return verify_result

    def verify_step_result(
        self,
        task_name: str,
        step_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        檢查單一步驟結果。
        """
        step_index = step_result.get("step")
        action = step_result.get("action")
        status = str(step_result.get("status", "") or "").strip().lower()
        output = step_result.get("output")

        passed = self._is_step_success(step_result)

        check = {
            "step": step_index,
            "action": action,
            "status": status,
            "passed": passed,
            "reason": self._build_step_reason(status=status, output=output, passed=passed),
            "step_result": step_result,
        }

        if self.trace_logger is not None:
            self.trace_logger.log_verifier(
                step_id=self._build_step_id(step_index),
                title="verify step result",
                message=f"step={step_index}, passed={passed}, status={status}",
                status="passed" if passed else "failed",
                source="verifier",
                raw={
                    "task_name": task_name,
                    "check": check,
                },
            )

        if not passed and self.trace_logger is not None:
            self.trace_logger.log_correction(
                step_id=self._build_step_id(step_index),
                title="step needs correction",
                message=f"step={step_index}, action={action}",
                status="needs_correction",
                source="correction",
                raw={
                    "task_name": task_name,
                    "step_result": step_result,
                    "reason": check["reason"],
                },
            )

        return check

    # =========================================================
    # internal
    # =========================================================

    def _is_step_success(self, step_result: Dict[str, Any]) -> bool:
        status = str(step_result.get("status", "") or "").strip().lower()

        if status in self.SUCCESS_STATUSES:
            return True

        if status in self.FAILURE_STATUSES:
            return False

        success_flag = step_result.get("success")
        if isinstance(success_flag, bool):
            return success_flag

        return False

    def _build_step_reason(self, status: str, output: Any, passed: bool) -> str:
        if passed:
            return f"status={status or 'unknown'} treated as success"

        if not status:
            return "missing status and no explicit success flag"

        if output in (None, ""):
            return f"status={status} treated as failure"

        return f"status={status}, output={output}"

    def _build_step_id(self, step_index: Any) -> str:
        if step_index is None:
            return ""
        try:
            return f"step_{int(step_index):02d}"
        except Exception:
            return f"step_{step_index}"