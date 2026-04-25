from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.failure_policy import FailurePolicy


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
    # runtime state
    # ============================================================

    def ensure_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)

        if os.path.exists(runtime_state_file):
            state = self._read_json(runtime_state_file, {})
            if not isinstance(state, dict):
                state = {}
            state = self._normalize_runtime_state(task, state)
            self._write_json(runtime_state_file, state)
            return state

        state = self._build_initial_runtime_state(task)
        self._write_json(runtime_state_file, state)
        return state

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        if not os.path.exists(runtime_state_file):
            return self.ensure_runtime_state(task)

        state = self._read_json(runtime_state_file, {})
        if not isinstance(state, dict):
            state = {}

        state = self._normalize_runtime_state(task, state)
        return state

    def save_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_runtime_state(task, state if isinstance(state, dict) else {})
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)
        self._write_json(runtime_state_file, normalized)
        return normalized

    # ============================================================
    # state transitions
    # ============================================================

    def mark_running(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)

        state["status"] = "running"
        state["last_run_tick"] = current_tick
        state["updated_at"] = self._now()
        state["task_name"] = self._task_name(task)
        state["task_id"] = self._task_id(task)
        state["goal"] = self._task_goal(task)
        state["task_dir"] = self._task_dir(task)

        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)
        state = self.save_runtime_state(task, state)

        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "mark_running",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "current_tick": current_tick,
                "current_step_index": state.get("current_step_index", 0),
                "steps_total": state.get("steps_total", 0),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "status": "running",
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }

    def advance_step(
        self,
        task: Dict[str, Any],
        step_result: Optional[Dict[str, Any]] = None,
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)

        steps = state.get("steps", [])
        idx = int(state.get("current_step_index", 0) or 0)

        current_step = steps[idx] if isinstance(steps, list) and 0 <= idx < len(steps) else None

        if isinstance(step_result, dict):
            results = state.setdefault("results", [])
            if not isinstance(results, list):
                results = []
                state["results"] = results

            step_results = state.setdefault("step_results", [])
            if not isinstance(step_results, list):
                step_results = []
                state["step_results"] = step_results

            execution_log = state.setdefault("execution_log", [])
            if not isinstance(execution_log, list):
                execution_log = []
                state["execution_log"] = execution_log

            execution_trace = state.setdefault("execution_trace", [])
            if not isinstance(execution_trace, list):
                execution_trace = []
                state["execution_trace"] = execution_trace

            sanitized_step_result = self._sanitize_step_result_for_storage(step_result)

            step_record = {
                "step_index": idx,
                "step": copy.deepcopy(current_step),
                "result": copy.deepcopy(sanitized_step_result),
                "tick": current_tick,
                "ts": self._now(),
            }

            results.append(copy.deepcopy(step_record))
            step_results.append(copy.deepcopy(step_record))
            execution_log.append(copy.deepcopy(step_record))

            incoming_trace = self._extract_execution_trace_from_step_result(sanitized_step_result)
            if incoming_trace:
                execution_trace.extend(copy.deepcopy(incoming_trace))

            state["last_step_result"] = copy.deepcopy(step_record)
            state["last_error"] = None

            result_payload = sanitized_step_result.get("result")
            if isinstance(result_payload, dict):
                for key in ("message", "content", "text", "final_answer", "stdout"):
                    value = result_payload.get(key)
                    if isinstance(value, str) and value.strip():
                        state["last_output"] = value.strip()
                        break

            if not str(state.get("last_output") or "").strip():
                for key in ("message", "content", "text", "final_answer", "stdout"):
                    value = sanitized_step_result.get(key)
                    if isinstance(value, str) and value.strip():
                        state["last_output"] = value.strip()
                        break

        next_index = idx + 1
        state["current_step_index"] = next_index
        state["updated_at"] = self._now()

        if next_index >= len(steps):
            state["status"] = "finished"
            state["finished_at_tick"] = current_tick
            state["finished_at"] = self._now()

            final_answer = self._extract_final_answer_from_step_result(step_result)
            if final_answer:
                state["final_answer"] = final_answer
            elif isinstance(state.get("last_output"), str) and state["last_output"].strip():
                state["final_answer"] = state["last_output"].strip()
        else:
            state["status"] = "running"

        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "advance_step",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "current_tick": current_tick,
                "next_step_index": state.get("current_step_index", 0),
                "steps_total": state.get("steps_total", 0),
                "status": state.get("status"),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "status": state.get("status", "running"),
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }

    def mark_finished(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        final_answer: str = "",
        final_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)

        state["status"] = "finished"
        state["current_step_index"] = int(state.get("steps_total", 0) or 0)
        state["finished_at_tick"] = current_tick
        state["finished_at"] = self._now()
        state["updated_at"] = self._now()
        state["last_error"] = None

        if isinstance(final_result, dict):
            sanitized_final_result = self._sanitize_step_result_for_storage(final_result)
            state["final_result"] = copy.deepcopy(sanitized_final_result)

            if not isinstance(state.get("last_step_result"), dict):
                state["last_step_result"] = {
                    "step_index": self._safe_int(
                        sanitized_final_result.get("step_index"),
                        int(state.get("steps_total", 0) or 0),
                    ),
                    "step": copy.deepcopy(
                        sanitized_final_result.get("step")
                        if isinstance(sanitized_final_result.get("step"), dict)
                        else None
                    ),
                    "result": copy.deepcopy(sanitized_final_result),
                    "tick": current_tick,
                    "ts": self._now(),
                }

        resolved_final_answer = str(final_answer or "").strip()
        if not resolved_final_answer and isinstance(final_result, dict):
            resolved_final_answer = self._extract_final_answer_from_step_result(final_result)

        if not resolved_final_answer:
            resolved_final_answer = str(state.get("last_output") or "").strip()

        state["final_answer"] = resolved_final_answer

        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "mark_finished",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "current_tick": current_tick,
                "final_answer": state.get("final_answer", ""),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": True,
            "status": "finished",
            "task": copy.deepcopy(task),
            "runtime_state": state,
            "final_answer": state.get("final_answer", ""),
        }

    # ============================================================
    # failure
    # ============================================================

    def mark_failed(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        failure_type: str = DEFAULT_FAILURE_TYPE,
        failure_message: str = "",
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)

        failure_type = self._normalize_failure_type(failure_type)
        decision = FailurePolicy.decide(failure_type)

        state["status"] = "failed"
        state["last_failure_tick"] = current_tick
        state["last_error"] = failure_message
        state["failure_type"] = failure_type
        state["failure_message"] = failure_message
        state["updated_at"] = self._now()

        state["failure_decision"] = {
            "retry": decision.retry,
            "replan": decision.replan,
            "fail": decision.fail,
            "wait": decision.wait,
        }

        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "mark_failed",
            {
                "failure_type": failure_type,
                "decision": state["failure_decision"],
                "failure_message": failure_message,
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": False,
            "status": "failed",
            "failure_type": failure_type,
            "decision": state["failure_decision"],
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }

    # ============================================================
    # utils
    # ============================================================

    def _build_initial_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_steps = task.get("steps", [])
        if not isinstance(task_steps, list):
            task_steps = []

        state = {
            "task_name": self._task_name(task),
            "task_id": self._task_id(task),
            "goal": self._task_goal(task),
            "task_dir": self._task_dir(task),
            "status": str(task.get("status") or "queued"),
            "steps": copy.deepcopy(task_steps),
            "results": copy.deepcopy(task.get("results", [])) if isinstance(task.get("results"), list) else [],
            "step_results": copy.deepcopy(task.get("step_results", [])) if isinstance(task.get("step_results"), list) else [],
            "execution_log": copy.deepcopy(task.get("execution_log", [])) if isinstance(task.get("execution_log"), list) else [],
            "execution_trace": copy.deepcopy(task.get("execution_trace", [])) if isinstance(task.get("execution_trace"), list) else [],
            "current_step_index": int(task.get("current_step_index", 0) or 0),
            "steps_total": len(task_steps),
            "replan_count": int(task.get("replan_count", 0) or 0),
            "max_replans": int(task.get("max_replans", 1) or 1),
            "last_step_result": self._sanitize_last_step_record(task.get("last_step_result")),
            "last_error": task.get("last_error"),
            "last_output": str(task.get("last_output") or ""),
            "final_answer": str(task.get("final_answer") or ""),
            "final_result": self._sanitize_step_result_for_storage(task.get("final_result")) if isinstance(task.get("final_result"), dict) else copy.deepcopy(task.get("final_result")),
            "created_at": self._now(),
            "updated_at": self._now(),
            "last_observation": copy.deepcopy(task.get("last_observation", {})) if isinstance(task.get("last_observation"), dict) else {},
            "last_decision": str(task.get("last_decision") or ""),
            "last_decision_reason": str(task.get("last_decision_reason") or ""),
            "next_action": str(task.get("next_action") or ""),
            "terminal_reason": str(task.get("terminal_reason") or ""),
            "loop_cycle_count": int(task.get("loop_cycle_count", 0) or 0),
            "loop_history": copy.deepcopy(task.get("loop_history", [])) if isinstance(task.get("loop_history"), list) else [],
            "capability": str(task.get("capability") or ""),
            "operation": str(task.get("operation") or ""),
            "capability_hint": copy.deepcopy(task.get("capability_hint", {})) if isinstance(task.get("capability_hint"), dict) else {},
            "capability_registry_hint": copy.deepcopy(task.get("capability_registry_hint", {})) if isinstance(task.get("capability_registry_hint"), dict) else {},
            "capability_execution": copy.deepcopy(task.get("capability_execution", {})) if isinstance(task.get("capability_execution"), dict) else {},
        }
        return state

    def _normalize_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(state if isinstance(state, dict) else {})

        normalized["task_name"] = normalized.get("task_name") or self._task_name(task)
        normalized["task_id"] = normalized.get("task_id") or self._task_id(task)
        normalized["goal"] = normalized.get("goal") or self._task_goal(task)
        normalized["task_dir"] = normalized.get("task_dir") or self._task_dir(task)

        status = str(normalized.get("status") or task.get("status") or "queued").strip().lower()
        if status not in TERMINAL_STATUSES and status not in NON_TERMINAL_STATUSES:
            status = "queued"
        normalized["status"] = status

        task_steps = task.get("steps", [])
        if not isinstance(task_steps, list):
            task_steps = []

        current_steps = normalized.get("steps")
        if not isinstance(current_steps, list):
            current_steps = []

        if task_steps and (not current_steps or len(task_steps) != len(current_steps)):
            normalized["steps"] = copy.deepcopy(task_steps)
        else:
            normalized["steps"] = copy.deepcopy(current_steps)

        normalized["steps_total"] = int(normalized.get("steps_total", len(normalized["steps"])) or len(normalized["steps"]))
        normalized["current_step_index"] = int(normalized.get("current_step_index", 0) or 0)
        normalized["replan_count"] = int(normalized.get("replan_count", task.get("replan_count", 0)) or 0)
        normalized["max_replans"] = int(normalized.get("max_replans", task.get("max_replans", 1)) or 1)

        if not isinstance(normalized.get("results"), list):
            normalized["results"] = []
        else:
            normalized["results"] = [self._sanitize_step_record(item) for item in normalized["results"] if isinstance(item, dict)]

        if not isinstance(normalized.get("step_results"), list):
            normalized["step_results"] = copy.deepcopy(normalized["results"])
        else:
            normalized["step_results"] = [self._sanitize_step_record(item) for item in normalized["step_results"] if isinstance(item, dict)]

        if not isinstance(normalized.get("execution_log"), list):
            normalized["execution_log"] = []
        else:
            normalized["execution_log"] = [self._sanitize_step_record(item) for item in normalized["execution_log"] if isinstance(item, dict)]

        if not isinstance(normalized.get("execution_trace"), list):
            normalized["execution_trace"] = []
        else:
            normalized["execution_trace"] = [copy.deepcopy(item) for item in normalized["execution_trace"] if isinstance(item, dict)]

        normalized["last_step_result"] = self._sanitize_last_step_record(
            normalized.get("last_step_result", task.get("last_step_result"))
        )
        normalized["last_error"] = normalized.get("last_error", task.get("last_error"))
        normalized["last_output"] = str(normalized.get("last_output", task.get("last_output", "")) or "")
        normalized["final_answer"] = str(normalized.get("final_answer", task.get("final_answer", "")) or "")
        final_result_value = normalized.get("final_result", task.get("final_result"))
        if isinstance(final_result_value, dict):
            normalized["final_result"] = self._sanitize_step_result_for_storage(final_result_value)
        else:
            normalized["final_result"] = copy.deepcopy(final_result_value)

        normalized.setdefault("created_at", self._now())
        normalized["updated_at"] = self._now()

        normalized["last_observation"] = self._prefer_nonempty_dict(
            normalized.get("last_observation"),
            task.get("last_observation"),
            default={},
        )

        normalized["last_decision"] = self._prefer_nonempty_str(
            normalized.get("last_decision"),
            task.get("last_decision"),
        )
        normalized["last_decision_reason"] = self._prefer_nonempty_str(
            normalized.get("last_decision_reason"),
            task.get("last_decision_reason"),
        )
        normalized["next_action"] = self._prefer_nonempty_str(
            normalized.get("next_action"),
            task.get("next_action"),
        )
        normalized["terminal_reason"] = self._prefer_nonempty_str(
            normalized.get("terminal_reason"),
            task.get("terminal_reason"),
        )

        normalized["loop_cycle_count"] = self._prefer_positive_int(
            normalized.get("loop_cycle_count"),
            task.get("loop_cycle_count"),
            default=0,
        )

        normalized["loop_history"] = self._prefer_nonempty_list(
            normalized.get("loop_history"),
            task.get("loop_history"),
            default=[],
        )

        normalized["capability"] = self._prefer_nonempty_str(
            normalized.get("capability"),
            task.get("capability"),
        )
        normalized["operation"] = self._prefer_nonempty_str(
            normalized.get("operation"),
            task.get("operation"),
        )
        normalized["capability_hint"] = self._prefer_nonempty_dict(
            normalized.get("capability_hint"),
            task.get("capability_hint"),
            default={},
        )
        normalized["capability_registry_hint"] = self._prefer_nonempty_dict(
            normalized.get("capability_registry_hint"),
            task.get("capability_registry_hint"),
            default={},
        )
        normalized["capability_execution"] = self._normalize_capability_execution(
            normalized.get("capability_execution"),
            task.get("capability_execution"),
        )

        return normalized

    def _sync_steps_from_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        synced = copy.deepcopy(state)

        task_steps = task.get("steps", [])
        if isinstance(task_steps, list) and task_steps:
            synced["steps"] = copy.deepcopy(task_steps)
            synced["steps_total"] = len(task_steps)
        else:
            steps = synced.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            synced["steps"] = copy.deepcopy(steps)
            synced["steps_total"] = len(steps)

        return synced

    def _sync_loop_fields_from_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        synced = copy.deepcopy(state)

        if isinstance(task.get("last_observation"), dict) and task.get("last_observation"):
            synced["last_observation"] = copy.deepcopy(task.get("last_observation"))

        for key in ("last_decision", "last_decision_reason", "next_action", "terminal_reason"):
            value = task.get(key)
            if value is not None and str(value).strip():
                synced[key] = str(value).strip()

        if "loop_cycle_count" in task:
            try:
                value = int(task.get("loop_cycle_count") or 0)
                if value > 0:
                    synced["loop_cycle_count"] = value
            except Exception:
                pass

        if isinstance(task.get("loop_history"), list) and task.get("loop_history"):
            synced["loop_history"] = copy.deepcopy(task.get("loop_history"))

        capability = str(task.get("capability") or "").strip()
        if capability:
            synced["capability"] = capability

        operation = str(task.get("operation") or "").strip()
        if operation:
            synced["operation"] = operation

        if isinstance(task.get("capability_hint"), dict) and task.get("capability_hint"):
            synced["capability_hint"] = copy.deepcopy(task.get("capability_hint"))

        if isinstance(task.get("capability_registry_hint"), dict) and task.get("capability_registry_hint"):
            synced["capability_registry_hint"] = copy.deepcopy(task.get("capability_registry_hint"))

        if isinstance(task.get("capability_execution"), dict) and task.get("capability_execution"):
            synced["capability_execution"] = self._normalize_capability_execution(
                synced.get("capability_execution"),
                task.get("capability_execution"),
            )

        return synced

    def _sync_task_from_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if not isinstance(task, dict):
            return

        task["status"] = state.get("status", task.get("status"))
        task["current_step_index"] = state.get("current_step_index", task.get("current_step_index", 0))
        task["steps_total"] = state.get("steps_total", task.get("steps_total", 0))
        task["steps"] = copy.deepcopy(state.get("steps", task.get("steps", [])))
        task["results"] = copy.deepcopy(state.get("results", task.get("results", [])))
        task["step_results"] = copy.deepcopy(state.get("step_results", task.get("step_results", [])))
        task["execution_log"] = copy.deepcopy(state.get("execution_log", task.get("execution_log", [])))
        task["execution_trace"] = copy.deepcopy(state.get("execution_trace", task.get("execution_trace", [])))
        task["last_step_result"] = copy.deepcopy(state.get("last_step_result"))
        task["last_error"] = state.get("last_error")
        task["final_answer"] = state.get("final_answer", task.get("final_answer", ""))
        task["final_result"] = copy.deepcopy(state.get("final_result"))
        task["failure_type"] = state.get("failure_type")
        task["failure_message"] = state.get("failure_message")
        task["failure_decision"] = copy.deepcopy(state.get("failure_decision"))
        task["runtime_state"] = copy.deepcopy(state)

        task["last_observation"] = copy.deepcopy(state.get("last_observation", {}))
        task["last_decision"] = state.get("last_decision", "")
        task["last_decision_reason"] = state.get("last_decision_reason", "")
        task["next_action"] = state.get("next_action", "")
        task["terminal_reason"] = state.get("terminal_reason", "")
        task["loop_cycle_count"] = state.get("loop_cycle_count", 0)
        task["loop_history"] = copy.deepcopy(state.get("loop_history", []))

        task["capability"] = state.get("capability", task.get("capability", ""))
        task["operation"] = state.get("operation", task.get("operation", ""))
        task["capability_hint"] = copy.deepcopy(state.get("capability_hint", task.get("capability_hint", {})))
        task["capability_registry_hint"] = copy.deepcopy(
            state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
        )
        task["capability_execution"] = copy.deepcopy(
            state.get("capability_execution", task.get("capability_execution", {}))
        )

    # ============================================================
    # trace sanitation / extraction
    # ============================================================

    def _extract_execution_trace_from_step_result(
        self,
        step_result: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(step_result, dict):
            return []

        existing_trace = step_result.get("execution_trace")
        if isinstance(existing_trace, list):
            return [copy.deepcopy(item) for item in existing_trace if isinstance(item, dict)]

        result_payload = step_result.get("result")
        if isinstance(result_payload, dict):
            nested_trace = result_payload.get("execution_trace")
            if isinstance(nested_trace, list):
                return [copy.deepcopy(item) for item in nested_trace if isinstance(item, dict)]

        return []

    def _sanitize_step_result_for_storage(self, step_result: Any) -> Any:
        if not isinstance(step_result, dict):
            return copy.deepcopy(step_result)

        sanitized = copy.deepcopy(step_result)

        outer_trace = self._extract_execution_trace_from_step_result(sanitized)
        if outer_trace:
            sanitized["execution_trace"] = copy.deepcopy(outer_trace)

        result_payload = sanitized.get("result")
        if isinstance(result_payload, dict):
            result_payload.pop("execution_trace", None)

            nested_result = result_payload.get("result")
            if isinstance(nested_result, dict):
                nested_result.pop("execution_trace", None)

        return sanitized

    def _sanitize_step_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = copy.deepcopy(record)
        result_payload = sanitized.get("result")
        if isinstance(result_payload, dict):
            sanitized["result"] = self._sanitize_step_result_for_storage(result_payload)
        return sanitized

    def _sanitize_last_step_record(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return copy.deepcopy(value)

        if isinstance(value.get("result"), dict) and "tick" in value and "ts" in value:
            return self._sanitize_step_record(value)

        return {
            "step_index": self._safe_int(value.get("step_index"), 0),
            "step": copy.deepcopy(value.get("step")) if isinstance(value.get("step"), dict) else None,
            "result": self._sanitize_step_result_for_storage(value),
            "tick": None,
            "ts": None,
        }

    def _extract_final_answer_from_step_result(self, step_result: Optional[Dict[str, Any]]) -> str:
        if not isinstance(step_result, dict):
            return ""

        for key in ("final_answer", "message", "content", "text", "stdout"):
            value = step_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        result_block = step_result.get("result")
        if isinstance(result_block, dict):
            for key in ("final_answer", "message", "content", "text", "stdout"):
                value = result_block.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    # ============================================================
    # file / task helpers
    # ============================================================

    def _get_runtime_state_file(self, task: Dict[str, Any]) -> str:
        if isinstance(task, dict):
            value = str(task.get("runtime_state_file") or "").strip()
            if value:
                return value

            task_dir = str(task.get("task_dir") or "").strip()
            if task_dir:
                return os.path.join(task_dir, "runtime_state.json")

            task_name = str(
                task.get("task_name")
                or task.get("task_id")
                or task.get("id")
                or ""
            ).strip()
            if task_name:
                return os.path.join(self.workspace_root, "tasks", task_name, "runtime_state.json")

        return os.path.join(self.workspace_root, "tasks", "unknown_task", "runtime_state.json")

    def _task_name(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("task_name")
            or task.get("task_id")
            or task.get("id")
            or "unknown_task"
        ).strip()

    def _task_id(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("task_id")
            or task.get("id")
            or task.get("task_name")
            or "unknown_task"
        ).strip()

    def _task_goal(self, task: Dict[str, Any]) -> str:
        return str(task.get("goal") or task.get("title") or "").strip()

    def _task_dir(self, task: Dict[str, Any]) -> str:
        value = str(task.get("task_dir") or "").strip()
        if value:
            return value
        return os.path.join(self.workspace_root, "tasks", self._task_name(task))

    def _normalize_failure_type(self, failure_type: str) -> str:
        value = str(failure_type or DEFAULT_FAILURE_TYPE).strip().lower()
        if value in FAILURE_TYPES:
            return value
        return DEFAULT_FAILURE_TYPE

    # ============================================================
    # generic helpers
    # ============================================================

    def _prefer_nonempty_dict(self, primary: Any, fallback: Any, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if isinstance(primary, dict) and primary:
            return copy.deepcopy(primary)
        if isinstance(fallback, dict) and fallback:
            return copy.deepcopy(fallback)
        return copy.deepcopy(default if isinstance(default, dict) else {})

    def _prefer_nonempty_str(self, primary: Any, fallback: Any, default: str = "") -> str:
        if primary is not None and str(primary).strip():
            return str(primary).strip()
        if fallback is not None and str(fallback).strip():
            return str(fallback).strip()
        return default

    def _prefer_positive_int(self, primary: Any, fallback: Any, default: int = 0) -> int:
        try:
            value = int(primary)
            if value >= 0:
                return value
        except Exception:
            pass

        try:
            value = int(fallback)
            if value >= 0:
                return value
        except Exception:
            pass

        return default

    def _prefer_nonempty_list(self, primary: Any, fallback: Any, default: Optional[List[Any]] = None) -> List[Any]:
        if isinstance(primary, list) and primary:
            return copy.deepcopy(primary)
        if isinstance(fallback, list) and fallback:
            return copy.deepcopy(fallback)
        return copy.deepcopy(default if isinstance(default, list) else [])

    def _normalize_capability_execution(self, primary: Any, fallback: Any = None) -> Dict[str, Any]:
        source: Dict[str, Any] = {}
        if isinstance(primary, dict) and primary:
            source = copy.deepcopy(primary)
        elif isinstance(fallback, dict) and fallback:
            source = copy.deepcopy(fallback)

        if not isinstance(source, dict):
            source = {}

        enabled = bool(source.get("enabled", False))
        status = str(source.get("status") or ("pending" if enabled else "metadata_only")).strip()
        reason = str(source.get("reason") or "").strip()

        normalized = copy.deepcopy(source)
        normalized["enabled"] = enabled
        normalized["status"] = status or ("pending" if enabled else "metadata_only")
        normalized["reason"] = reason

        return normalized

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _ensure_parent_dir(self, file_path: str) -> None:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _read_json(self, file_path: str, default: Any) -> Any:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)

    def _write_json(self, file_path: str, data: Any) -> None:
        self._ensure_parent_dir(file_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _trace(
        self,
        label: str,
        payload: Any,
        runtime_state_file: Optional[str] = None,
    ) -> None:
        try:
            if runtime_state_file:
                base_dir = os.path.dirname(runtime_state_file)
            else:
                base_dir = self.workspace_root

            if not base_dir:
                return

            os.makedirs(base_dir, exist_ok=True)
            trace_path = os.path.join(base_dir, self.trace_log_filename)

            record = {
                "ts": self._now(),
                "label": label,
                "payload": payload,
            }

            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass