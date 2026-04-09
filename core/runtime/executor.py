from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import time

from core.runtime.trace_logger import ensure_trace_logger
from core.runtime.verifier import Verifier


class Executor:
    """
    Executor

    目前版本功能：
    1. 逐步執行 plan["steps"]
    2. 支援 step retry
    3. 執行後做 verifier / correction
    4. retry exhausted 後可進入 replan
    5. 空 plan 不再直接算成功
    6. planner replan 無效時，使用 deterministic fallback plan
    7. executor 可做強制修正（forced repair）
    8. 寫入 execution / verifier / correction / lifecycle trace
    """

    SUCCESS_STATUSES = {"done", "success", "ok", "passed"}

    def __init__(
        self,
        workspace_root: Path | str = "workspace",
        trace_logger: Optional[Any] = None,
        verifier: Optional[Verifier] = None,
        planner: Optional[Any] = None,
        default_retry_limit: int = 1,
        retry_delay_seconds: float = 0.0,
        max_replan_rounds: int = 1,
        enable_forced_repair: bool = True,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.trace_logger = ensure_trace_logger(trace_logger)
        self.verifier = verifier or Verifier(trace_logger=self.trace_logger)
        self.planner = planner

        self.default_retry_limit = max(0, int(default_retry_limit))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self.max_replan_rounds = max(0, int(max_replan_rounds))
        self.enable_forced_repair = bool(enable_forced_repair)

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
        執行整個 Plan，必要時進行 replan / forced repair。
        """
        self.trace_logger.set_task(task_name)
        self.trace_logger.mark_start(
            title="execute agent loop start",
            message=f"task={task_name}, iteration={iteration}",
            source="executor",
            raw={
                "task_name": task_name,
                "iteration": iteration,
                "initial_plan": plan,
                "max_replan_rounds": self.max_replan_rounds,
                "enable_forced_repair": self.enable_forced_repair,
            },
        )

        current_plan = dict(plan or {})
        current_iteration = iteration
        replan_round = 0

        rounds: List[Dict[str, Any]] = []
        replan_history: List[Dict[str, Any]] = []

        final_round_result: Dict[str, Any] = {}
        final_verify_result: Dict[str, Any] = {}
        final_needs_correction = False

        while True:
            round_result = self._execute_single_round(
                task_name=task_name,
                plan=current_plan,
                iteration=current_iteration,
                replan_round=replan_round,
            )
            rounds.append(round_result)

            verify_result = round_result.get("verify_result", {}) or {}
            needs_correction = bool(round_result.get("needs_correction", False))

            final_round_result = round_result
            final_verify_result = verify_result
            final_needs_correction = needs_correction

            if not needs_correction:
                self.trace_logger.log_correction(
                    title="agent loop stop",
                    message=f"round={replan_round}, no correction needed",
                    status="success",
                    source="correction",
                    raw={
                        "task_name": task_name,
                        "replan_round": replan_round,
                        "verify_result": verify_result,
                    },
                )
                break

            if replan_round >= self.max_replan_rounds:
                self.trace_logger.log_correction(
                    title="replan exhausted",
                    message=f"replan exhausted at round {replan_round}",
                    status="failed",
                    source="correction",
                    raw={
                        "task_name": task_name,
                        "replan_round": replan_round,
                        "max_replan_rounds": self.max_replan_rounds,
                        "verify_result": verify_result,
                    },
                )
                break

            replanned = self._replan(
                task_name=task_name,
                failed_verify_result=verify_result,
                previous_plan=current_plan,
                previous_round_result=round_result,
                next_iteration=current_iteration + 1,
                next_replan_round=replan_round + 1,
            )

            replan_history.append(replanned)

            new_plan = replanned.get("plan")
            if not new_plan or not isinstance(new_plan, dict):
                self.trace_logger.log_correction(
                    title="replan failed",
                    message="planner did not return a valid plan",
                    status="failed",
                    source="correction",
                    raw={
                        "task_name": task_name,
                        "replan_round": replan_round + 1,
                        "replanned": replanned,
                    },
                )
                break

            current_plan = new_plan
            current_iteration += 1
            replan_round += 1

        final_result = {
            "task_name": task_name,
            "iteration": iteration,
            "final_iteration": current_iteration,
            "replan_rounds_used": replan_round,
            "success": not final_needs_correction,
            "needs_correction": final_needs_correction,
            "final_round_result": final_round_result,
            "final_verify_result": final_verify_result,
            "rounds": rounds,
            "replan_history": replan_history,
        }

        self.trace_logger.mark_end(
            title="execute agent loop end",
            message=f"task={task_name}, success={final_result['success']}, replan_rounds_used={replan_round}",
            status="success" if final_result["success"] else "failed",
            source="executor",
            raw=final_result,
        )

        self.trace_logger.flush()
        return final_result

    # =========================================================
    # Single round
    # =========================================================

    def _execute_single_round(
        self,
        task_name: str,
        plan: Dict[str, Any],
        iteration: int,
        replan_round: int,
    ) -> Dict[str, Any]:
        original_steps: List[Dict[str, Any]] = plan.get("steps", []) or []
        normalized_steps = self._normalize_plan_steps(task_name=task_name, steps=original_steps)

        results: List[Dict[str, Any]] = []
        retry_summary: List[Dict[str, Any]] = []

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        self.trace_logger.mark_start(
            title="execute round start",
            message=f"task={task_name}, iteration={iteration}, replan_round={replan_round}, step_count={len(normalized_steps)}",
            source="executor",
            raw={
                "task_name": task_name,
                "iteration": iteration,
                "replan_round": replan_round,
                "original_step_count": len(original_steps),
                "normalized_step_count": len(normalized_steps),
                "original_plan": plan,
                "normalized_steps": normalized_steps,
            },
        )

        if not normalized_steps:
            round_result = {
                "task_name": task_name,
                "iteration": iteration,
                "replan_round": replan_round,
                "results": [],
                "success": False,
                "retry_summary": [],
                "plan": plan,
                "normalized_steps": normalized_steps,
                "empty_plan": True,
            }

            self.trace_logger.log_correction(
                title="empty plan detected",
                message="plan contains zero executable steps",
                status="failed",
                source="correction",
                raw={
                    "task_name": task_name,
                    "iteration": iteration,
                    "replan_round": replan_round,
                    "plan": plan,
                },
            )

            self.trace_logger.mark_end(
                title="execute round end",
                message=f"task={task_name}, iteration={iteration}, replan_round={replan_round}, empty_plan=True",
                status="failed",
                source="executor",
                raw=round_result,
            )

            verify_result = {
                "task_name": task_name,
                "passed": False,
                "step_checks": [],
                "failed_steps": [
                    {
                        "step": None,
                        "action": "empty_plan",
                        "status": "failed",
                        "passed": False,
                        "reason": "replanned plan is empty",
                        "step_result": {},
                    }
                ],
                "correction": {
                    "needs_correction": True,
                    "action": "replan_again",
                    "reason": "empty_plan",
                    "failed_steps": [
                        {
                            "step": None,
                            "action": "empty_plan",
                            "status": "failed",
                            "passed": False,
                            "reason": "replanned plan is empty",
                            "step_result": {},
                        }
                    ],
                },
            }

            self.trace_logger.log_verifier(
                title="verify execution result end",
                message="passed=False because empty plan",
                status="failed",
                source="verifier",
                raw=verify_result,
            )

            round_result["verify_result"] = verify_result
            round_result["needs_correction"] = True
            return round_result

        overall_success = True

        for index, step in enumerate(normalized_steps, start=1):
            result = self._execute_step_with_retry(task_name, index, step)
            results.append(result)

            retry_info = result.get("retry_info", {})
            if retry_info:
                retry_summary.append(retry_info)

            if result.get("status") not in self.SUCCESS_STATUSES:
                overall_success = False

        round_result = {
            "task_name": task_name,
            "iteration": iteration,
            "replan_round": replan_round,
            "results": results,
            "success": overall_success,
            "retry_summary": retry_summary,
            "plan": plan,
            "normalized_steps": normalized_steps,
            "empty_plan": False,
        }

        self.trace_logger.mark_end(
            title="execute round end",
            message=f"task={task_name}, iteration={iteration}, replan_round={replan_round}, success={overall_success}",
            status="success" if overall_success else "partial_failed",
            source="executor",
            raw=round_result,
        )

        verify_result = self.verifier.verify_execution_result(
            task_name=task_name,
            execution_result=round_result,
        )

        round_result["verify_result"] = verify_result
        round_result["needs_correction"] = bool(
            verify_result.get("correction", {}).get("needs_correction", False)
        )
        return round_result

    # =========================================================
    # Forced repair / plan normalization
    # =========================================================

    def _normalize_plan_steps(
        self,
        task_name: str,
        steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self.enable_forced_repair:
            return list(steps or [])

        normalized: List[Dict[str, Any]] = []
        known_files = set()

        for step in steps or []:
            if not isinstance(step, dict):
                continue

            step_type = str(step.get("type") or step.get("action") or "").strip().lower()
            path = str(step.get("path", "") or "").strip().replace("\\", "/")

            if step_type == "write_file" and path:
                normalized.append(dict(step))
                known_files.add(path)
                continue

            if step_type == "read_file" and path:
                path_exists = self._path_exists_for_task(task_name=task_name, path=path)
                if not path_exists and path not in known_files:
                    forced_write = self._build_forced_write_before_read(path=path)
                    normalized.append(forced_write)
                    known_files.add(path)

                    self.trace_logger.log_correction(
                        title="forced repair insert write before read",
                        message=f"inserted write_file before read_file for {path}",
                        status="forced_repair",
                        source="correction",
                        raw={
                            "task_name": task_name,
                            "original_step": step,
                            "inserted_step": forced_write,
                        },
                    )

                normalized.append(dict(step))
                continue

            normalized.append(dict(step))

        return normalized

    def _build_forced_write_before_read(self, path: str) -> Dict[str, Any]:
        return {
            "type": "write_file",
            "path": path,
            "title": f"forced repair create {path}",
            "message": f"executor forced repair inserted create step before reading {path}",
            "status": "done",
        }

    def _path_exists_for_task(self, task_name: str, path: str) -> bool:
        normalized = str(path or "").strip().replace("\\", "/")
        if not normalized:
            return False

        direct = Path(normalized)
        if direct.is_absolute():
            return direct.exists()

        candidate_1 = self.workspace_root / task_name / normalized
        candidate_2 = self.workspace_root / normalized
        return candidate_1.exists() or candidate_2.exists()

    # =========================================================
    # Replan
    # =========================================================

    def _replan(
        self,
        task_name: str,
        failed_verify_result: Dict[str, Any],
        previous_plan: Dict[str, Any],
        previous_round_result: Dict[str, Any],
        next_iteration: int,
        next_replan_round: int,
    ) -> Dict[str, Any]:
        failed_steps = failed_verify_result.get("failed_steps", []) or []

        self.trace_logger.log_correction(
            title="replan requested",
            message=f"failed_steps={len(failed_steps)}, next_round={next_replan_round}",
            status="replanning",
            source="correction",
            raw={
                "task_name": task_name,
                "failed_steps": failed_steps,
                "previous_plan": previous_plan,
                "previous_round_result": previous_round_result,
                "next_iteration": next_iteration,
                "next_replan_round": next_replan_round,
            },
        )

        replan_input = self._build_replan_input(
            task_name=task_name,
            failed_steps=failed_steps,
            previous_plan=previous_plan,
            previous_round_result=previous_round_result,
        )

        self.trace_logger.log_decision(
            title="replan input",
            message=replan_input,
            source="planner",
            raw={
                "task_name": task_name,
                "failed_steps": failed_steps,
                "next_iteration": next_iteration,
                "next_replan_round": next_replan_round,
            },
        )

        replanned_plan: Dict[str, Any] = {}

        if self.planner is not None:
            context = {
                "workspace": task_name,
                "user_input": replan_input,
                "failed_steps": failed_steps,
                "previous_plan": previous_plan,
                "previous_round_result": previous_round_result,
                "replan_round": next_replan_round,
            }

            try:
                replanned_plan = self.planner.plan(
                    context=context,
                    user_input=replan_input,
                )
            except Exception as exc:
                self.trace_logger.log_error(
                    event_type="decision",
                    title="planner replan failed",
                    message=str(exc),
                    source="planner",
                    error=exc,
                    raw={
                        "task_name": task_name,
                        "replan_input": replan_input,
                        "next_iteration": next_iteration,
                        "next_replan_round": next_replan_round,
                    },
                )
                replanned_plan = {}

        planner_steps = replanned_plan.get("steps", []) if isinstance(replanned_plan, dict) else []
        used_fallback = False

        if not planner_steps:
            fallback_plan = self._build_fallback_replan_plan(
                task_name=task_name,
                failed_steps=failed_steps,
                previous_plan=previous_plan,
                previous_round_result=previous_round_result,
            )
            replanned_plan = fallback_plan
            used_fallback = True

            self.trace_logger.log_correction(
                title="fallback replan used",
                message=f"fallback_steps={len(fallback_plan.get('steps', []))}",
                status="fallback",
                source="correction",
                raw={
                    "task_name": task_name,
                    "failed_steps": failed_steps,
                    "fallback_plan": fallback_plan,
                },
            )

        self.trace_logger.log_decision(
            title="replan result",
            message=f"replanned_steps={len(replanned_plan.get('steps', []))}, used_fallback={used_fallback}",
            source="planner",
            raw={
                "task_name": task_name,
                "replanned_plan": replanned_plan,
                "used_fallback": used_fallback,
                "next_iteration": next_iteration,
                "next_replan_round": next_replan_round,
            },
        )

        return {
            "task_name": task_name,
            "next_iteration": next_iteration,
            "next_replan_round": next_replan_round,
            "input": replan_input,
            "failed_steps": failed_steps,
            "plan": replanned_plan,
            "used_fallback": used_fallback,
        }

    def _build_replan_input(
        self,
        task_name: str,
        failed_steps: List[Dict[str, Any]],
        previous_plan: Dict[str, Any],
        previous_round_result: Dict[str, Any],
    ) -> str:
        if not failed_steps:
            return (
                f"請重新規劃任務 {task_name}。"
                f" 必須輸出至少一個可執行步驟，不能是空計畫。"
            )

        first = failed_steps[0]
        step_result = first.get("step_result", {}) or {}
        action = step_result.get("action") or first.get("action") or "unknown_action"
        title = step_result.get("title") or ""
        reason = first.get("reason", "unknown_reason")

        if action == "read_file":
            target = self._extract_target_name_from_failed_step(step_result=step_result, fallback_title=title)
            return (
                f"請重新規劃任務 {task_name}。"
                f" 目前失敗步驟是讀取檔案，原因：{reason}。"
                f" 請先建立 {target}，然後再讀取 {target}。"
                f" 必須輸出至少 2 個步驟，不能是空計畫。"
            )

        if action == "write_file":
            target = self._extract_target_name_from_failed_step(step_result=step_result, fallback_title=title)
            return (
                f"請重新規劃任務 {task_name}。"
                f" 目前失敗步驟是建立檔案，原因：{reason}。"
                f" 請重新建立 {target}。"
                f" 必須輸出至少 1 個步驟，不能是空計畫。"
            )

        if action == "empty_plan":
            return (
                f"請重新規劃任務 {task_name}。"
                f" 上一輪產生了空計畫。"
                f" 請輸出至少一個可執行步驟，不能是空計畫。"
            )

        return (
            f"請重新規劃任務 {task_name}。"
            f" 失敗動作={action}，原因={reason}。"
            f" 請輸出至少一個可執行步驟，不能是空計畫。"
        )

    def _build_fallback_replan_plan(
        self,
        task_name: str,
        failed_steps: List[Dict[str, Any]],
        previous_plan: Dict[str, Any],
        previous_round_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not failed_steps:
            return {
                "planner_mode": "executor_fallback",
                "intent": "respond",
                "final_answer": "fallback replan generated",
                "steps": [
                    {
                        "type": "write_file",
                        "path": "recovered.txt",
                        "title": "fallback create recovered.txt",
                        "message": "executor fallback created recovery file",
                        "status": "done",
                    },
                    {
                        "type": "read_file",
                        "path": "recovered.txt",
                        "title": "fallback read recovered.txt",
                        "message": "executor fallback read recovery file",
                        "status": "done",
                    },
                ],
            }

        first = failed_steps[0]
        step_result = first.get("step_result", {}) or {}
        action = step_result.get("action") or first.get("action") or ""
        title = step_result.get("title") or ""

        target = self._extract_target_name_from_failed_step(step_result=step_result, fallback_title=title)

        if action == "read_file":
            return {
                "planner_mode": "executor_fallback",
                "intent": "read_file",
                "final_answer": "fallback replan generated for failed read",
                "steps": [
                    {
                        "type": "write_file",
                        "path": target,
                        "title": f"fallback create {target}",
                        "message": f"create missing file {target} before read",
                        "status": "done",
                    },
                    {
                        "type": "read_file",
                        "path": target,
                        "title": f"fallback read {target}",
                        "message": f"read file {target} after create",
                        "status": "done",
                    },
                ],
            }

        if action == "write_file":
            return {
                "planner_mode": "executor_fallback",
                "intent": "write_file",
                "final_answer": "fallback replan generated for failed write",
                "steps": [
                    {
                        "type": "write_file",
                        "path": target,
                        "title": f"fallback rewrite {target}",
                        "message": f"rewrite file {target}",
                        "status": "done",
                    }
                ],
            }

        return {
            "planner_mode": "executor_fallback",
            "intent": "respond",
            "final_answer": "generic fallback replan generated",
            "steps": [
                {
                    "type": "write_file",
                    "path": "recovered.txt",
                    "title": "generic fallback create recovered.txt",
                    "message": "generic fallback recovery step",
                    "status": "done",
                }
            ],
        }

    def _extract_target_name_from_failed_step(
        self,
        step_result: Dict[str, Any],
        fallback_title: str = "",
    ) -> str:
        path = str(step_result.get("path", "") or "").strip()
        if path:
            return path.replace("\\", "/")

        title = str(fallback_title or "").strip()
        if title:
            lowered = title.lower()
            if lowered.endswith(".txt") or lowered.endswith(".md") or lowered.endswith(".json") or lowered.endswith(".py"):
                return title

        return "hello.txt"

    # =========================================================
    # Retry wrapper
    # =========================================================

    def _execute_step_with_retry(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        retry_limit = self._get_retry_limit(step)
        attempt = 0
        history: List[Dict[str, Any]] = []

        while True:
            attempt += 1

            if attempt > 1:
                self.trace_logger.log_correction(
                    step_id=f"step_{step_index:02d}",
                    title="retry step",
                    message=f"retry attempt={attempt} / max={retry_limit + 1}",
                    status="retrying",
                    source="correction",
                    raw={
                        "task_name": task_name,
                        "step_index": step_index,
                        "attempt": attempt,
                        "max_attempts": retry_limit + 1,
                        "step": step,
                    },
                )

            step_for_attempt = self._build_step_for_attempt(step=step, attempt=attempt)
            result = self._execute_step(task_name, step_index, step_for_attempt)

            history.append(
                {
                    "attempt": attempt,
                    "status": result.get("status"),
                    "output": result.get("output"),
                }
            )

            if result.get("status") in self.SUCCESS_STATUSES:
                if attempt > 1:
                    self.trace_logger.log_correction(
                        step_id=f"step_{step_index:02d}",
                        title="retry recovered",
                        message=f"step recovered on attempt {attempt}",
                        status="success",
                        source="correction",
                        raw={
                            "task_name": task_name,
                            "step_index": step_index,
                            "attempt": attempt,
                            "history": history,
                        },
                    )

                result["retry_info"] = {
                    "used_retry": attempt > 1,
                    "attempts": attempt,
                    "retry_limit": retry_limit,
                    "recovered": attempt > 1,
                    "history": history,
                }
                return result

            if attempt > retry_limit:
                self.trace_logger.log_correction(
                    step_id=f"step_{step_index:02d}",
                    title="retry exhausted",
                    message=f"retry exhausted after {attempt} attempts",
                    status="failed",
                    source="correction",
                    raw={
                        "task_name": task_name,
                        "step_index": step_index,
                        "attempts": attempt,
                        "retry_limit": retry_limit,
                        "history": history,
                        "step": step,
                    },
                )

                result["retry_info"] = {
                    "used_retry": attempt > 1,
                    "attempts": attempt,
                    "retry_limit": retry_limit,
                    "recovered": False,
                    "history": history,
                }
                return result

            if self.retry_delay_seconds > 0:
                time.sleep(self.retry_delay_seconds)

    def _get_retry_limit(self, step: Dict[str, Any]) -> int:
        raw = step.get("retry_limit", self.default_retry_limit)
        try:
            return max(0, int(raw))
        except Exception:
            return self.default_retry_limit

    def _build_step_for_attempt(self, step: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        step_copy = dict(step)
        step_copy["_attempt"] = attempt

        fail_until_attempt = step_copy.get("fail_until_attempt")
        if fail_until_attempt is not None:
            try:
                fail_until = int(fail_until_attempt)
            except Exception:
                fail_until = 0
            step_copy["force_error"] = attempt <= fail_until

        return step_copy

    # =========================================================
    # Internal
    # =========================================================

    def _execute_step(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        action = step.get("action") or step.get("type") or ""
        title = step.get("title") or step.get("name") or f"step_{step_index}"
        message = step.get("message") or step.get("description") or ""
        output = step.get("output") or f"Executed step {step_index}"
        attempt = int(step.get("_attempt", 1) or 1)
        path = str(step.get("path", "") or "").strip()

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.trace_logger.log_execution(
                step_id=f"step_{step_index:02d}",
                status="start",
                title=title,
                message=message or f"start action={action}",
                source="executor",
                raw={
                    "task_name": task_name,
                    "step_index": step_index,
                    "attempt": attempt,
                    "step": step,
                },
            )

            if bool(step.get("force_error", False)):
                raise RuntimeError(f"forced error at step {step_index} attempt {attempt}")

            normalized_status = str(step.get("status", "done") or "done").strip().lower()
            if not normalized_status:
                normalized_status = "done"

            step_result = {
                "step": step_index,
                "action": action,
                "path": path,
                "title": title,
                "message": message,
                "status": normalized_status,
                "output": output,
                "attempt": attempt,
            }

            step_file = task_dir / f"step_{step_index:02d}.json"
            with open(step_file, "w", encoding="utf-8") as f:
                json.dump(step_result, f, indent=2, ensure_ascii=False)

            self.trace_logger.log_execution(
                step_id=f"step_{step_index:02d}",
                status="success" if normalized_status in self.SUCCESS_STATUSES else normalized_status,
                title=title,
                message=f"step file saved: {step_file}",
                source="executor",
                raw={
                    "task_name": task_name,
                    "step_index": step_index,
                    "attempt": attempt,
                    "step_file": str(step_file),
                    "step_result": step_result,
                },
            )

            return step_result

        except Exception as exc:
            error_result = {
                "step": step_index,
                "action": action,
                "path": path,
                "title": title,
                "message": message,
                "status": "error",
                "output": str(exc),
                "attempt": attempt,
            }

            self.trace_logger.log_error(
                event_type="execution",
                step_id=f"step_{step_index:02d}",
                title=title,
                message=f"execute step failed: {exc}",
                source="executor",
                error=exc,
                raw={
                    "task_name": task_name,
                    "step_index": step_index,
                    "attempt": attempt,
                    "step": step,
                    "error_result": error_result,
                },
            )

            return error_result