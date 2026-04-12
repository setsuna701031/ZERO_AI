from __future__ import annotations

from typing import Any, Dict, List, Optional


class Verifier:
    """
    ZERO Verifier（相容 AgentLoop 版）

    目標：
    1. 與 agent_loop._run_verifier() 相容
    2. 不破壞 execution_result 原始結構
    3. 只補充 verifier 資訊，不覆寫 final_answer / last_result / results
    4. 預設以 execution_result 內部 ok / results 進行最小驗證
    """

    def __init__(self, llm_client: Any = None, debug: bool = False) -> None:
        self.llm_client = llm_client
        self.debug = debug

    # ------------------------------------------------------------
    # AgentLoop 相容入口
    # agent_loop 會優先呼叫 verify(result=execution_result)
    # ------------------------------------------------------------

    def verify(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "ok": False,
                "error": "verifier received non-dict result",
                "result": {
                    "verified": False,
                    "reason": "execution_result is not dict",
                },
            }

        enriched = dict(result)
        verification = self._verify_execution_result(result)

        # 只附加，不覆蓋主幹資料
        enriched["verification"] = verification

        # 不去改 final_answer，不去改 last_result，不去洗 results
        # 只有在 execution_result 本身沒有 ok 時，才補一個
        if "ok" not in enriched:
            enriched["ok"] = bool(verification.get("verified", False))

        return enriched

    # ------------------------------------------------------------
    # internal
    # ------------------------------------------------------------

    def _verify_execution_result(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        results = execution_result.get("results")
        if not isinstance(results, list):
            results = []

        if not results:
            overall_ok = bool(execution_result.get("ok", False))
            return {
                "verified": overall_ok,
                "reason": "no step results; used top-level ok",
                "failed_steps": [],
                "step_count": 0,
            }

        failed_steps: List[Dict[str, Any]] = []

        for item in results:
            if not isinstance(item, dict):
                failed_steps.append(
                    {
                        "step_index": None,
                        "reason": "step result is not dict",
                    }
                )
                continue

            step_index = item.get("step_index")
            inner_result = item.get("result")

            step_ok = self._extract_step_ok(inner_result)
            if not step_ok:
                failed_steps.append(
                    {
                        "step_index": step_index,
                        "reason": self._extract_step_reason(inner_result),
                        "result": inner_result,
                    }
                )

        verified = len(failed_steps) == 0

        return {
            "verified": verified,
            "reason": "all steps passed" if verified else f"{len(failed_steps)} step(s) failed",
            "failed_steps": failed_steps,
            "step_count": len(results),
        }

    def _extract_step_ok(self, step_result: Any) -> bool:
        if isinstance(step_result, dict):
            if "ok" in step_result:
                return bool(step_result.get("ok"))
            if "success" in step_result:
                return bool(step_result.get("success"))
            if "status" in step_result:
                status = str(step_result.get("status", "") or "").strip().lower()
                return status in {"ok", "success", "done", "passed", "completed", "finished"}
        return False

    def _extract_step_reason(self, step_result: Any) -> str:
        if not isinstance(step_result, dict):
            return "step result is not dict"

        error = step_result.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()

        status = str(step_result.get("status", "") or "").strip()
        if status:
            return f"status={status}"

        return "step reported failure"