from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from core.tools.fix_engine import FixEngine


class Replanner:
    """
    Replanner（接 fix_engine 版本）

    職責：
    1. 從 task 的 results / execution_log 找出最後一個失敗 step
    2. 檢查 replan 次數是否超限
    3. 呼叫 fix_engine 產生修復後的 recovery steps
    4. 封裝成 scheduler 可使用的 replan result

    這一版重點：
    - 保留你現在可用的結構
    - 補強 summary / meta，讓多輪修復更容易追蹤
    - 每次 replan 都會明確標出 error_type / repair_mode / failed_error
    - 修正 verify fallback：不再只回傳 verify 本身
    - 對 write_file / read_file / run_python → verify 這類流程，會盡量補回必要上下文
    """

    def __init__(
        self,
        llm_client: Any = None,
        fix_engine: Optional[FixEngine] = None,
    ) -> None:
        self.llm_client = llm_client
        self.fix_engine = fix_engine if fix_engine is not None else FixEngine()

    # ------------------------------------------------------------
    # public API
    # ------------------------------------------------------------

    def create_replan_for_task(
        self,
        task: Dict[str, Any],
        user_input: str = "",
    ) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return self._fail("invalid task payload")

        original_steps = task.get("steps", [])
        if not isinstance(original_steps, list):
            original_steps = []

        max_replans = self._safe_int(task.get("max_replans", 1), default=1)
        current_replan_count = self._safe_int(task.get("replan_count", 0), default=0)
        next_replan_count = current_replan_count + 1

        if next_replan_count > max_replans:
            return {
                "ok": True,
                "replanned": False,
                "summary": f"Replan limit reached ({current_replan_count}/{max_replans}).",
                "plan": {
                    "task": "no_replan_needed",
                    "mode": "plan",
                    "summary": f"Replan limit reached ({current_replan_count}/{max_replans}).",
                    "steps": [],
                    "meta": {
                        "source": "replanner",
                        "step_count": 0,
                        "failed_step_count": 0,
                        "next_replan_count": current_replan_count,
                        "current_replan_count": current_replan_count,
                        "max_replans": max_replans,
                        "reason": "replan_limit_reached",
                        "repair_mode": "none",
                        "error_type": "REPLAN_LIMIT_REACHED",
                    },
                },
            }

        failure_info = self._extract_failure_info(task)
        failed_step = failure_info.get("failed_step")
        failed_error = str(failure_info.get("failed_error") or "")
        failed_step_index = self._safe_int(
            failure_info.get("failed_step_index", -1),
            default=-1,
        )

        if not isinstance(failed_step, dict):
            return self._fail("failed step not found")

        failed_step_type = str(failed_step.get("type") or "").strip().lower()
        parsed_error = self.fix_engine.parse_error(failed_error)
        error_type = self.fix_engine.classify_error(
            error_info=parsed_error,
            failed_step=copy.deepcopy(failed_step),
        )

        repaired_steps = self.fix_engine.build_fix_plan(
            task=copy.deepcopy(task),
            failed_step=copy.deepcopy(failed_step),
            error=failed_error,
            original_steps=copy.deepcopy(original_steps),
        )

        if not isinstance(repaired_steps, list) or not repaired_steps:
            fallback_steps = self._build_basic_retry_steps(
                original_steps=original_steps,
                failed_step=failed_step,
                failed_step_index=failed_step_index,
            )

            if not fallback_steps:
                return self._fail(
                    summary="no recovery plan could be generated",
                    error_type=error_type,
                    failed_step_type=failed_step_type,
                    failed_error=failed_error,
                    next_replan_count=next_replan_count,
                    max_replans=max_replans,
                )

            return {
                "ok": True,
                "replanned": True,
                "summary": self._build_summary(
                    error_type=error_type,
                    repair_mode="fallback_retry_only",
                    failed_step_type=failed_step_type,
                    next_replan_count=next_replan_count,
                    max_replans=max_replans,
                ),
                "replan_count": next_replan_count,
                "plan": {
                    "task": "task_recovery_plan",
                    "mode": "plan",
                    "summary": "Fallback recovery plan generated after scheduler step failure.",
                    "steps": fallback_steps,
                    "meta": {
                        "source": "replanner",
                        "step_count": len(fallback_steps),
                        "failed_step_count": 1,
                        "failed_step_index": failed_step_index,
                        "failed_step_type": failed_step_type,
                        "failed_error": failed_error,
                        "error_type": error_type,
                        "repair_mode": "fallback_retry_only",
                        "next_replan_count": next_replan_count,
                        "current_replan_count": current_replan_count,
                        "max_replans": max_replans,
                        "user_input": str(user_input or ""),
                    },
                },
            }

        repair_mode = self._infer_repair_mode(
            original_steps=original_steps,
            repaired_steps=repaired_steps,
            failed_step=failed_step,
        )

        return {
            "ok": True,
            "replanned": True,
            "summary": self._build_summary(
                error_type=error_type,
                repair_mode=repair_mode,
                failed_step_type=failed_step_type,
                next_replan_count=next_replan_count,
                max_replans=max_replans,
            ),
            "replan_count": next_replan_count,
            "plan": {
                "task": "task_recovery_plan",
                "mode": "plan",
                "summary": "Task recovery plan generated after scheduler step failure.",
                "steps": copy.deepcopy(repaired_steps),
                "meta": {
                    "source": "replanner",
                    "step_count": len(repaired_steps),
                    "failed_step_count": 1,
                    "failed_step_index": failed_step_index,
                    "failed_step_type": failed_step_type,
                    "failed_error": failed_error,
                    "error_type": error_type,
                    "repair_mode": repair_mode,
                    "next_replan_count": next_replan_count,
                    "current_replan_count": current_replan_count,
                    "max_replans": max_replans,
                    "user_input": str(user_input or ""),
                },
            },
        }

    # ------------------------------------------------------------
    # failure extraction
    # ------------------------------------------------------------

    def _extract_failure_info(self, task: Dict[str, Any]) -> Dict[str, Any]:
        results = task.get("results", [])
        if not isinstance(results, list):
            results = []

        execution_log = task.get("execution_log", [])
        if not isinstance(execution_log, list):
            execution_log = []

        failed_step = None
        failed_error = ""
        failed_step_index = -1

        for item in reversed(results):
            if not isinstance(item, dict):
                continue
            if bool(item.get("ok")):
                continue

            failed_step = copy.deepcopy(item.get("step"))
            failed_error = str(item.get("error") or "")
            failed_step_index = self._safe_int(item.get("step_index", -1), default=-1)
            break

        if failed_step is None:
            for item in reversed(execution_log):
                if not isinstance(item, dict):
                    continue
                if bool(item.get("ok")):
                    continue

                failed_step = copy.deepcopy(item.get("step"))
                failed_error = str(item.get("error") or "")
                failed_step_index = self._safe_int(item.get("step_index", -1), default=-1)
                break

        return {
            "failed_step": failed_step,
            "failed_error": failed_error,
            "failed_step_index": failed_step_index,
        }

    # ------------------------------------------------------------
    # fallback
    # ------------------------------------------------------------

    def _build_basic_retry_steps(
        self,
        original_steps: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        failed_step_index: int = -1,
    ) -> List[Dict[str, Any]]:
        failed_type = str(failed_step.get("type") or "").strip().lower()

        if failed_type == "verify":
            verify_recovery = self._build_verify_recovery_steps(
                original_steps=original_steps,
                failed_step=failed_step,
                failed_step_index=failed_step_index,
            )
            if verify_recovery:
                return verify_recovery
            return [copy.deepcopy(failed_step)]

        if failed_type == "run_python":
            return [copy.deepcopy(failed_step)]

        if failed_type == "read_file":
            return [copy.deepcopy(failed_step)]

        if failed_type == "write_file":
            return [copy.deepcopy(failed_step)]

        return [copy.deepcopy(failed_step)]

    def _build_verify_recovery_steps(
        self,
        original_steps: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        failed_step_index: int = -1,
    ) -> List[Dict[str, Any]]:
        if not isinstance(original_steps, list):
            original_steps = []

        effective_failed_index = self._resolve_failed_step_index(
            original_steps=original_steps,
            failed_step=failed_step,
            failed_step_index=failed_step_index,
        )

        repaired_verify = copy.deepcopy(failed_step)
        if not isinstance(repaired_verify, dict):
            return []

        prefix_steps = original_steps[:effective_failed_index] if effective_failed_index > 0 else []

        context_index, context_step = self._find_last_step_with_index(
            prefix_steps,
            allowed_types=["run_python", "read_file", "write_file"],
        )

        if not isinstance(context_step, dict):
            return [copy.deepcopy(repaired_verify)]

        context_type = str(context_step.get("type") or "").strip().lower()

        # run_python → verify
        if context_type == "run_python":
            return [copy.deepcopy(context_step), copy.deepcopy(repaired_verify)]

        # read_file → verify
        if context_type == "read_file":
            context_path = str(context_step.get("path") or "").strip()
            if context_path and not str(repaired_verify.get("path") or "").strip():
                repaired_verify["path"] = context_path
            return [copy.deepcopy(context_step), copy.deepcopy(repaired_verify)]

        # write_file → verify
        # 這是你這次多任務測試真正踩到的情況：
        # write_file shared/a.py -> verify contains A
        # verify 如果沒有 path，原本只看 last_step_result，會抓不到檔案內容。
        # 所以 fallback 要把 verify 補成 verify(path=同一路徑, ...)
        if context_type == "write_file":
            context_path = str(context_step.get("path") or "").strip()
            if context_path and not str(repaired_verify.get("path") or "").strip():
                repaired_verify["path"] = context_path
            return [copy.deepcopy(context_step), copy.deepcopy(repaired_verify)]

        return [copy.deepcopy(repaired_verify)]

    def _resolve_failed_step_index(
        self,
        original_steps: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        failed_step_index: int,
    ) -> int:
        if isinstance(original_steps, list):
            if 0 <= int(failed_step_index) < len(original_steps):
                return int(failed_step_index)

        located = self._locate_step_index(
            steps=original_steps,
            target_step=failed_step,
        )
        if located >= 0:
            return located

        return len(original_steps)

    def _locate_step_index(
        self,
        steps: List[Dict[str, Any]],
        target_step: Dict[str, Any],
    ) -> int:
        if not isinstance(steps, list) or not isinstance(target_step, dict):
            return -1

        target_type = str(target_step.get("type") or "").strip().lower()
        target_path = str(target_step.get("path") or "").strip()
        target_contains = str(target_step.get("contains") or "").strip()
        target_equals = target_step.get("equals", None)

        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            step_type = str(step.get("type") or "").strip().lower()
            if step_type != target_type:
                continue

            step_path = str(step.get("path") or "").strip()
            step_contains = str(step.get("contains") or "").strip()
            step_equals = step.get("equals", None)

            if (
                step_path == target_path
                and step_contains == target_contains
                and step_equals == target_equals
            ):
                return idx

        return -1

    def _find_last_step_with_index(
        self,
        steps: List[Dict[str, Any]],
        allowed_types: List[str],
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        allowed = {str(x or "").strip().lower() for x in allowed_types}
        last_index = -1
        last_step: Optional[Dict[str, Any]] = None

        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type") or "").strip().lower()
            if step_type in allowed:
                last_index = idx
                last_step = copy.deepcopy(step)

        return last_index, last_step

    def _find_last_step_by_type(
        self,
        steps: List[Dict[str, Any]],
        step_type: str,
    ) -> Optional[Dict[str, Any]]:
        target = str(step_type or "").strip().lower()

        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            current_type = str(step.get("type") or "").strip().lower()
            if current_type == target:
                return copy.deepcopy(step)

        return None

    # ------------------------------------------------------------
    # summary / meta helpers
    # ------------------------------------------------------------

    def _build_summary(
        self,
        error_type: str,
        repair_mode: str,
        failed_step_type: str,
        next_replan_count: int,
        max_replans: int,
    ) -> str:
        error_text = str(error_type or "UNKNOWN")
        repair_text = str(repair_mode or "unknown")
        step_text = str(failed_step_type or "unknown")
        return (
            f"Recovery plan generated: error_type={error_text}, "
            f"repair_mode={repair_text}, failed_step={step_text}, "
            f"replan={next_replan_count}/{max_replans}"
        )

    def _infer_repair_mode(
        self,
        original_steps: List[Dict[str, Any]],
        repaired_steps: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
    ) -> str:
        if not repaired_steps:
            return "none"

        original_first = self._first_step_type(original_steps)
        repaired_first = self._first_step_type(repaired_steps)
        failed_type = str(failed_step.get("type") or "").strip().lower()

        if repaired_first == "write_file":
            if failed_type == "verify":
                return "rewrite_source_before_retry"
            return "rewrite_source"

        if repaired_first == "read_file":
            return "retry_read"

        if repaired_first == "run_python":
            if original_first == "write_file":
                return "retry_after_existing_write"
            return "retry_run"

        if repaired_first == "verify":
            if failed_type == "verify":
                return "retry_verify_with_context"
            return "generic_repair"

        return "generic_repair"

    def _first_step_type(self, steps: List[Dict[str, Any]]) -> str:
        for step in steps:
            if isinstance(step, dict):
                return str(step.get("type") or "").strip().lower()
        return ""

    # ------------------------------------------------------------
    # utils
    # ------------------------------------------------------------

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fail(
        self,
        summary: str,
        error_type: str = "UNKNOWN",
        failed_step_type: str = "",
        failed_error: str = "",
        next_replan_count: int = 0,
        max_replans: int = 0,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "replanned": False,
            "summary": str(summary),
            "plan": {
                "task": "no_replan_needed",
                "mode": "plan",
                "summary": str(summary),
                "steps": [],
                "meta": {
                    "source": "replanner",
                    "step_count": 0,
                    "failed_step_count": 0,
                    "next_replan_count": next_replan_count,
                    "max_replans": max_replans,
                    "error_type": str(error_type or "UNKNOWN"),
                    "failed_step_type": str(failed_step_type or ""),
                    "failed_error": str(failed_error or ""),
                    "repair_mode": "none",
                },
            },
        }