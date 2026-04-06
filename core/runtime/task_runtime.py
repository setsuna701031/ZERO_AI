from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.runtime.runtime_state_machine import RuntimeStateMachine


TERMINAL_STATUSES = {
    "finished",
    "failed",
    "cancelled",
    "timeout",
}

NON_TERMINAL_STATUSES = {
    "queued",
    "planning",
    "ready",
    "running",
    "waiting",
    "blocked",
    "retrying",
    "replanning",
    "paused",
}

DEFAULT_FAILURE_TYPE = "internal_error"

FAILURE_TYPES = {
    "transient_error",
    "tool_error",
    "validation_error",
    "dependency_unmet",
    "timeout",
    "unsafe_action_blocked",
    "unsafe_action",
    "cancelled",
    "internal_error",
}


class TaskRuntime:
    """
    ZERO Task Runtime

    目標：
    1. timeout / cancellation
    2. failure taxonomy
    3. dependency + ready/blocked 基礎狀態
    4. 與既有 Task OS 欄位盡量相容
    5. 相容舊版 task_runner / scheduler 仍會呼叫的方法
    6. 支援 step result / advance step
    7. 支援 replan 欄位保存，不被覆蓋洗掉
    8. 狀態變更統一走 RuntimeStateMachine
    9. dependency status 可自動從其他 task 的 runtime_state.json 解析
    10. 若 runtime_state 沒有 steps，會自動從 plan.json 載入 steps
    """

    def __init__(
        self,
        workspace_root: str = "workspace",
        debug: bool = False,
        trace_log_filename: str = "task_runtime_trace.log",
    ) -> None:
        self.workspace_root = workspace_root
        self.debug = debug
        self.trace_log_filename = trace_log_filename
        self.state_machine = RuntimeStateMachine(debug=debug)

    # ============================================================
    # public api
    # ============================================================

    def ensure_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)

        if os.path.exists(runtime_state_file):
            state = self._read_json(runtime_state_file, default={})
            if not isinstance(state, dict):
                state = {}

            state = self._normalize_runtime_state(task, state)
            state = self.state_machine.ensure_runtime_status_fields(state)
            self._write_json(runtime_state_file, state)

            self._trace(
                "ensure_runtime_state_existing",
                {
                    "runtime_state_file": runtime_state_file,
                    "status": state.get("status"),
                    "retry_count": state.get("retry_count", 0),
                    "max_retries": state.get("max_retries", 0),
                    "replan_count": state.get("replan_count", 0),
                    "max_replans": state.get("max_replans", 0),
                    "steps_total": state.get("steps_total", 0),
                    "current_step_index": state.get("current_step_index", 0),
                },
                runtime_state_file=runtime_state_file,
            )
            return state

        state = self._build_initial_runtime_state(task)
        state = self.state_machine.ensure_runtime_status_fields(state)
        self._write_json(runtime_state_file, state)

        self._trace(
            "ensure_runtime_state_created",
            {
                "runtime_state_file": runtime_state_file,
                "status": state.get("status"),
                "retry_count": state.get("retry_count", 0),
                "max_retries": state.get("max_retries", 0),
                "replan_count": state.get("replan_count", 0),
                "max_replans": state.get("max_replans", 0),
                "steps_total": state.get("steps_total", 0),
                "current_step_index": state.get("current_step_index", 0),
            },
            runtime_state_file=runtime_state_file,
        )
        return state

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        runtime_state_file = self._get_runtime_state_file(task)
        if not os.path.exists(runtime_state_file):
            return self.ensure_runtime_state(task)

        state = self._read_json(runtime_state_file, default={})
        if not isinstance(state, dict):
            state = {}

        state = self._normalize_runtime_state(task, state)
        state = self.state_machine.ensure_runtime_status_fields(state)
        return state

    def save_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = copy.deepcopy(state or {})
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)

        normalized = self._normalize_runtime_state(task, state)
        normalized = self.state_machine.ensure_runtime_status_fields(normalized)
        self._write_json(runtime_state_file, normalized)
        return normalized

    def refresh_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_state_from_task(task, state)
        return self.save_runtime_state(task, state)

    # ============================================================
    # compatibility alias api
    # ============================================================

    def load_runtime(self, task_name_or_task: Any) -> Dict[str, Any]:
        task = self._task_like(task_name_or_task)
        return self.load_runtime_state(task)

    def save_runtime(self, task_name_or_task: Any, state: Dict[str, Any]) -> Dict[str, Any]:
        task = self._task_like(task_name_or_task)
        return self.save_runtime_state(task, state)

    # ============================================================
    # compatibility methods for old task_runner
    # ============================================================

    def check_timeout_before_run(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        result = self.check_timeout(task=task, current_tick=current_tick)

        if result.get("timeout") is True:
            result["timed_out"] = True
            return result

        return {
            "ok": True,
            "timed_out": False,
            "action": "timeout_check_passed",
            "task_name": self._task_name(task),
            "status": result.get("task", {}).get("status") if isinstance(result.get("task"), dict) else None,
            "task": result.get("task"),
            "runtime_state": result.get("runtime_state"),
            "message": result.get("reason", "within_timeout"),
        }

    def check_cancel_before_run(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        result = self.apply_cancel_if_requested(task=task, current_tick=current_tick)

        if result.get("cancelled") is True:
            result["cancel_applied"] = True
            return result

        return {
            "ok": True,
            "cancel_applied": False,
            "action": "cancel_check_passed",
            "task_name": self._task_name(task),
            "status": result.get("task", {}).get("status") if isinstance(result.get("task"), dict) else None,
            "task": result.get("task"),
            "runtime_state": result.get("runtime_state"),
            "message": result.get("reason", "cancel_not_requested"),
        }

    def check_blocked_by_dependencies(
        self,
        task: Dict[str, Any],
        dependency_status_map: Optional[Dict[str, str]] = None,
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        result = self.evaluate_readiness(
            task=task,
            dependency_status_map=dependency_status_map,
            current_tick=current_tick,
        )

        status = str(result.get("status", "") or "").strip().lower()
        action = str(result.get("action", "") or "").strip().lower()

        blocked = (
            status in {"blocked", "waiting"}
            or action in {"task_blocked", "waiting_dependencies", "task_waiting"}
        )

        return {
            "ok": bool(result.get("ok", True)),
            "blocked": blocked,
            "action": result.get("action"),
            "task_name": result.get("task_name"),
            "status": result.get("status"),
            "message": result.get("message", ""),
            "task": result.get("task"),
            "runtime_state": result.get("runtime_state"),
            "error": result.get("error"),
            "failure_type": result.get("failure_type"),
        }

    # ============================================================
    # step helpers used by runner
    # ============================================================

    def append_step_result(self, task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        results = copy.deepcopy(state.get("results", []))
        if not isinstance(results, list):
            results = []

        results.append(copy.deepcopy(result))
        state["results"] = results
        state["step_results"] = copy.deepcopy(results)
        state["last_step_result"] = copy.deepcopy(result)

        execution_log = copy.deepcopy(state.get("execution_log", []))
        if not isinstance(execution_log, list):
            execution_log = []

        execution_log.append(
            {
                "type": "step_result",
                "step_index": result.get("step", {}).get("step_index") if isinstance(result.get("step"), dict) else None,
                "ok": result.get("ok") if isinstance(result, dict) else None,
                "error": result.get("error") if isinstance(result, dict) else None,
            }
        )
        state["execution_log"] = execution_log

        saved = self.save_runtime_state(task, state)

        self._trace(
            "append_step_result",
            {
                "task_name": self._task_name(task),
                "results_count": len(saved.get("results", [])),
                "last_ok": result.get("ok") if isinstance(result, dict) else None,
                "last_error": result.get("error") if isinstance(result, dict) else None,
                "replan_count": saved.get("replan_count", 0),
                "replanned": saved.get("replanned", False),
                "status": saved.get("status"),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )
        return saved

    def advance_step(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        current_step_index = int(state.get("current_step_index", 0) or 0)
        state["current_step_index"] = current_step_index + 1

        steps = state.get("steps", [])
        if not isinstance(steps, list):
            steps = []
        state["steps_total"] = int(state.get("steps_total", len(steps)) or len(steps))

        saved = self.save_runtime_state(task, state)

        self._trace(
            "advance_step",
            {
                "task_name": self._task_name(task),
                "old_index": current_step_index,
                "new_index": saved.get("current_step_index"),
                "steps_total": saved.get("steps_total"),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )
        return saved

    # ============================================================
    # replan
    # ============================================================

    def can_replan(self, task: Dict[str, Any]) -> bool:
        state = self.load_runtime_state(task)
        replan_count = int(state.get("replan_count", 0) or 0)
        max_replans = int(state.get("max_replans", 0) or 0)
        return replan_count < max_replans

    def attempt_replan(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        reason: str = "",
        planner_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        if not self.can_replan(task):
            return {
                "ok": False,
                "action": "replan_not_allowed",
                "task_name": self._task_name(task),
                "status": state.get("status"),
                "message": "max replans reached",
                "runtime_state": state,
                "task": self._apply_runtime_state_to_task(task, state),
            }

        if not isinstance(planner_result, dict):
            return {
                "ok": False,
                "action": "replan_missing_plan",
                "task_name": self._task_name(task),
                "status": state.get("status"),
                "message": "planner_result missing",
                "runtime_state": state,
                "task": self._apply_runtime_state_to_task(task, state),
            }

        new_steps = planner_result.get("steps", [])
        if not isinstance(new_steps, list):
            new_steps = []

        old_replan_count = int(state.get("replan_count", 0) or 0)
        new_replan_count = old_replan_count + 1

        state["steps"] = copy.deepcopy(new_steps)
        state["steps_total"] = len(new_steps)
        state["current_step_index"] = 0
        state["planner_result"] = copy.deepcopy(planner_result)
        state["replan_count"] = new_replan_count
        state["replanned"] = True
        state["replan_reason"] = str(reason or "")
        state["failure_type"] = None
        state["failure_message"] = None
        state["last_error"] = None
        state["blocked_reason"] = ""

        if current_tick > 0:
            state["last_failure_tick"] = current_tick

        state, _ = self.state_machine.mark_ready(
            state,
            reason="task_runtime_attempt_replan",
        )

        execution_log = copy.deepcopy(state.get("execution_log", []))
        if not isinstance(execution_log, list):
            execution_log = []

        execution_log.append(
            {
                "type": "replan",
                "current_tick": current_tick,
                "reason": str(reason or ""),
                "replan_count": new_replan_count,
                "steps_total": len(new_steps),
            }
        )
        state["execution_log"] = execution_log

        saved = self.save_runtime_state(task, state)

        self._trace(
            "attempt_replan_success",
            {
                "task_name": self._task_name(task),
                "current_tick": current_tick,
                "reason": str(reason or ""),
                "old_replan_count": old_replan_count,
                "new_replan_count": new_replan_count,
                "steps_total": len(new_steps),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        merged_task = self._apply_runtime_state_to_task(task, saved)
        merged_task["steps"] = copy.deepcopy(new_steps)
        merged_task["steps_total"] = len(new_steps)
        merged_task["planner_result"] = copy.deepcopy(planner_result)
        merged_task["replan_count"] = new_replan_count
        merged_task["replanned"] = True
        merged_task["replan_reason"] = str(reason or "")

        return {
            "ok": True,
            "action": "replanned",
            "task_name": self._task_name(task),
            "status": saved.get("status"),
            "message": "task replanned",
            "runtime_state": saved,
            "task": merged_task,
        }

    # ============================================================
    # dependency / readiness
    # ============================================================

    def evaluate_readiness(
        self,
        task: Dict[str, Any],
        dependency_status_map: Optional[Dict[str, str]] = None,
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)
        task = self._apply_runtime_state_to_task(task, state)

        if self.is_terminal_status(task.get("status")):
            return {
                "ok": True,
                "action": "already_terminal",
                "task_name": self._task_name(task),
                "status": task.get("status"),
                "task": task,
                "runtime_state": state,
            }

        depends_on = self._normalize_depends_on(task.get("depends_on", []))
        effective_dependency_status_map = self._build_dependency_status_map(
            task=task,
            depends_on=depends_on,
            provided_map=dependency_status_map,
        )

        if not depends_on:
            old_status = state.get("status") or "queued"
            if old_status in ("queued", "blocked", "waiting", "planning"):
                state, transition = self.state_machine.mark_ready(
                    state,
                    reason="dependencies_satisfied_no_dependencies",
                )

                if (
                    not transition.ok
                    or self.state_machine.normalize_status(state.get("status")) != "ready"
                ):
                    state["status"] = "ready"
                    state = self.state_machine.ensure_runtime_status_fields(state)

                state["blocked_reason"] = ""
                state["failure_type"] = None
                state["failure_message"] = None

                state = self.save_runtime_state(task, state)

                self._trace(
                    "mark_ready_no_dependencies",
                    {
                        "old_status": old_status,
                        "new_status": state.get("status"),
                        "current_tick": current_tick,
                    },
                    runtime_state_file=self._get_runtime_state_file(task),
                )

            return {
                "ok": True,
                "action": "task_ready",
                "task_name": self._task_name(task),
                "status": state.get("status"),
                "task": self._apply_runtime_state_to_task(task, state),
                "runtime_state": state,
            }

        unmet: List[str] = []
        failed: List[str] = []

        for dep in depends_on:
            dep_status = str(effective_dependency_status_map.get(dep, "")).strip().lower()
            if dep_status == "finished":
                continue
            if dep_status in ("failed", "cancelled", "timeout"):
                failed.append(f"{dep}:{dep_status}")
            else:
                unmet.append(f"{dep}:{dep_status or 'unknown'}")

        if failed:
            message = f"dependency failed: {', '.join(failed)}"
            return self.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="dependency_unmet",
                failure_message=message,
            )

        if unmet:
            old_status = state.get("status") or "queued"
            blocked_reason = f"waiting dependencies: {', '.join(unmet)}"

            state, transition = self.state_machine.mark_waiting(
                state,
                reason="dependencies_unmet",
            )

            normalized_status = self.state_machine.normalize_status(state.get("status"))
            if not transition.ok or normalized_status not in {"waiting", "blocked"}:
                state["status"] = "waiting"
                state = self.state_machine.ensure_runtime_status_fields(state)

            state["blocked_reason"] = blocked_reason
            state["failure_type"] = None
            state["failure_message"] = None

            state = self.save_runtime_state(task, state)

            self._trace(
                "mark_waiting_dependencies",
                {
                    "old_status": old_status,
                    "new_status": state.get("status"),
                    "current_tick": current_tick,
                    "blocked_reason": blocked_reason,
                    "dependency_status_map": effective_dependency_status_map,
                },
                runtime_state_file=self._get_runtime_state_file(task),
            )

            return {
                "ok": True,
                "action": "waiting_dependencies",
                "task_name": self._task_name(task),
                "status": state.get("status"),
                "message": blocked_reason,
                "task": self._apply_runtime_state_to_task(task, state),
                "runtime_state": state,
            }

        old_status = state.get("status") or "queued"
        state, transition = self.state_machine.mark_ready(
            state,
            reason="dependencies_satisfied",
        )

        if (
            not transition.ok
            or self.state_machine.normalize_status(state.get("status")) != "ready"
        ):
            state["status"] = "ready"
            state = self.state_machine.ensure_runtime_status_fields(state)

        state["blocked_reason"] = ""
        state["failure_type"] = None
        state["failure_message"] = None

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_ready_dependencies_satisfied",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "dependency_status_map": effective_dependency_status_map,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "action": "task_ready",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    # ============================================================
    # state transitions
    # ============================================================

    def mark_running(self, task: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        old_status = state.get("status")

        state, transition = self.state_machine.mark_running(
            state,
            reason="task_runtime_mark_running",
        )

        state["last_run_tick"] = current_tick
        state["blocked_reason"] = ""
        state["failure_type"] = None
        state["failure_message"] = None
        state["last_error"] = None

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_running",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "transition_ok": transition.ok,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "action": "task_running",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task marked as running",
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def mark_finished(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        final_answer: str = "",
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        if not final_answer:
            last_step_result = state.get("last_step_result")
            if isinstance(last_step_result, dict):
                result_obj = last_step_result.get("result")
                if isinstance(result_obj, dict):
                    stdout = result_obj.get("stdout")
                    if isinstance(stdout, str) and stdout.strip():
                        final_answer = stdout.strip()

        old_status = state.get("status")

        state, transition = self.state_machine.mark_finished(
            state,
            reason="task_runtime_mark_finished",
        )

        state["finished_tick"] = current_tick
        state["final_answer"] = final_answer or state.get("final_answer", "")
        state["failure_type"] = None
        state["failure_message"] = None
        state["last_error"] = None
        state["blocked_reason"] = ""

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_finished",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "final_answer": state.get("final_answer", ""),
                "transition_ok": transition.ok,
                "steps_total": state.get("steps_total", 0),
                "current_step_index": state.get("current_step_index", 0),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "action": "task_finished",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task finished",
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def mark_failed(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        failure_type: str = DEFAULT_FAILURE_TYPE,
        failure_message: str = "",
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        failure_type = self._normalize_failure_type(failure_type)
        old_status = state.get("status")

        state, transition = self.state_machine.mark_failed(
            state,
            reason="task_runtime_mark_failed",
        )

        state["last_failure_tick"] = current_tick
        state["last_error"] = failure_message
        state["failure_type"] = failure_type
        state["failure_message"] = failure_message
        state["blocked_reason"] = ""

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_failed",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "failure_type": failure_type,
                "failure_message": failure_message,
                "transition_ok": transition.ok,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": False,
            "action": "task_failed",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task failed",
            "error": failure_message,
            "failure_type": failure_type,
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def mark_timeout(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        failure_message: str = "",
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        old_status = state.get("status")
        message = failure_message or "task timeout"

        state, transition = self.state_machine.mark_timeout(
            state,
            reason="task_runtime_mark_timeout",
        )

        state["last_failure_tick"] = current_tick
        state["last_error"] = message
        state["failure_type"] = "timeout"
        state["failure_message"] = message
        state["blocked_reason"] = ""

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_timeout",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "failure_message": message,
                "transition_ok": transition.ok,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": False,
            "action": "task_timeout",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task timeout",
            "error": message,
            "failure_type": "timeout",
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def mark_cancelled(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        reason: str = "",
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        old_status = state.get("status")
        message = reason or "task cancelled"

        state, transition = self.state_machine.mark_cancelled(
            state,
            reason="task_runtime_mark_cancelled",
        )

        state["last_error"] = message
        state["failure_type"] = "cancelled"
        state["failure_message"] = message
        state["blocked_reason"] = ""

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_cancelled",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "reason": message,
                "transition_ok": transition.ok,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": False,
            "action": "task_cancelled",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task cancelled",
            "error": message,
            "failure_type": "cancelled",
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def mark_retrying(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        failure_type: str = "transient_error",
        failure_message: str = "",
        next_retry_tick: int = 0,
    ) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        failure_type = self._normalize_failure_type(failure_type)
        old_status = state.get("status")
        retry_count = int(state.get("retry_count", 0) or 0) + 1

        state, transition = self.state_machine.mark_retrying(
            state,
            reason="task_runtime_mark_retrying",
            next_retry_tick=next_retry_tick,
        )

        state["retry_count"] = retry_count
        state["last_failure_tick"] = current_tick
        state["last_error"] = failure_message
        state["failure_type"] = failure_type
        state["failure_message"] = failure_message
        state["next_retry_tick"] = next_retry_tick

        state = self.save_runtime_state(task, state)

        self._trace(
            "mark_retrying",
            {
                "old_status": old_status,
                "new_status": state.get("status"),
                "current_tick": current_tick,
                "failure_type": failure_type,
                "failure_message": failure_message,
                "retry_count": retry_count,
                "next_retry_tick": next_retry_tick,
                "transition_ok": transition.ok,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "action": "task_retrying",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "task marked as retrying",
            "failure_type": failure_type,
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    # ============================================================
    # timeout / cancellation checks
    # ============================================================

    def check_timeout(self, task: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)
        task = self._apply_runtime_state_to_task(task, state)

        if self.is_terminal_status(task.get("status")):
            return {
                "ok": True,
                "timeout": False,
                "reason": "already_terminal",
                "task": task,
                "runtime_state": state,
            }

        timeout_ticks = int(task.get("timeout_ticks", state.get("timeout_ticks", 0)) or 0)
        if timeout_ticks <= 0:
            return {
                "ok": True,
                "timeout": False,
                "reason": "timeout_disabled",
                "task": task,
                "runtime_state": state,
            }

        created_tick = int(task.get("created_tick", state.get("created_tick", 0)) or 0)
        elapsed = int(current_tick) - created_tick

        if elapsed >= timeout_ticks:
            result = self.mark_timeout(
                task=task,
                current_tick=current_tick,
                failure_message=f"task timeout after {elapsed} ticks (limit={timeout_ticks})",
            )
            result["timeout"] = True
            return result

        return {
            "ok": True,
            "timeout": False,
            "reason": "within_timeout",
            "elapsed_ticks": elapsed,
            "timeout_ticks": timeout_ticks,
            "task": task,
            "runtime_state": state,
        }

    def is_cancel_requested(self, task: Dict[str, Any]) -> bool:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        if bool(task.get("cancel_requested", False)):
            return True
        if bool(state.get("cancel_requested", False)):
            return True
        return False

    def request_cancel(self, task: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)

        task["cancel_requested"] = True
        task["cancel_reason"] = reason or task.get("cancel_reason", "")

        state["cancel_requested"] = True
        state["cancel_reason"] = task["cancel_reason"]

        state = self.save_runtime_state(task, state)

        self._trace(
            "request_cancel",
            {
                "task_name": self._task_name(task),
                "reason": task["cancel_reason"],
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "action": "cancel_requested",
            "task_name": self._task_name(task),
            "status": state.get("status"),
            "message": "cancel requested",
            "task": self._apply_runtime_state_to_task(task, state),
            "runtime_state": state,
        }

    def apply_cancel_if_requested(self, task: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
        task = copy.deepcopy(task or {})
        state = self.load_runtime_state(task)
        task = self._apply_runtime_state_to_task(task, state)

        if self.is_terminal_status(task.get("status")):
            return {
                "ok": True,
                "cancelled": False,
                "reason": "already_terminal",
                "task": task,
                "runtime_state": state,
            }

        if not self.is_cancel_requested(task):
            return {
                "ok": True,
                "cancelled": False,
                "reason": "cancel_not_requested",
                "task": task,
                "runtime_state": state,
            }

        result = self.mark_cancelled(
            task=task,
            current_tick=current_tick,
            reason=task.get("cancel_reason") or state.get("cancel_reason") or "task cancelled by request",
        )
        result["cancelled"] = True
        return result

    # ============================================================
    # retry policy helpers
    # ============================================================

    def should_retry(
        self,
        task: Dict[str, Any],
        failure_type: str,
    ) -> bool:
        task = copy.deepcopy(task or {})
        failure_type = self._normalize_failure_type(failure_type)

        retry_count = int(task.get("retry_count", 0) or 0)
        max_retries = int(task.get("max_retries", 0) or 0)

        if retry_count >= max_retries:
            return False

        retryable_types = {
            "transient_error",
            "tool_error",
            "timeout",
        }

        return failure_type in retryable_types

    # ============================================================
    # small helpers used by runner / scheduler
    # ============================================================

    def is_terminal_status(self, status: Any) -> bool:
        return self.state_machine.is_terminal(status)

    def is_ready_status(self, status: Any) -> bool:
        return self.state_machine.normalize_status(status) in {"ready", "queued", "retrying"}

    def is_blocked_status(self, status: Any) -> bool:
        return self.state_machine.normalize_status(status) in {"blocked", "waiting"}

    def to_public_failure(self, failure_type: str, failure_message: str = "") -> Dict[str, Any]:
        failure_type = self._normalize_failure_type(failure_type)
        return {
            "failure_type": failure_type,
            "failure_message": failure_message or "",
            "retryable": failure_type in {"transient_error", "tool_error", "timeout"},
            "replan": failure_type in {"validation_error", "tool_error"},
            "fatal": failure_type in {"unsafe_action_blocked", "unsafe_action", "cancelled"},
        }

    # ============================================================
    # internal helpers
    # ============================================================

    def _build_initial_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_name = self._task_name(task)
        depends_on = self._normalize_depends_on(task.get("depends_on", []))

        plan_file = str(task.get("plan_file", "") or "")
        planner_result = copy.deepcopy(task.get("planner_result", {})) if isinstance(task.get("planner_result", {}), dict) else {}

        task_steps = task.get("steps", [])
        if not isinstance(task_steps, list):
            task_steps = []

        loaded_steps, loaded_planner_result = self._load_steps_and_plan_from_plan_file(plan_file)
        if loaded_planner_result and not planner_result:
            planner_result = loaded_planner_result

        steps = task_steps if task_steps else loaded_steps
        if not isinstance(steps, list):
            steps = []

        status = str(task.get("status") or "queued").strip().lower()
        if not status:
            status = "queued"

        if depends_on and status == "queued":
            blocked_reason = "waiting dependencies"
        else:
            blocked_reason = str(task.get("blocked_reason", "") or "")

        history = task.get("history", ["queued"])
        if isinstance(history, str):
            history = [history]
        elif not isinstance(history, list):
            history = ["queued"]

        results = task.get("results", [])
        if not isinstance(results, list):
            results = []

        execution_log = task.get("execution_log", [])
        if not isinstance(execution_log, list):
            execution_log = []

        return {
            "task_name": task_name,
            "status": status,
            "priority": int(task.get("priority", 0) or 0),
            "retry_count": int(task.get("retry_count", 0) or 0),
            "max_retries": int(task.get("max_retries", 0) or 0),
            "retry_delay": int(task.get("retry_delay", 0) or 0),
            "next_retry_tick": int(task.get("next_retry_tick", 0) or 0),
            "timeout_ticks": int(task.get("timeout_ticks", 0) or 0),
            "wait_until_tick": int(task.get("wait_until_tick", 0) or 0),
            "created_tick": int(task.get("created_tick", 0) or 0),
            "last_run_tick": self._nullable_int(task.get("last_run_tick")),
            "last_failure_tick": self._nullable_int(task.get("last_failure_tick")),
            "finished_tick": self._nullable_int(task.get("finished_tick")),
            "depends_on": depends_on,
            "blocked_reason": blocked_reason,
            "failure_type": self._nullable_str(task.get("failure_type")),
            "failure_message": self._nullable_str(task.get("failure_message")),
            "last_error": self._nullable_str(task.get("last_error")),
            "final_answer": str(task.get("final_answer", "") or ""),
            "cancel_requested": bool(task.get("cancel_requested", False)),
            "cancel_reason": str(task.get("cancel_reason", "") or ""),
            "runtime_state_file": self._get_runtime_state_file(task),
            "plan_file": plan_file,
            "log_file": str(task.get("log_file", "") or ""),
            "result_file": str(task.get("result_file", "") or ""),
            "execution_log_file": str(task.get("execution_log_file", "") or ""),
            "current_step_index": int(task.get("current_step_index", 0) or 0),
            "steps_total": int(task.get("steps_total", len(steps)) or len(steps)),
            "steps": copy.deepcopy(steps),
            "results": copy.deepcopy(results),
            "step_results": copy.deepcopy(results),
            "last_step_result": copy.deepcopy(task.get("last_step_result")),
            "replan_count": int(task.get("replan_count", 0) or 0),
            "replanned": bool(task.get("replanned", False)),
            "replan_reason": str(task.get("replan_reason", "") or ""),
            "max_replans": int(task.get("max_replans", 1) or 1),
            "planner_result": copy.deepcopy(planner_result),
            "history": copy.deepcopy(history),
            "execution_log": copy.deepcopy(execution_log),
            "goal": str(task.get("goal", "") or ""),
            "title": str(task.get("title", "") or ""),
            "task_dir": str(task.get("task_dir", "") or ""),
            "workspace_dir": str(task.get("workspace_dir", "") or ""),
        }

    def _normalize_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        base = self._build_initial_runtime_state(task)
        merged = copy.deepcopy(base)
        merged.update(copy.deepcopy(state or {}))

        merged["task_name"] = self._task_name(task) or str(merged.get("task_name", "") or "")
        merged["status"] = self.state_machine.normalize_status(merged.get("status", "queued"))
        merged["priority"] = int(merged.get("priority", 0) or 0)
        merged["retry_count"] = int(merged.get("retry_count", 0) or 0)
        merged["max_retries"] = int(merged.get("max_retries", 0) or 0)
        merged["retry_delay"] = int(merged.get("retry_delay", 0) or 0)
        merged["next_retry_tick"] = int(merged.get("next_retry_tick", 0) or 0)
        merged["timeout_ticks"] = int(merged.get("timeout_ticks", 0) or 0)
        merged["wait_until_tick"] = int(merged.get("wait_until_tick", 0) or 0)
        merged["created_tick"] = int(merged.get("created_tick", 0) or 0)
        merged["last_run_tick"] = self._nullable_int(merged.get("last_run_tick"))
        merged["last_failure_tick"] = self._nullable_int(merged.get("last_failure_tick"))
        merged["finished_tick"] = self._nullable_int(merged.get("finished_tick"))
        merged["depends_on"] = self._normalize_depends_on(merged.get("depends_on", []))
        merged["blocked_reason"] = str(merged.get("blocked_reason", "") or "")
        merged["failure_type"] = self._nullable_str(merged.get("failure_type"))
        if merged["failure_type"]:
            merged["failure_type"] = self._normalize_failure_type(merged["failure_type"])
        merged["failure_message"] = self._nullable_str(merged.get("failure_message"))
        merged["last_error"] = self._nullable_str(merged.get("last_error"))
        merged["final_answer"] = str(merged.get("final_answer", "") or "")
        merged["cancel_requested"] = bool(merged.get("cancel_requested", False))
        merged["cancel_reason"] = str(merged.get("cancel_reason", "") or "")
        merged["runtime_state_file"] = self._get_runtime_state_file(task)
        merged["plan_file"] = str(merged.get("plan_file", task.get("plan_file", "")) or "")
        merged["log_file"] = str(merged.get("log_file", "") or "")
        merged["result_file"] = str(merged.get("result_file", "") or "")
        merged["execution_log_file"] = str(merged.get("execution_log_file", "") or "")
        merged["current_step_index"] = int(merged.get("current_step_index", 0) or 0)

        steps = merged.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        if not steps:
            loaded_steps, loaded_planner_result = self._load_steps_and_plan_from_plan_file(merged["plan_file"])
            if isinstance(loaded_steps, list) and loaded_steps:
                steps = loaded_steps
            if isinstance(loaded_planner_result, dict) and loaded_planner_result:
                current_planner_result = merged.get("planner_result", {})
                if not isinstance(current_planner_result, dict) or not current_planner_result:
                    merged["planner_result"] = copy.deepcopy(loaded_planner_result)

        merged["steps"] = steps
        merged["steps_total"] = int(merged.get("steps_total", len(steps)) or len(steps))
        if merged["steps_total"] <= 0 and isinstance(steps, list):
            merged["steps_total"] = len(steps)

        results = merged.get("results", [])
        if not isinstance(results, list):
            results = []
        merged["results"] = results
        merged["step_results"] = copy.deepcopy(merged.get("step_results", results)) if isinstance(merged.get("step_results", results), list) else copy.deepcopy(results)
        merged["last_step_result"] = copy.deepcopy(merged.get("last_step_result"))

        merged["replan_count"] = int(merged.get("replan_count", 0) or 0)
        merged["replanned"] = bool(merged.get("replanned", False))
        merged["replan_reason"] = str(merged.get("replan_reason", "") or "")
        merged["max_replans"] = int(merged.get("max_replans", 1) or 1)
        merged["planner_result"] = copy.deepcopy(merged.get("planner_result", {})) if isinstance(merged.get("planner_result", {}), dict) else {}

        history = merged.get("history", ["queued"])
        if isinstance(history, str):
            history = [history]
        elif not isinstance(history, list):
            history = ["queued"]
        merged["history"] = history

        execution_log = merged.get("execution_log", [])
        if not isinstance(execution_log, list):
            execution_log = []
        merged["execution_log"] = execution_log

        merged["goal"] = str(merged.get("goal", task.get("goal", "")) or "")
        merged["title"] = str(merged.get("title", task.get("title", "")) or "")
        merged["task_dir"] = str(merged.get("task_dir", task.get("task_dir", "")) or "")
        merged["workspace_dir"] = str(merged.get("workspace_dir", task.get("workspace_dir", "")) or "")

        return merged

    def _sync_state_from_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        synced = copy.deepcopy(state or {})
        for key in (
            "status",
            "priority",
            "retry_count",
            "max_retries",
            "retry_delay",
            "next_retry_tick",
            "timeout_ticks",
            "wait_until_tick",
            "created_tick",
            "last_run_tick",
            "last_failure_tick",
            "finished_tick",
            "depends_on",
            "blocked_reason",
            "failure_type",
            "failure_message",
            "last_error",
            "final_answer",
            "cancel_requested",
            "cancel_reason",
            "current_step_index",
            "steps",
            "steps_total",
            "results",
            "step_results",
            "last_step_result",
            "replan_count",
            "replanned",
            "replan_reason",
            "max_replans",
            "planner_result",
            "history",
            "execution_log",
            "result_file",
            "execution_log_file",
            "plan_file",
            "log_file",
            "goal",
            "title",
            "task_dir",
            "workspace_dir",
        ):
            if key in task:
                synced[key] = copy.deepcopy(task.get(key))
        return self._normalize_runtime_state(task, synced)

    def _apply_runtime_state_to_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(task or {})
        for key in (
            "status",
            "priority",
            "retry_count",
            "max_retries",
            "retry_delay",
            "next_retry_tick",
            "timeout_ticks",
            "wait_until_tick",
            "created_tick",
            "last_run_tick",
            "last_failure_tick",
            "finished_tick",
            "depends_on",
            "blocked_reason",
            "failure_type",
            "failure_message",
            "last_error",
            "final_answer",
            "cancel_requested",
            "cancel_reason",
            "current_step_index",
            "steps",
            "steps_total",
            "results",
            "step_results",
            "last_step_result",
            "replan_count",
            "replanned",
            "replan_reason",
            "max_replans",
            "planner_result",
            "history",
            "execution_log",
            "result_file",
            "execution_log_file",
            "plan_file",
            "log_file",
            "goal",
            "title",
            "task_dir",
            "workspace_dir",
            "runtime_status_history",
            "runtime_created_at",
            "last_status_change_at",
            "planning_at",
            "ready_at",
            "running_at",
            "retrying_at",
            "waiting_at",
            "blocked_at",
            "replanning_at",
            "paused_at",
            "finished_at",
            "failed_at",
            "cancelled_at",
            "timeout_at",
            "last_started_at",
            "last_finished_at",
            "last_failed_at",
            "last_cancelled_at",
            "last_timeout_at",
        ):
            if key in state:
                merged[key] = copy.deepcopy(state.get(key))
        return merged

    def _task_like(self, task_name_or_task: Any) -> Dict[str, Any]:
        if isinstance(task_name_or_task, dict):
            return copy.deepcopy(task_name_or_task)

        task_name = str(task_name_or_task or "").strip()
        return {
            "task_name": task_name,
            "task_id": task_name,
            "task_dir": os.path.join(self.workspace_root, "tasks", task_name),
            "runtime_state_file": os.path.join(self.workspace_root, "tasks", task_name, "runtime_state.json"),
        }

    def _task_name(self, task: Dict[str, Any]) -> str:
        for key in ("task_name", "task_id", "id", "name", "title"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown_task"

    def _get_runtime_state_file(self, task: Dict[str, Any]) -> str:
        value = task.get("runtime_state_file")
        if isinstance(value, str) and value.strip():
            return value.strip()

        task_dir = task.get("task_dir")
        if isinstance(task_dir, str) and task_dir.strip():
            return os.path.join(task_dir, "runtime_state.json")

        task_name = self._task_name(task)
        return os.path.join(self.workspace_root, "tasks", task_name, "runtime_state.json")

    def _normalize_depends_on(self, value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            return [text]

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    result.append(item.strip())
            return result

        return []

    def _build_dependency_status_map(
        self,
        task: Dict[str, Any],
        depends_on: List[str],
        provided_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        result: Dict[str, str] = {}

        if isinstance(provided_map, dict):
            for key, value in provided_map.items():
                result[str(key).strip()] = str(value or "").strip().lower()

        for dep in depends_on:
            dep_key = str(dep).strip()
            if not dep_key:
                continue

            if result.get(dep_key):
                continue

            dep_runtime_file = self._resolve_dependency_runtime_state_file(task, dep_key)
            dep_state = self._read_json(dep_runtime_file, default={})
            dep_status = ""

            if isinstance(dep_state, dict):
                dep_status = str(dep_state.get("status", "") or "").strip().lower()

            result[dep_key] = dep_status

        return result

    def _resolve_dependency_runtime_state_file(self, task: Dict[str, Any], dependency_name: str) -> str:
        current_task_dir = str(task.get("task_dir", "") or "").strip()
        if current_task_dir:
            tasks_dir = os.path.dirname(current_task_dir)
            if tasks_dir:
                return os.path.join(tasks_dir, dependency_name, "runtime_state.json")

        runtime_state_file = str(task.get("runtime_state_file", "") or "").strip()
        if runtime_state_file:
            current_task_dir = os.path.dirname(runtime_state_file)
            tasks_dir = os.path.dirname(current_task_dir)
            if tasks_dir:
                return os.path.join(tasks_dir, dependency_name, "runtime_state.json")

        return os.path.join(self.workspace_root, "tasks", dependency_name, "runtime_state.json")

    def _load_steps_and_plan_from_plan_file(self, plan_file: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        plan_file = str(plan_file or "").strip()
        if not plan_file:
            return [], {}

        plan = self._read_json(plan_file, default={})
        if not isinstance(plan, dict):
            return [], {}

        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        normalized_steps: List[Dict[str, Any]] = []
        for item in steps:
            if isinstance(item, dict):
                normalized_steps.append(copy.deepcopy(item))

        return normalized_steps, copy.deepcopy(plan)

    def _normalize_failure_type(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in FAILURE_TYPES:
            return text
        return DEFAULT_FAILURE_TYPE

    def _nullable_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _nullable_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _read_json(self, path: str, default: Any = None) -> Any:
        if not os.path.exists(path):
            return copy.deepcopy(default)

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)

    def _write_json(self, path: str, data: Any) -> None:
        self._ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _ensure_parent_dir(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _trace(
        self,
        label: str,
        payload: Optional[Dict[str, Any]] = None,
        runtime_state_file: str = "",
    ) -> None:
        payload = payload or {}
        if runtime_state_file:
            trace_path = os.path.join(
                os.path.dirname(runtime_state_file),
                self.trace_log_filename,
            )
        else:
            trace_path = os.path.join(self.workspace_root, self.trace_log_filename)

        self._ensure_parent_dir(trace_path)

        line = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "label": label,
            "payload": payload,
        }

        try:
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:
            pass

        if self.debug:
            print(f"[TaskRuntime] {label}: {payload}")