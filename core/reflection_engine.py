from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReflectionDecision:
    ok: bool
    action: str
    reason: str
    summary: str
    generated_steps: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "reason": self.reason,
            "summary": self.summary,
            "generated_steps": list(self.generated_steps),
            "meta": dict(self.meta),
        }


class ReflectionEngine:
    """
    第一版 Reflection Engine（規則式）
    目標：
    - 在 step retry 用完後，分析失敗原因
    - 決定要不要 replan
    - 產生補救 subtasks

    action 目前可能值：
    - "replan" : 產生新的補救 steps，讓 Agent 繼續跑
    - "abort"  : 無法補救，直接終止
    """

    def reflect(
        self,
        task: Dict[str, Any],
        error: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReflectionDecision:
        title = str(task.get("title", "")).strip()
        lower_title = title.lower()
        lower_error = str(error or "").lower()

        # --------------------------------------------------------------
        # 1. demo_always_fail：測試永久失敗後的補救流程
        #    不再沿用 always_fail 關鍵字，避免補救步驟再被測試邏輯攔截
        # --------------------------------------------------------------
        if "forced permanent failure" in lower_error or "always_fail" in lower_title:
            return ReflectionDecision(
                ok=True,
                action="replan",
                reason="step_failed_permanently",
                summary="原步驟持續失敗，改用替代補救流程。",
                generated_steps=[
                    "建立補救資料夾 demo_ok",
                    "驗證補救資料夾 demo_ok 是否存在",
                ],
                meta={
                    "strategy": "fallback_recovery_flow",
                    "source_error": error,
                },
            )

        # --------------------------------------------------------------
        # 2. file not found：先建立檔案，再重新驗證
        # --------------------------------------------------------------
        if "file not found" in lower_error:
            return ReflectionDecision(
                ok=True,
                action="replan",
                reason="missing_file",
                summary="檔案不存在，先建立目標資源再重新驗證。",
                generated_steps=[
                    "建立缺失目標資源",
                    "再次驗證缺失目標資源",
                ],
                meta={
                    "strategy": "create_then_verify",
                    "source_error": error,
                },
            )

        # --------------------------------------------------------------
        # 3. unsupported tool / unsupported action
        # --------------------------------------------------------------
        if "unsupported tool" in lower_error or "unsupported workspace action" in lower_error:
            return ReflectionDecision(
                ok=False,
                action="abort",
                reason="unsupported_operation",
                summary="工具或動作本身不支援，無法自動補救。",
                generated_steps=[],
                meta={
                    "strategy": "abort",
                    "source_error": error,
                },
            )

        # --------------------------------------------------------------
        # 4. forced failure on first attempt 通常 retry 已可處理
        #    走到這裡代表 retry 邏輯異常或已被耗盡，補一個保守 replan
        # --------------------------------------------------------------
        if "forced failure on first attempt" in lower_error or "fail_first" in lower_title:
            return ReflectionDecision(
                ok=True,
                action="replan",
                reason="retry_path_exhausted",
                summary="預期可由 retry 解決，但目前仍失敗，改走保守替代步驟。",
                generated_steps=[
                    "建立替代資料夾 demo_ok",
                    "驗證替代資料夾 demo_ok 是否存在",
                ],
                meta={
                    "strategy": "fallback_after_retry",
                    "source_error": error,
                },
            )

        # --------------------------------------------------------------
        # 5. 一般未知錯誤：生成保守補救步驟
        # --------------------------------------------------------------
        if title:
            return ReflectionDecision(
                ok=True,
                action="replan",
                reason="generic_runtime_failure",
                summary="遇到未知執行錯誤，嘗試產生保守補救步驟。",
                generated_steps=[
                    f"重新分析失敗原因：{title}",
                    f"建立補救內容：{title}",
                    f"再次驗證結果：{title}",
                ],
                meta={
                    "strategy": "generic_recovery",
                    "source_error": error,
                },
            )

        return ReflectionDecision(
            ok=False,
            action="abort",
            reason="empty_task_context",
            summary="缺乏可用任務資訊，無法補救。",
            generated_steps=[],
            meta={
                "strategy": "abort",
                "source_error": error,
            },
        )