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

    第一輪內部收束版：
    - 不改外部主線行為
    - 先收 retry / repair / step execution 的內部責任
    - 保持目前 smoke tests 可過
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
            round_result = self._build_empty_plan_round_result(
                task_name=task_name,
                iteration=iteration,
                replan_round=replan_round,
                plan=plan,
                normalized_steps=normalized_steps,
            )
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

    def _build_empty_plan_round_result(
        self,
        task_name: str,
        iteration: int,
        replan_round: int,
        plan: Dict[str, Any],
        normalized_steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
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
        known_dirs = set()

        for step in steps or []:
            if not isinstance(step, dict):
                continue

            step_copy = dict(step)
            step_type = str(step_copy.get("type") or step_copy.get("action") or "").strip().lower()
            path = str(step_copy.get("path", "") or "").strip().replace("\\", "/")

            if step_type == "mkdir" and path:
                normalized.append(step_copy)
                known_dirs.add(path)
                continue

            if step_type == "write_file" and path:
                dir_steps = self._build_missing_dir_repairs(
                    task_name=task_name,
                    path=path,
                    known_dirs=known_dirs,
                )
                normalized.extend(dir_steps)
                normalized.append(step_copy)

                known_files.add(path)
                parent_dir = self._parent_dir(path)
                if parent_dir:
                    known_dirs.add(parent_dir)
                continue

            if step_type == "read_file" and path:
                dir_steps = self._build_missing_dir_repairs(
                    task_name=task_name,
                    path=path,
                    known_dirs=known_dirs,
                )
                normalized.extend(dir_steps)

                path_exists = self._path_exists_for_task(task_name=task_name, path=path)
                if not path_exists and path not in known_files:
                    forced_write = self._build_forced_write_before_read(path=path)
                    normalized.append(forced_write)
                    known_files.add(path)

                    parent_dir = self._parent_dir(path)
                    if parent_dir:
                        known_dirs.add(parent_dir)

                    self.trace_logger.log_correction(
                        title="forced repair insert write before read",
                        message=f"inserted write_file before read_file for {path}",
                        status="forced_repair",
                        source="correction",
                        raw={
                            "task_name": task_name,
                            "original_step": step_copy,
                            "inserted_step": forced_write,
                        },
                    )

                normalized.append(step_copy)
                continue

            normalized.append(step_copy)

        return normalized

    def _build_missing_dir_repairs(
        self,
        task_name: str,
        path: str,
        known_dirs: set,
    ) -> List[Dict[str, Any]]:
        repairs: List[Dict[str, Any]] = []
        parent_dir = self._parent_dir(path)

        if not parent_dir:
            return repairs

        if parent_dir in known_dirs:
            return repairs

        if self._dir_exists_for_task(task_name=task_name, path=parent_dir):
            known_dirs.add(parent_dir)
            return repairs

        mkdir_step = {
            "type": "mkdir",
            "path": parent_dir,
            "title": f"forced repair mkdir {parent_dir}",
            "message": f"executor inserted mkdir for missing directory {parent_dir}",
            "status": "done",
        }
        repairs.append(mkdir_step)
        known_dirs.add(parent_dir)

        self.trace_logger.log_correction(
            title="forced repair insert mkdir",
            message=f"inserted mkdir for {parent_dir}",
            status="forced_repair",
            source="correction",
            raw={
                "task_name": task_name,
                "path": path,
                "inserted_step": mkdir_step,
            },
        )

        return repairs

    def _build_forced_write_before_read(self, path: str) -> Dict[str, Any]:
        return {
            "type": "write_file",
            "path": path,
            "title": f"forced repair create {path}",
            "message": f"executor forced repair inserted create step before reading {path}",
            "status": "done",
        }

    def _parent_dir(self, path: str) -> str:
        normalized = str(path or "").strip().replace("\\", "/")
        if not normalized or "/" not in normalized:
            return ""
        return normalized.rsplit("/", 1)[0].strip("/")

    # =========================================================
    # Safe path
    # =========================================================

    def _resolve_safe_path(self, task_name: str, path: str) -> Path:
        normalized = str(path or "").strip().replace("\\", "/")

        if not normalized:
            raise ValueError("empty path")

        raw_path = Path(normalized)

        if raw_path.is_absolute():
            raise ValueError(f"absolute path not allowed: {normalized}")

        parts = [part for part in raw_path.parts if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise ValueError(f"path traversal not allowed: {normalized}")

        task_root = (self.workspace_root / task_name).resolve()
        task_root.mkdir(parents=True, exist_ok=True)

        safe_path = (task_root / Path(*parts)).resolve()

        try:
            safe_path.relative_to(task_root)
        except ValueError as exc:
            raise ValueError(f"unsafe path detected: {normalized}") from exc

        return safe_path

    def _path_exists_for_task(self, task_name: str, path: str) -> bool:
        normalized = str(path or "").strip().replace("\\", "/")
        if not normalized:
            return False

        try:
            safe_path = self._resolve_safe_path(task_name=task_name, path=normalized)
        except Exception:
            return False

        return safe_path.exists()

    def _dir_exists_for_task(self, task_name: str, path: str) -> bool:
        normalized = str(path or "").strip().replace("\\", "/")
        if not normalized:
            return True

        try:
            safe_path = self._resolve_safe_path(task_name=task_name, path=normalized)
        except Exception:
            return False

        return safe_path.exists() and safe_path.is_dir()

    def _build_safe_fallback_path(self, task_name: str, original_path: str) -> str:
        normalized = str(original_path or "").strip().replace("\\", "/")
        filename = normalized.rsplit("/", 1)[-1] if normalized else "output.txt"
        if not filename:
            filename = "output.txt"
        return f"_repaired/{filename}"

    def _ensure_dir_for_task(self, task_name: str, path: str) -> None:
        normalized = str(path or "").strip().replace("\\", "/")
        if not normalized:
            return

        safe_dir = self._resolve_safe_path(task_name=task_name, path=normalized)
        safe_dir.mkdir(parents=True, exist_ok=True)

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
            if (
                lowered.endswith(".txt")
                or lowered.endswith(".md")
                or lowered.endswith(".json")
                or lowered.endswith(".py")
            ):
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
                self._log_retry_start(
                    task_name=task_name,
                    step_index=step_index,
                    attempt=attempt,
                    retry_limit=retry_limit,
                    step=step,
                )

            step_for_attempt = self._build_step_for_attempt(step=step, attempt=attempt)
            result = self._execute_step(task_name, step_index, step_for_attempt)

            if self._should_try_safe_path_repair(step=step_for_attempt, result=result):
                repaired_result = self._try_write_safe_path_repair(
                    task_name=task_name,
                    step_index=step_index,
                    step=step_for_attempt,
                    failed_result=result,
                )
                if repaired_result is not None:
                    result = repaired_result

            history.append(self._build_retry_history_item(attempt=attempt, result=result))

            if result.get("status") in self.SUCCESS_STATUSES:
                if attempt > 1:
                    self._log_retry_recovered(
                        task_name=task_name,
                        step_index=step_index,
                        attempt=attempt,
                        history=history,
                    )

                result["retry_info"] = self._build_retry_info(
                    attempt=attempt,
                    retry_limit=retry_limit,
                    recovered=(attempt > 1),
                    history=history,
                )
                return result

            if attempt > retry_limit:
                self._log_retry_exhausted(
                    task_name=task_name,
                    step_index=step_index,
                    attempt=attempt,
                    retry_limit=retry_limit,
                    history=history,
                    step=step,
                )

                result["retry_info"] = self._build_retry_info(
                    attempt=attempt,
                    retry_limit=retry_limit,
                    recovered=False,
                    history=history,
                )
                return result

            if self.retry_delay_seconds > 0:
                time.sleep(self.retry_delay_seconds)

    def _should_try_safe_path_repair(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
    ) -> bool:
        if not self.enable_forced_repair:
            return False

        action = str(step.get("action") or step.get("type") or "").strip().lower()
        if action != "write_file":
            return False

        return result.get("status") == "error"

    def _build_retry_history_item(
        self,
        attempt: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "attempt": attempt,
            "status": result.get("status"),
            "output": result.get("output"),
            "path": result.get("path", ""),
            "resolved_path": result.get("resolved_path", ""),
        }

    def _build_retry_info(
        self,
        attempt: int,
        retry_limit: int,
        recovered: bool,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "used_retry": attempt > 1,
            "attempts": attempt,
            "retry_limit": retry_limit,
            "recovered": recovered,
            "history": history,
        }

    def _log_retry_start(
        self,
        task_name: str,
        step_index: int,
        attempt: int,
        retry_limit: int,
        step: Dict[str, Any],
    ) -> None:
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

    def _log_retry_recovered(
        self,
        task_name: str,
        step_index: int,
        attempt: int,
        history: List[Dict[str, Any]],
    ) -> None:
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

    def _log_retry_exhausted(
        self,
        task_name: str,
        step_index: int,
        attempt: int,
        retry_limit: int,
        history: List[Dict[str, Any]],
        step: Dict[str, Any],
    ) -> None:
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

    # =========================================================
    # Safe path repair
    # =========================================================

    def _try_write_safe_path_repair(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
        failed_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        action = str(step.get("action") or step.get("type") or "").strip().lower()
        path = str(step.get("path", "") or "").strip().replace("\\", "/")

        if action != "write_file":
            return None

        if not path:
            return None

        fallback_path = self._build_safe_fallback_path(task_name=task_name, original_path=path)
        repaired_step = self._build_safe_path_repaired_step(step=step, fallback_path=fallback_path, original_path=path)

        self.trace_logger.log_correction(
            step_id=f"step_{step_index:02d}",
            title="write safe path repair",
            message=f"redirect write_file from {path} to {fallback_path}",
            status="forced_repair",
            source="correction",
            raw={
                "task_name": task_name,
                "step_index": step_index,
                "original_path": path,
                "fallback_path": fallback_path,
                "failed_result": failed_result,
            },
        )

        repaired_result = self._execute_step(task_name, step_index, repaired_step)
        if repaired_result.get("status") in self.SUCCESS_STATUSES:
            repaired_result["repaired_from_path"] = path
            repaired_result["repair_type"] = "safe_path_fallback"
            return repaired_result

        return None

    def _build_safe_path_repaired_step(
        self,
        step: Dict[str, Any],
        fallback_path: str,
        original_path: str,
    ) -> Dict[str, Any]:
        repaired_step = dict(step)
        repaired_step["path"] = fallback_path
        repaired_step["title"] = f"safe-path repair write {fallback_path}"
        repaired_step["message"] = f"executor redirected write_file from {original_path} to safe path {fallback_path}"
        repaired_step["status"] = "done"
        repaired_step["force_error"] = False
        repaired_step["simulate_write_failure"] = False
        return repaired_step

    # =========================================================
    # Retry config
    # =========================================================

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
    # Internal execution
    # =========================================================

    def _execute_step(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        action = str(step.get("action") or step.get("type") or "").strip().lower()
        title = step.get("title") or step.get("name") or f"step_{step_index}"
        message = step.get("message") or step.get("description") or ""
        output = step.get("output") or f"Executed step {step_index}"
        attempt = int(step.get("_attempt", 1) or 1)
        raw_path = str(step.get("path", "") or "").strip().replace("\\", "/")

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        safe_path, path_error = self._resolve_step_safe_path(
            task_name=task_name,
            raw_path=raw_path,
        )
        if path_error is not None:
            error_result = self._build_step_error_result(
                step_index=step_index,
                action=action,
                path=raw_path,
                resolved_path="",
                title=title,
                message=message,
                error_message=f"unsafe_path: {path_error}",
                attempt=attempt,
            )
            self._log_step_error(
                task_name=task_name,
                step_index=step_index,
                title=title,
                message=f"unsafe path rejected: {path_error}",
                step=step,
                error=path_error,
                error_result=error_result,
                attempt=attempt,
            )
            return error_result

        try:
            self._log_step_start(
                task_name=task_name,
                step_index=step_index,
                title=title,
                message=message or f"start action={action}",
                step=step,
                attempt=attempt,
            )

            if bool(step.get("force_error", False)):
                raise RuntimeError(f"forced error at step {step_index} attempt {attempt}")

            normalized_status = str(step.get("status", "done") or "done").strip().lower()
            if not normalized_status:
                normalized_status = "done"

            output = self._execute_step_action(
                action=action,
                step=step,
                task_name=task_name,
                raw_path=raw_path,
                safe_path=safe_path,
                default_output=output,
            )

            step_result = self._build_step_success_result(
                step_index=step_index,
                action=action,
                path=raw_path,
                resolved_path=str(safe_path) if safe_path is not None else "",
                title=title,
                message=message,
                status=normalized_status,
                output=output,
                attempt=attempt,
            )

            step_file = self._write_step_result_file(
                task_dir=task_dir,
                step_index=step_index,
                step_result=step_result,
            )

            self._log_step_success(
                task_name=task_name,
                step_index=step_index,
                title=title,
                step_file=step_file,
                step_result=step_result,
                attempt=attempt,
                normalized_status=normalized_status,
            )

            return step_result

        except Exception as exc:
            error_result = self._build_step_error_result(
                step_index=step_index,
                action=action,
                path=raw_path,
                resolved_path=str(safe_path) if safe_path is not None else "",
                title=title,
                message=message,
                error_message=str(exc),
                attempt=attempt,
            )

            self._log_step_error(
                task_name=task_name,
                step_index=step_index,
                title=title,
                message=f"execute step failed: {exc}",
                step=step,
                error=exc,
                error_result=error_result,
                attempt=attempt,
            )

            return error_result

    def _resolve_step_safe_path(
        self,
        task_name: str,
        raw_path: str,
    ) -> tuple[Optional[Path], Optional[Exception]]:
        if not raw_path:
            return None, None

        try:
            return self._resolve_safe_path(task_name=task_name, path=raw_path), None
        except Exception as exc:
            return None, exc

    def _execute_step_action(
        self,
        action: str,
        step: Dict[str, Any],
        task_name: str,
        raw_path: str,
        safe_path: Optional[Path],
        default_output: Any,
    ) -> Any:
        if action == "mkdir":
            if safe_path is None:
                raise ValueError("mkdir requires path")
            safe_path.mkdir(parents=True, exist_ok=True)
            return default_output

        if action == "write_file":
            if safe_path is None:
                raise ValueError("write_file requires path")

            safe_path.parent.mkdir(parents=True, exist_ok=True)

            if bool(step.get("simulate_write_failure", False)):
                raise RuntimeError(f"simulated write failure for path {raw_path}")

            content = self._resolve_write_content(step=step, fallback_output=default_output)
            self._write_content_to_path(safe_path=safe_path, content=content)
            return default_output

        if action == "read_file":
            if safe_path is None:
                raise ValueError("read_file requires path")

            if not safe_path.exists():
                raise FileNotFoundError(f"file not found: {raw_path}")

            return safe_path.read_text(encoding="utf-8")

        return default_output

    def _resolve_write_content(
        self,
        step: Dict[str, Any],
        fallback_output: Any,
    ) -> Any:
        content = step.get("content")
        if content is None:
            content = step.get("text")
        if content is None:
            content = step.get("data")
        if content is None:
            content = fallback_output
        return content

    def _write_content_to_path(
        self,
        safe_path: Path,
        content: Any,
    ) -> None:
        if isinstance(content, (dict, list)):
            safe_path.write_text(
                json.dumps(content, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return

        safe_path.write_text(str(content), encoding="utf-8")

    def _build_step_success_result(
        self,
        step_index: int,
        action: str,
        path: str,
        resolved_path: str,
        title: str,
        message: str,
        status: str,
        output: Any,
        attempt: int,
    ) -> Dict[str, Any]:
        return {
            "step": step_index,
            "action": action,
            "path": path,
            "resolved_path": resolved_path,
            "title": title,
            "message": message,
            "status": status,
            "output": output,
            "attempt": attempt,
        }

    def _build_step_error_result(
        self,
        step_index: int,
        action: str,
        path: str,
        resolved_path: str,
        title: str,
        message: str,
        error_message: str,
        attempt: int,
    ) -> Dict[str, Any]:
        return {
            "step": step_index,
            "action": action,
            "path": path,
            "resolved_path": resolved_path,
            "title": title,
            "message": message,
            "status": "error",
            "output": error_message,
            "attempt": attempt,
        }

    def _write_step_result_file(
        self,
        task_dir: Path,
        step_index: int,
        step_result: Dict[str, Any],
    ) -> Path:
        step_file = task_dir / f"step_{step_index:02d}.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(step_result, f, indent=2, ensure_ascii=False)
        return step_file

    def _log_step_start(
        self,
        task_name: str,
        step_index: int,
        title: str,
        message: str,
        step: Dict[str, Any],
        attempt: int,
    ) -> None:
        self.trace_logger.log_execution(
            step_id=f"step_{step_index:02d}",
            status="start",
            title=title,
            message=message,
            source="executor",
            raw={
                "task_name": task_name,
                "step_index": step_index,
                "attempt": attempt,
                "step": step,
            },
        )

    def _log_step_success(
        self,
        task_name: str,
        step_index: int,
        title: str,
        step_file: Path,
        step_result: Dict[str, Any],
        attempt: int,
        normalized_status: str,
    ) -> None:
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

    def _log_step_error(
        self,
        task_name: str,
        step_index: int,
        title: str,
        message: str,
        step: Dict[str, Any],
        error: Exception | str,
        error_result: Dict[str, Any],
        attempt: int,
    ) -> None:
        self.trace_logger.log_error(
            event_type="execution",
            step_id=f"step_{step_index:02d}",
            title=title,
            message=message,
            source="executor",
            error=error,
            raw={
                "task_name": task_name,
                "step_index": step_index,
                "attempt": attempt,
                "step": step,
                "error_result": error_result,
            },
        )