from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import traceback


@dataclass
class ReflectionIssue:
    level: str
    code: str
    message: str
    evidence: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionReport:
    ok: bool
    summary: str
    score: int
    status: str
    issues: List[ReflectionIssue] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "score": self.score,
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
            "strengths": list(self.strengths),
            "suggestions": list(self.suggestions),
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
        }


class ReflectionEngine:
    """
    ReflectionEngine
    ----------------
    專門把一次任務執行後的資料做「事後分析」。
    不直接決策下一步，只負責產出一份結構化 reflection report。

    支援輸入：
    - plan: dict / list / object / None
    - runtime: dict / object / None
    - log: list / dict / str / None
    - result: dict / object / None

    輸出：
    - ReflectionReport
    """

    def analyze(
        self,
        plan: Any = None,
        runtime: Any = None,
        log: Any = None,
        result: Any = None,
    ) -> Dict[str, Any]:
        try:
            normalized_plan = self._normalize_plan(plan)
            normalized_runtime = self._normalize_runtime(runtime)
            normalized_log = self._normalize_log(log)
            normalized_result = self._normalize_result(result)

            issues: List[ReflectionIssue] = []
            strengths: List[str] = []
            suggestions: List[str] = []
            metrics: Dict[str, Any] = {}

            self._check_plan_exists(normalized_plan, issues, suggestions)
            self._check_plan_quality(normalized_plan, issues, strengths, suggestions, metrics)
            self._check_runtime(normalized_runtime, issues, strengths, suggestions, metrics)
            self._check_log(normalized_log, issues, suggestions, metrics)
            self._check_result(normalized_result, issues, strengths, suggestions, metrics)
            self._cross_check(normalized_plan, normalized_runtime, normalized_log, normalized_result, issues, strengths, suggestions, metrics)

            score = self._compute_score(issues, metrics)
            status = self._derive_status(score, normalized_result, issues)
            ok = status in ("good", "acceptable")

            summary = self._build_summary(score, status, issues, strengths, metrics)

            report = ReflectionReport(
                ok=ok,
                summary=summary,
                score=score,
                status=status,
                issues=issues,
                strengths=strengths,
                suggestions=self._dedup_keep_order(suggestions),
                metrics=metrics,
            )
            return report.to_dict()

        except Exception as exc:
            fallback_issue = ReflectionIssue(
                level="critical",
                code="reflection_engine_crashed",
                message=f"ReflectionEngine analyze() 發生例外: {exc}",
                evidence={"traceback": traceback.format_exc()},
                suggestion="先修復 reflection_engine，再重新分析本次任務。",
            )
            fallback_report = ReflectionReport(
                ok=False,
                summary="ReflectionEngine 執行失敗，無法完成反思分析。",
                score=0,
                status="broken",
                issues=[fallback_issue],
                strengths=[],
                suggestions=["檢查 reflection_engine 的輸入格式與欄位內容。"],
                metrics={},
            )
            return fallback_report.to_dict()

    # ------------------------------------------------------------------
    # Normalize
    # ------------------------------------------------------------------

    def _normalize_plan(self, plan: Any) -> Dict[str, Any]:
        if plan is None:
            return {"raw": None, "steps": [], "goal": None}

        if isinstance(plan, dict):
            steps = self._extract_steps_from_plan_dict(plan)
            goal = plan.get("goal") or plan.get("task") or plan.get("objective")
            return {
                "raw": plan,
                "steps": steps,
                "goal": goal,
                "step_count": len(steps),
            }

        if isinstance(plan, list):
            steps = [self._to_text(x) for x in plan if self._to_text(x)]
            return {
                "raw": plan,
                "steps": steps,
                "goal": None,
                "step_count": len(steps),
            }

        return {
            "raw": plan,
            "steps": [],
            "goal": getattr(plan, "goal", None),
            "step_count": 0,
        }

    def _normalize_runtime(self, runtime: Any) -> Dict[str, Any]:
        if runtime is None:
            return {
                "raw": None,
                "status": None,
                "started": None,
                "ended": None,
                "duration_sec": None,
                "executed_steps": None,
                "failed_steps": None,
                "retried_steps": None,
            }

        if isinstance(runtime, dict):
            return {
                "raw": runtime,
                "status": runtime.get("status"),
                "started": runtime.get("started_at") or runtime.get("start_time"),
                "ended": runtime.get("finished_at") or runtime.get("end_time"),
                "duration_sec": runtime.get("duration_sec") or runtime.get("elapsed_sec"),
                "executed_steps": runtime.get("executed_steps"),
                "failed_steps": runtime.get("failed_steps"),
                "retried_steps": runtime.get("retried_steps"),
            }

        return {
            "raw": runtime,
            "status": getattr(runtime, "status", None),
            "started": getattr(runtime, "started_at", None),
            "ended": getattr(runtime, "finished_at", None),
            "duration_sec": getattr(runtime, "duration_sec", None),
            "executed_steps": getattr(runtime, "executed_steps", None),
            "failed_steps": getattr(runtime, "failed_steps", None),
            "retried_steps": getattr(runtime, "retried_steps", None),
        }

    def _normalize_log(self, log: Any) -> Dict[str, Any]:
        if log is None:
            return {
                "raw": None,
                "entries": [],
                "count": 0,
                "error_count": 0,
                "warning_count": 0,
            }

        entries: List[Dict[str, Any]] = []

        if isinstance(log, str):
            lines = [line.strip() for line in log.splitlines() if line.strip()]
            entries = [{"level": self._guess_level_from_text(line), "message": line} for line in lines]

        elif isinstance(log, list):
            for item in log:
                if isinstance(item, dict):
                    entries.append(
                        {
                            "level": str(item.get("level", "")).lower() or self._guess_level_from_text(self._to_text(item)),
                            "message": self._to_text(item.get("message") or item),
                            "raw": item,
                        }
                    )
                else:
                    text = self._to_text(item)
                    if text:
                        entries.append({"level": self._guess_level_from_text(text), "message": text})

        elif isinstance(log, dict):
            maybe_entries = log.get("entries") or log.get("logs") or []
            if isinstance(maybe_entries, list):
                for item in maybe_entries:
                    if isinstance(item, dict):
                        entries.append(
                            {
                                "level": str(item.get("level", "")).lower() or self._guess_level_from_text(self._to_text(item)),
                                "message": self._to_text(item.get("message") or item),
                                "raw": item,
                            }
                        )
                    else:
                        text = self._to_text(item)
                        if text:
                            entries.append({"level": self._guess_level_from_text(text), "message": text})
            else:
                text = self._to_text(log)
                if text:
                    entries.append({"level": self._guess_level_from_text(text), "message": text})

        error_count = sum(1 for e in entries if e.get("level") in ("error", "critical"))
        warning_count = sum(1 for e in entries if e.get("level") == "warning")

        return {
            "raw": log,
            "entries": entries,
            "count": len(entries),
            "error_count": error_count,
            "warning_count": warning_count,
        }

    def _normalize_result(self, result: Any) -> Dict[str, Any]:
        if result is None:
            return {
                "raw": None,
                "success": None,
                "status": None,
                "final_output": None,
                "error": None,
            }

        if isinstance(result, dict):
            success = result.get("success")
            status = result.get("status")
            error = result.get("error") or result.get("exception") or result.get("message")
            final_output = (
                result.get("final_output")
                or result.get("output")
                or result.get("answer")
                or result.get("result")
            )
            return {
                "raw": result,
                "success": success,
                "status": status,
                "final_output": final_output,
                "error": error,
            }

        return {
            "raw": result,
            "success": getattr(result, "success", None),
            "status": getattr(result, "status", None),
            "final_output": getattr(result, "final_output", None),
            "error": getattr(result, "error", None),
        }

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_plan_exists(
        self,
        plan: Dict[str, Any],
        issues: List[ReflectionIssue],
        suggestions: List[str],
    ) -> None:
        if not plan.get("raw"):
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="missing_plan",
                    message="本次任務沒有可用的 plan 資料。",
                    suggestion="在執行前先產出結構化 plan，再交給 runtime 執行。",
                )
            )
            suggestions.append("讓 planner 輸出固定欄位，例如 goal、steps、constraints。")

    def _check_plan_quality(
        self,
        plan: Dict[str, Any],
        issues: List[ReflectionIssue],
        strengths: List[str],
        suggestions: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        steps = plan.get("steps") or []
        step_count = len(steps)
        metrics["plan_step_count"] = step_count

        if step_count == 0:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="plan_has_no_steps",
                    message="plan 存在，但沒有可執行 steps。",
                    evidence={"goal": plan.get("goal")},
                    suggestion="把 plan 拆成明確步驟，至少讓 executor 能逐步追蹤。",
                )
            )
            return

        if step_count >= 2:
            strengths.append("plan 已拆成多個 steps，具備基本可執行性。")

        very_short_steps = [s for s in steps if len(str(s).strip()) < 4]
        if very_short_steps:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="plan_steps_too_short",
                    message="部分 plan steps 過短，可能缺乏可執行細節。",
                    evidence={"examples": very_short_steps[:3]},
                    suggestion="把 step 寫成動作句，例如『讀取任務』『呼叫工具』『驗證結果』。",
                )
            )
            suggestions.append("避免使用過短 step 名稱，例如『做一下』『處理它』。")

        duplicate_steps = self._find_duplicates(steps)
        if duplicate_steps:
            issues.append(
                ReflectionIssue(
                    level="info",
                    code="duplicate_plan_steps",
                    message="plan 中有重複 steps，可能代表規劃冗餘。",
                    evidence={"duplicates": duplicate_steps},
                    suggestion="在 planner 階段加入 step 去重。",
                )
            )

    def _check_runtime(
        self,
        runtime: Dict[str, Any],
        issues: List[ReflectionIssue],
        strengths: List[str],
        suggestions: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        status = self._to_text(runtime.get("status")).lower()
        duration_sec = self._safe_number(runtime.get("duration_sec"))
        executed_steps = self._safe_int(runtime.get("executed_steps"))
        failed_steps = self._safe_int(runtime.get("failed_steps"))
        retried_steps = self._safe_int(runtime.get("retried_steps"))

        metrics["runtime_status"] = status or None
        metrics["duration_sec"] = duration_sec
        metrics["executed_steps"] = executed_steps
        metrics["failed_steps"] = failed_steps
        metrics["retried_steps"] = retried_steps

        if status in ("success", "completed", "done", "ok"):
            strengths.append("runtime 狀態顯示為成功完成。")

        if status in ("failed", "error", "crashed", "aborted"):
            issues.append(
                ReflectionIssue(
                    level="critical",
                    code="runtime_failed",
                    message=f"runtime 狀態為失敗：{status}",
                    suggestion="追查失敗 step、工具錯誤、或流程中斷點。",
                )
            )

        if duration_sec is not None:
            if duration_sec < 0:
                issues.append(
                    ReflectionIssue(
                        level="warning",
                        code="negative_duration",
                        message="runtime duration_sec 小於 0，表示時間紀錄異常。",
                        evidence={"duration_sec": duration_sec},
                        suggestion="檢查開始/結束時間的寫入順序。",
                    )
                )
            elif duration_sec > 0:
                strengths.append("runtime 有記錄執行時間，可用於後續效能分析。")

        if failed_steps is not None and failed_steps > 0:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="failed_steps_detected",
                    message=f"runtime 顯示有 {failed_steps} 個失敗 steps。",
                    evidence={"failed_steps": failed_steps},
                    suggestion="把每個失敗 step 的原因記到 runtime 或 log。",
                )
            )

        if retried_steps is not None and retried_steps > 0:
            strengths.append(f"runtime 發生過 {retried_steps} 次 retry，代表具備一定恢復能力。")
            suggestions.append("可以在 reflection 裡記錄 retry 成功率，之後做策略優化。")

    def _check_log(
        self,
        log: Dict[str, Any],
        issues: List[ReflectionIssue],
        suggestions: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        count = log.get("count", 0)
        error_count = log.get("error_count", 0)
        warning_count = log.get("warning_count", 0)

        metrics["log_count"] = count
        metrics["log_error_count"] = error_count
        metrics["log_warning_count"] = warning_count

        if count == 0:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="empty_log",
                    message="本次任務沒有可分析的 log。",
                    suggestion="至少保留 step start / step end / tool result / error 這四類 log。",
                )
            )
            return

        if error_count > 0:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="errors_in_log",
                    message=f"log 中有 {error_count} 筆 error/critical 記錄。",
                    evidence={"error_count": error_count},
                    suggestion="把錯誤分類為 tool error、timeout、validation error、logic error。",
                )
            )

        if warning_count > 0:
            suggestions.append("可把 warning 類型整理成固定 code，方便統計。")

    def _check_result(
        self,
        result: Dict[str, Any],
        issues: List[ReflectionIssue],
        strengths: List[str],
        suggestions: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        success = result.get("success")
        status = self._to_text(result.get("status")).lower()
        final_output = result.get("final_output")
        error = result.get("error")

        metrics["result_success"] = success
        metrics["result_status"] = status or None
        metrics["has_final_output"] = bool(final_output)
        metrics["has_error"] = bool(error)

        if success is True:
            strengths.append("result 明確標示 success=True。")

        if success is False:
            issues.append(
                ReflectionIssue(
                    level="critical",
                    code="result_marked_failed",
                    message="result 明確標示 success=False。",
                    evidence={"status": status, "error": self._to_text(error)},
                    suggestion="檢查最後輸出是否因驗證失敗、工具失敗、或中斷造成。",
                )
            )

        if not final_output and success is True:
            issues.append(
                ReflectionIssue(
                    level="warning",
                    code="success_without_output",
                    message="result 顯示成功，但沒有 final_output。",
                    suggestion="成功任務應產出明確 output，避免上層無法使用結果。",
                )
            )

        if error:
            issues.append(
                ReflectionIssue(
                    level="warning" if success is not False else "critical",
                    code="result_contains_error",
                    message="result 中包含 error 訊息。",
                    evidence={"error": self._to_text(error)},
                    suggestion="把 error 結構化，例如 code / message / recoverable。",
                )
            )
            suggestions.append("錯誤不要只存文字，最好有 code 與 recoverable 欄位。")

    def _cross_check(
        self,
        plan: Dict[str, Any],
        runtime: Dict[str, Any],
        log: Dict[str, Any],
        result: Dict[str, Any],
        issues: List[ReflectionIssue],
        strengths: List[str],
        suggestions: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        plan_steps = len(plan.get("steps") or [])
        executed_steps = self._safe_int(runtime.get("executed_steps"))
        failed_steps = self._safe_int(runtime.get("failed_steps"))
        success = result.get("success")
        has_error_logs = (log.get("error_count") or 0) > 0
        has_output = bool(result.get("final_output"))

        if plan_steps and executed_steps is not None:
            metrics["step_completion_ratio"] = round(executed_steps / max(plan_steps, 1), 3)

            if executed_steps < plan_steps:
                issues.append(
                    ReflectionIssue(
                        level="warning",
                        code="not_all_steps_executed",
                        message=f"plan 有 {plan_steps} 步，但 runtime 只記錄執行了 {executed_steps} 步。",
                        evidence={
                            "plan_steps": plan_steps,
                            "executed_steps": executed_steps,
                        },
                        suggestion="確認 runtime 是否遺漏記錄，或流程是否中途提前結束。",
                    )
                )

            if executed_steps >= plan_steps and plan_steps > 0:
                strengths.append("runtime 執行步數已覆蓋 plan 步數。")

        if success is True and has_error_logs:
            issues.append(
                ReflectionIssue(
                    level="info",
                    code="success_with_error_logs",
                    message="任務最終成功，但中途出現 error log。",
                    suggestion="把可恢復錯誤與致命錯誤分開，避免誤判品質。",
                )
            )

        if success is False and has_output:
            issues.append(
                ReflectionIssue(
                    level="info",
                    code="failed_but_has_output",
                    message="任務標示失敗，但仍產生了 output。",
                    suggestion="區分 partial output 與 final output，避免上層誤用。",
                )
            )

        if failed_steps is not None and failed_steps == 0 and success is True and not has_error_logs:
            strengths.append("整體流程乾淨，未觀察到失敗 step 或 error log。")

        if not plan.get("goal") and plan_steps > 0:
            suggestions.append("planner 最好補 goal 欄位，讓 reflection 能更準確判斷是否完成任務目標。")

    # ------------------------------------------------------------------
    # Scoring / Summary
    # ------------------------------------------------------------------

    def _compute_score(self, issues: List[ReflectionIssue], metrics: Dict[str, Any]) -> int:
        score = 100

        penalty_map = {
            "critical": 25,
            "warning": 10,
            "info": 3,
        }

        for issue in issues:
            score -= penalty_map.get(issue.level, 5)

        log_count = metrics.get("log_count", 0)
        if log_count > 0:
            score += 2

        if metrics.get("has_final_output"):
            score += 5

        if metrics.get("result_success") is True:
            score += 5

        if metrics.get("plan_step_count", 0) >= 2:
            score += 3

        score = max(0, min(100, score))
        return score

    def _derive_status(
        self,
        score: int,
        result: Dict[str, Any],
        issues: List[ReflectionIssue],
    ) -> str:
        has_critical = any(i.level == "critical" for i in issues)
        if has_critical:
            return "bad"

        success = result.get("success")
        if success is False:
            return "bad"

        if score >= 85:
            return "good"
        if score >= 60:
            return "acceptable"
        return "needs_improvement"

    def _build_summary(
        self,
        score: int,
        status: str,
        issues: List[ReflectionIssue],
        strengths: List[str],
        metrics: Dict[str, Any],
    ) -> str:
        issue_count = len(issues)
        strength_count = len(strengths)

        if status == "good":
            return (
                f"本次任務整體表現良好，reflection score={score}。"
                f"目前發現 {issue_count} 個問題，保留 {strength_count} 個正向訊號。"
            )

        if status == "acceptable":
            return (
                f"本次任務可接受，但仍有改善空間，reflection score={score}。"
                f"目前發現 {issue_count} 個問題，建議優先處理 warning 類項目。"
            )

        if status == "needs_improvement":
            return (
                f"本次任務品質偏弱，reflection score={score}。"
                f"目前發現 {issue_count} 個問題，流程穩定性需要加強。"
            )

        if status == "bad":
            return (
                f"本次任務存在明顯失敗或高風險訊號，reflection score={score}。"
                f"建議先修復 critical / failed 類問題，再繼續堆功能。"
            )

        return "本次任務已完成 reflection 分析。"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_steps_from_plan_dict(self, plan: Dict[str, Any]) -> List[str]:
        candidate_keys = ["steps", "plan", "items", "subtasks", "actions"]
        for key in candidate_keys:
            value = plan.get(key)
            if isinstance(value, list):
                steps: List[str] = []
                for item in value:
                    if isinstance(item, dict):
                        text = (
                            item.get("description")
                            or item.get("title")
                            or item.get("step")
                            or item.get("action")
                            or self._to_text(item)
                        )
                    else:
                        text = self._to_text(item)

                    text = text.strip()
                    if text:
                        steps.append(text)
                return steps

        return []

    def _guess_level_from_text(self, text: str) -> str:
        lower = (text or "").lower()
        if any(k in lower for k in ["critical", "fatal", "panic"]):
            return "critical"
        if any(k in lower for k in ["error", "failed", "exception", "traceback"]):
            return "error"
        if any(k in lower for k in ["warn", "warning", "retry", "fallback"]):
            return "warning"
        return "info"

    def _find_duplicates(self, items: List[str]) -> List[str]:
        seen = set()
        duplicates = []
        for item in items:
            key = item.strip().lower()
            if not key:
                continue
            if key in seen and item not in duplicates:
                duplicates.append(item)
            seen.add(key)
        return duplicates

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _safe_number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            return ""

    def _dedup_keep_order(self, items: List[str]) -> List[str]:
        seen = set()
        result = []
        for item in items:
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result


if __name__ == "__main__":
    engine = ReflectionEngine()

    demo_plan = {
        "goal": "完成一個簡單任務",
        "steps": [
            "讀取任務",
            "規劃步驟",
            "執行工具",
            "驗證結果",
        ],
    }

    demo_runtime = {
        "status": "success",
        "duration_sec": 3.6,
        "executed_steps": 4,
        "failed_steps": 0,
        "retried_steps": 1,
    }

    demo_log = [
        {"level": "info", "message": "task started"},
        {"level": "warning", "message": "tool timeout, retry once"},
        {"level": "info", "message": "task finished"},
    ]

    demo_result = {
        "success": True,
        "status": "completed",
        "final_output": "任務已完成",
        "error": None,
    }

    report = engine.analyze(
        plan=demo_plan,
        runtime=demo_runtime,
        log=demo_log,
        result=demo_result,
    )

    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))