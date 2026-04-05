from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


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
       - 先分類 error_type
       - transient / timeout / rate_limit / network -> retry
       - validation / syntax / not_found -> replan
       - permission / unsafe -> fail
       - unknown -> retry 不行再 replan，不行就 fail
    6. 若 step 成功但 runtime 還殘留 last_error：
       - 保守 continue，不要因為舊錯誤殘留又重複 replan
    7. 正常情況 -> continue
    """

    TERMINAL_STATUSES = {
        "finished",
        "failed",
        "cancelled",
        "timeout",
    }

    RETRYABLE_ERROR_TYPES = {
        "transient_error",
        "timeout_error",
        "network_error",
        "rate_limit_error",
        "temporary_error",
    }

    REPLANNABLE_ERROR_TYPES = {
        "validation_error",
        "syntax_error",
        "not_found_error",
        "dependency_error",
        "tool_usage_error",
        "command_error",
    }

    FATAL_ERROR_TYPES = {
        "permission_error",
        "unsafe_action",
        "cancelled",
        "fatal_error",
    }

    READ_ONLY_STEP_TYPES = {
        "read_file",
        "list_files",
        "inspect",
        "analyze",
        "search",
        "web_search",
        "check",
        "verify",
        "noop",
    }

    SIDE_EFFECT_STEP_TYPES = {
        "command",
        "write_file",
        "delete_file",
        "call_api",
        "http_request",
        "shell",
        "execute",
    }

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
        error_type = self._classify_error(
            error_text=tool_error,
            step=step,
            step_result=step_result,
            runtime_state=runtime_state,
        )

        step_type = self._safe_str(step.get("type")).lower()
        is_idempotent = self._is_idempotent_step(step=step, step_result=step_result)
        retry_safe = self._is_retry_safe(step=step, step_result=step_result)
        replan_safe = self._is_replan_safe(step=step, step_result=step_result)

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
                error_type="",
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
            )

        if status in {"failed", "cancelled", "timeout"}:
            return self._result(
                decision="fail",
                reason=f"runtime_state already terminal: {status}",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
                error_type=error_type,
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
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
                    error_type="plan_empty",
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type="validation_error",
                )

            return self._result(
                decision="fail",
                reason="plan is empty and replan limit reached",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
                error_type="plan_empty",
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
                failure_type="validation_error",
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
                error_type="",
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
            )

        # -----------------------------------------------------
        # 4. step / tool 失敗
        # -----------------------------------------------------
        step_failed = (not step_ok) or (tool_status in {"failed", "error"})

        if step_failed:
            # 4.1 fatal
            if error_type in self.FATAL_ERROR_TYPES:
                return self._result(
                    decision="fail",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                    error_type=error_type,
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type=self._map_error_type_to_failure_type(error_type, fallback=failure_type),
                )

            # 4.2 retryable
            if error_type in self.RETRYABLE_ERROR_TYPES:
                if self._should_retry(
                    retry_count=retry_count,
                    max_retries=max_retries,
                    failure_type=failure_type,
                    step_result=step_result,
                    tool_result=tool_result,
                    step=step,
                ):
                    return self._result(
                        decision="retry",
                        reason=tool_error,
                        goal=goal,
                        step=step,
                        step_result=step_result,
                        runtime_state=runtime_state,
                        error_type=error_type,
                        retry_safe=retry_safe,
                        replan_safe=replan_safe,
                        is_idempotent=is_idempotent,
                        failure_type=self._map_error_type_to_failure_type(error_type, fallback="transient_error"),
                    )

                if self._should_replan(
                    replan_count=replan_count,
                    max_replans=max_replans,
                    step=step,
                ):
                    return self._result(
                        decision="replan",
                        reason=tool_error,
                        goal=goal,
                        step=step,
                        step_result=step_result,
                        runtime_state=runtime_state,
                        error_type=error_type,
                        retry_safe=retry_safe,
                        replan_safe=replan_safe,
                        is_idempotent=is_idempotent,
                        failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"),
                    )

                return self._result(
                    decision="fail",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                    error_type=error_type,
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"),
                )

            # 4.3 replannable
            if error_type in self.REPLANNABLE_ERROR_TYPES:
                if self._should_replan(
                    replan_count=replan_count,
                    max_replans=max_replans,
                    step=step,
                ):
                    return self._result(
                        decision="replan",
                        reason=tool_error,
                        goal=goal,
                        step=step,
                        step_result=step_result,
                        runtime_state=runtime_state,
                        error_type=error_type,
                        retry_safe=retry_safe,
                        replan_safe=replan_safe,
                        is_idempotent=is_idempotent,
                        failure_type=self._map_error_type_to_failure_type(error_type, fallback="validation_error"),
                    )

                return self._result(
                    decision="fail",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                    error_type=error_type,
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type=self._map_error_type_to_failure_type(error_type, fallback="validation_error"),
                )

            # 4.4 unknown -> retry -> replan -> fail
            if self._should_retry(
                retry_count=retry_count,
                max_retries=max_retries,
                failure_type=failure_type,
                step_result=step_result,
                tool_result=tool_result,
                step=step,
            ):
                return self._result(
                    decision="retry",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                    error_type=error_type,
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"),
                )

            if self._should_replan(
                replan_count=replan_count,
                max_replans=max_replans,
                step=step,
            ):
                return self._result(
                    decision="replan",
                    reason=tool_error,
                    goal=goal,
                    step=step,
                    step_result=step_result,
                    runtime_state=runtime_state,
                    error_type=error_type,
                    retry_safe=retry_safe,
                    replan_safe=replan_safe,
                    is_idempotent=is_idempotent,
                    failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"),
                )

            return self._result(
                decision="fail",
                reason=tool_error,
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
                error_type=error_type,
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
                failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"),
            )

        # -----------------------------------------------------
        # 5. step 成功，但 runtime 還殘留舊錯誤
        # -----------------------------------------------------
        if last_error:
            return self._result(
                decision="continue",
                reason=f"step ok but runtime still contains error: {last_error}",
                goal=goal,
                step=step,
                step_result=step_result,
                runtime_state=runtime_state,
                error_type="",
                retry_safe=retry_safe,
                replan_safe=replan_safe,
                is_idempotent=is_idempotent,
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
            error_type="",
            retry_safe=retry_safe,
            replan_safe=replan_safe,
            is_idempotent=is_idempotent,
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
        step: Dict[str, Any],
    ) -> bool:
        if max_retries <= 0:
            return False

        if retry_count >= max_retries:
            return False

        if not self._is_retry_safe(step=step, step_result=step_result):
            return False

        result_retryable = step_result.get("retryable")
        if isinstance(result_retryable, bool):
            return result_retryable

        tool_retryable = tool_result.get("retryable")
        if isinstance(tool_retryable, bool):
            return tool_retryable

        retryable_failure_types = {
            "",
            "tool_error",
            "transient_error",
            "timeout",
            "temporary",
        }

        return failure_type in retryable_failure_types

    def _should_replan(
        self,
        *,
        replan_count: int,
        max_replans: int,
        step: Dict[str, Any],
    ) -> bool:
        if max_replans <= 0:
            return False

        if replan_count >= max_replans:
            return False

        if not self._is_replan_safe(step=step, step_result=None):
            return False

        return True

    def _classify_error(
        self,
        *,
        error_text: str,
        step: Dict[str, Any],
        step_result: Dict[str, Any],
        runtime_state: Dict[str, Any],
    ) -> str:
        explicit_failure_type = self._safe_str(step_result.get("failure_type")).lower()
        if explicit_failure_type:
            mapped = self._normalize_explicit_failure_type(explicit_failure_type)
            if mapped:
                return mapped

        runtime_failure_type = self._safe_str(runtime_state.get("failure_type")).lower()
        if runtime_failure_type:
            mapped = self._normalize_explicit_failure_type(runtime_failure_type)
            if mapped:
                return mapped

        if not error_text:
            step_type = self._safe_str(step.get("type")).lower()
            if step_type == "command":
                return "command_error"
            return "unknown_error"

        text = error_text.lower()

        transient_keywords = [
            "timeout",
            "timed out",
            "connection reset",
            "connection refused",
            "temporary",
            "temporarily",
            "rate limit",
            "too many requests",
            "network",
            "service unavailable",
            "unavailable",
            "try again",
            "econnreset",
            "502 bad gateway",
            "503 service unavailable",
            "504 gateway timeout",
        ]
        if self._contains_any(text, transient_keywords):
            if "timeout" in text or "timed out" in text or "gateway timeout" in text:
                return "timeout_error"
            if "rate limit" in text or "too many requests" in text:
                return "rate_limit_error"
            if "network" in text or "connection" in text or "econnreset" in text:
                return "network_error"
            return "transient_error"

        not_found_keywords = [
            "no such file",
            "not found",
            "cannot find",
            "can't find",
            "does not exist",
            "no module named",
        ]
        if self._contains_any(text, not_found_keywords):
            return "not_found_error"

        validation_keywords = [
            "invalid",
            "validation",
            "bad request",
            "missing required",
            "missing argument",
            "unknown argument",
            "unsupported option",
            "required field",
        ]
        if self._contains_any(text, validation_keywords):
            return "validation_error"

        syntax_keywords = [
            "syntax error",
            "syntaxerror",
            "unexpected token",
            "unexpected end",
            "usage:",
            "parse error",
        ]
        if self._contains_any(text, syntax_keywords):
            return "syntax_error"

        dependency_keywords = [
            "dependency",
            "blocked",
            "waiting for",
            "prerequisite",
        ]
        if self._contains_any(text, dependency_keywords):
            return "dependency_error"

        permission_keywords = [
            "permission denied",
            "access denied",
            "operation not permitted",
            "forbidden",
            "unauthorized",
        ]
        if self._contains_any(text, permission_keywords):
            return "permission_error"

        unsafe_keywords = [
            "unsafe",
            "dangerous",
            "blocked by safety",
            "policy violation",
        ]
        if self._contains_any(text, unsafe_keywords):
            return "unsafe_action"

        step_type = self._safe_str(step.get("type")).lower()
        if step_type == "command":
            return "command_error"

        return "unknown_error"

    def _normalize_explicit_failure_type(self, failure_type: str) -> str:
        mapping = {
            "transient_error": "transient_error",
            "timeout": "timeout_error",
            "tool_error": "unknown_error",
            "validation_error": "validation_error",
            "dependency_unmet": "dependency_error",
            "unsafe_action": "unsafe_action",
            "unsafe_action_blocked": "unsafe_action",
            "cancelled": "cancelled",
            "internal_error": "fatal_error",
        }
        return mapping.get(failure_type, "")

    def _map_error_type_to_failure_type(self, error_type: str, fallback: str = "tool_error") -> str:
        mapping = {
            "transient_error": "transient_error",
            "timeout_error": "timeout",
            "network_error": "transient_error",
            "rate_limit_error": "transient_error",
            "temporary_error": "transient_error",
            "validation_error": "validation_error",
            "syntax_error": "validation_error",
            "not_found_error": "validation_error",
            "dependency_error": "dependency_unmet",
            "permission_error": "unsafe_action_blocked",
            "unsafe_action": "unsafe_action_blocked",
            "tool_usage_error": "validation_error",
            "command_error": "tool_error",
            "unknown_error": fallback or "tool_error",
            "cancelled": "cancelled",
            "fatal_error": "internal_error",
        }
        return mapping.get(error_type, fallback or "tool_error")

    # =========================================================
    # Idempotent / safety helpers
    # =========================================================

    def _is_idempotent_step(
        self,
        *,
        step: Dict[str, Any],
        step_result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        explicit = self._read_boolean_flag(step, ["idempotent"])
        if explicit is not None:
            return explicit

        if isinstance(step_result, dict):
            explicit = self._read_boolean_flag(step_result, ["idempotent"])
            if explicit is not None:
                return explicit

        step_type = self._safe_str(step.get("type")).lower()

        if step_type in self.READ_ONLY_STEP_TYPES:
            return True

        if step_type in self.SIDE_EFFECT_STEP_TYPES:
            return False

        side_effects = self._read_boolean_flag(step, ["side_effects"])
        if side_effects is not None:
            return not side_effects

        return False

    def _is_retry_safe(
        self,
        *,
        step: Dict[str, Any],
        step_result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        explicit = self._read_boolean_flag(step, ["retry_safe"])
        if explicit is not None:
            return explicit

        if isinstance(step_result, dict):
            explicit = self._read_boolean_flag(step_result, ["retry_safe"])
            if explicit is not None:
                return explicit

        return self._is_idempotent_step(step=step, step_result=step_result)

    def _is_replan_safe(
        self,
        *,
        step: Dict[str, Any],
        step_result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        explicit = self._read_boolean_flag(step, ["replan_safe"])
        if explicit is not None:
            return explicit

        if isinstance(step_result, dict):
            explicit = self._read_boolean_flag(step_result, ["replan_safe"])
            if explicit is not None:
                return explicit

        return self._is_idempotent_step(step=step, step_result=step_result)

    def _read_boolean_flag(self, obj: Optional[Dict[str, Any]], keys: List[str]) -> Optional[bool]:
        if not isinstance(obj, dict):
            return None

        for key in keys:
            if key in obj:
                return self._as_bool(obj.get(key))
        return None

    # =========================================================
    # Step result helpers
    # =========================================================

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
            or self._safe_str(tool_result.get("message"))
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
        error_type: str,
        retry_safe: bool,
        replan_safe: bool,
        is_idempotent: bool,
        failure_type: str = "",
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
            "failure_type": failure_type or runtime_state.get("failure_type"),
            "retry_count": runtime_state.get("retry_count"),
            "max_retries": runtime_state.get("max_retries"),
            "replan_count": runtime_state.get("replan_count"),
            "max_replans": runtime_state.get("max_replans"),
            "step_result_ok": step_result.get("ok"),
            "error_type": error_type,
            "retry_safe": retry_safe,
            "replan_safe": replan_safe,
            "idempotent": is_idempotent,
        }

    # =========================================================
    # IO helpers
    # =========================================================

    def _load_json(self, file_path: str) -> Dict[str, Any]:
        if not file_path or not os.path.exists(file_path):
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
        if not file_path or not os.path.exists(file_path):
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

    # =========================================================
    # Primitive helpers
    # =========================================================

    def _contains_any(self, text: str, keywords: List[str]) -> bool:
        for kw in keywords:
            if kw in text:
                return True
        return False

    def _safe_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.strip().lower() in {
                "true",
                "1",
                "yes",
                "y",
                "ok",
            }

        if isinstance(value, (int, float)):
            return value != 0

        return False

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default