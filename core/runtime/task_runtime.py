from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.failure_policy import FailurePolicy
from core.runtime.audit_log import AuditLogger
from core.runtime.runtime_state_guard import RuntimeStateGuard, validate_runtime_state
from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy, RuntimeTransitionPolicyError
from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.runtime_authority_seal import is_task_completion_authority


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
    "waiting_review",
    "waiting_blocker",
    "retrying",
    "replanning",
    "needs_observation",
    "needs_resume",
    "recoverable",
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


# Runtime artifact safety limits.
# Keep runtime_state.json useful for debugging, but prevent recursive / giant payload growth.
MAX_STORED_TEXT_CHARS = 12000
MAX_STORED_LIST_ITEMS = 50
MAX_STORED_TRACE_ITEMS = 200
DROP_RECURSIVE_KEYS = {"runtime_state", "task", "raw_task", "raw_result", "runner_result"}


def project_runtime_status(
    payload: Dict[str, Any],
    status: Any,
    *,
    owner: str = "task_runtime",
    reason: str = "runtime_status_projection",
) -> Dict[str, Any]:
    """Project a runtime status field through the canonical status write boundary.

    Non-owner layers call this instead of assigning ``["status"]`` directly.
    The ``owner`` and ``reason`` arguments are intentionally accepted for audit
    readability at call sites without changing legacy payload shapes.
    """
    _ = (owner, reason)
    if not isinstance(payload, dict):
        raise TypeError("runtime status projection target must be a dict")
    payload["status"] = status
    return payload


class TaskRuntime:
    def __init__(
        self,
        workspace_root: str = "workspace",
        debug: bool = False,
        trace_log_filename: str = "task_runtime_trace.log",
        evidence_adapter: Any = None,
        operator_runtime: Any = None,
        operator_bridge: Any = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.debug = debug
        self.trace_log_filename = trace_log_filename
        self.evidence_adapter = evidence_adapter
        if operator_bridge is None and operator_runtime is not None:
            from core.runtime.operator_integration_bridge import OperatorIntegrationBridge

            operator_bridge = OperatorIntegrationBridge(operator_runtime)
        self.operator_bridge = operator_bridge
        self.state_machine = RuntimeStateMachine(debug=debug)
        self.audit = AuditLogger(workspace_root=self.workspace_root)
        self.state_guard = RuntimeStateGuard()
        self.transition_policy = RuntimeTransitionPolicy()
        self.persistence = RuntimePersistenceService(
            workspace_root=self.workspace_root,
            source="task_runtime",
        )

    def _operator_bridge_session_id(
        self,
        *,
        task: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> str:
        for source in (state or {}, task or {}):
            if not isinstance(source, dict):
                continue
            for key in ("operator_session_id", "persistent_operator_session_id"):
                value = str(source.get(key) or "").strip()
                if value:
                    return value
            operator_state = source.get("operator")
            if isinstance(operator_state, dict):
                value = str(operator_state.get("session_id") or "").strip()
                if value:
                    return value
            metadata = source.get("metadata")
            if isinstance(metadata, dict):
                for key in ("operator_session_id", "persistent_operator_session_id"):
                    value = str(metadata.get(key) or "").strip()
                    if value:
                        return value
        return ""

    def _operator_bridge_record_step(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        result: Dict[str, Any],
        failed: bool,
    ) -> None:
        bridge = getattr(self, "operator_bridge", None)
        if bridge is None:
            return
        session_id = self._operator_bridge_session_id(task=task, state=state)
        if not session_id:
            return
        try:
            evidence_refs = result.get("evidence_refs") if isinstance(result, dict) else None
            nested_result = result.get("result") if isinstance(result, dict) else None
            if not evidence_refs and isinstance(nested_result, dict):
                evidence_refs = nested_result.get("evidence_refs")
            if failed:
                bridge.on_step_failed(
                    session_id,
                    step,
                    error=result.get("error") or result.get("message") or result,
                    evidence_refs=evidence_refs,
                )
            else:
                bridge.on_step_completed(
                    session_id,
                    step,
                    result=result,
                    evidence_refs=evidence_refs,
                )
        except Exception:
            if self.debug:
                print("[TaskRuntime] operator bridge step record ignored")

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
        self._emit_task_runtime_evidence("created", task=task, state=state)
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
        if not str(normalized.get("runtime_owner") or "").strip():
            normalized = self._stamp_runtime_ownership(
                normalized,
                owner="task_runtime",
                action=str(normalized.get("last_transition_action") or "save_runtime_state"),
            )
        guard_warnings = validate_runtime_state(normalized)
        if guard_warnings:
            normalized["runtime_state_guard_warnings"] = list(guard_warnings)
        else:
            normalized.pop("runtime_state_guard_warnings", None)
        normalized = self._compact_runtime_state_for_storage(normalized)
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
        state = self._stamp_runtime_ownership(state, owner="task_runtime", action="mark_running")

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

        result = {
            "ok": True,
            "status": "running",
            "task": copy.deepcopy(task),
            "runtime_state": state,
            **self._runtime_transition_metadata(state, "mark_running"),
        }
        self._emit_task_runtime_evidence("started", task=task, state=state)
        return result

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

        if not isinstance(steps, list):
            steps = []

        if idx >= len(steps):
            state["current_step_index"] = len(steps)
            state["status"] = "finished"
            state["finished_at_tick"] = current_tick
            state["finished_tick"] = current_tick
            state["finished_at"] = self._now()
            state["updated_at"] = self._now()

            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)

            self._trace(
                "advance_step_already_finished",
                {
                    "task_id": state.get("task_id"),
                    "task_name": state.get("task_name"),
                    "current_tick": current_tick,
                    "current_step_index": state.get("current_step_index", 0),
                    "steps_total": state.get("steps_total", 0),
                    "status": state.get("status"),
                },
                runtime_state_file=self._get_runtime_state_file(task),
            )

            result = {
                "ok": True,
                "status": "finished",
                "task": copy.deepcopy(task),
                "runtime_state": state,
            }
            self._emit_task_runtime_evidence("completed", task=task, state=state)
            return result

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
            self._update_repair_context_from_step_record(
                state=state,
                task=task,
                step_record=step_record,
                failed=False,
            )

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

            self._operator_bridge_record_step(
                task=task,
                state=state,
                step=current_step,
                result=sanitized_step_result,
                failed=False,
            )

        next_index = idx + 1
        state["current_step_index"] = next_index
        state["updated_at"] = self._now()

        if next_index >= len(steps):
            if bool(state.get("terminal_validation_required")):
                state["status"] = "needs_observation"
                state["next_action"] = "observe_terminal_result"
                state["terminal_validation"] = {
                    "execution_succeeded": True,
                    "observation_completed": False,
                    "artifact_validation_passed": False,
                    "evidence_persisted": False,
                    "deviation_detected": False,
                    "confirmed_finished": False,
                }
            else:
                state["status"] = "finished"
                state["finished_at_tick"] = current_tick
                state["finished_tick"] = current_tick
                state["finished_at"] = self._now()

            final_answer = self._extract_final_answer_from_step_result(step_result)
            if final_answer:
                state["final_answer"] = final_answer
            elif isinstance(state.get("last_output"), str) and state["last_output"].strip():
                state["final_answer"] = state["last_output"].strip()
        else:
            state["status"] = "running"

        if isinstance(step_result, dict):
            context = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
            self._update_goal_state_after_step(
                context=context,
                state=state,
                step_index=idx,
                step_result=step_result,
                failed=False,
                current_tick=current_tick,
            )
            state["repair_context"] = context

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

        result = {
            "ok": True,
            "status": state.get("status", "running"),
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }
        if str(state.get("status") or "").strip().lower() in {"finished", "completed"}:
            self._emit_task_runtime_evidence("completed", task=task, state=state)
        else:
            self._emit_task_runtime_evidence("started", task=task, state=state)
        return result

    def record_step_failure(
        self,
        task: Dict[str, Any],
        step: Optional[Dict[str, Any]] = None,
        step_result: Optional[Dict[str, Any]] = None,
        current_tick: int = 0,
        status: str = "running",
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)

        steps = state.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        idx = int(state.get("current_step_index", 0) or 0)
        current_step = step if isinstance(step, dict) else steps[idx] if 0 <= idx < len(steps) else None
        sanitized_step_result = self._sanitize_step_result_for_storage(
            step_result if isinstance(step_result, dict) else {"ok": False, "error": "invalid step result"}
        )

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

        step_record = {
            "step_index": idx,
            "step": copy.deepcopy(current_step),
            "result": copy.deepcopy(sanitized_step_result),
            "tick": current_tick,
            "ts": self._now(),
        }
        self._update_repair_context_from_step_record(
            state=state,
            task=task,
            step_record=step_record,
            failed=True,
        )

        results.append(copy.deepcopy(step_record))
        step_results.append(copy.deepcopy(step_record))
        execution_log.append(copy.deepcopy(step_record))

        incoming_trace = self._extract_execution_trace_from_step_result(sanitized_step_result)
        if incoming_trace:
            execution_trace.extend(copy.deepcopy(incoming_trace))

        state["last_step_result"] = copy.deepcopy(step_record)
        state["last_error"] = self._stringify_failure_message(sanitized_step_result.get("error"))

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

        self._operator_bridge_record_step(
            task=task,
            state=state,
            step=current_step,
            result=sanitized_step_result,
            failed=True,
        )

        normalized_status = str(status or "").strip().lower()
        if normalized_status in TERMINAL_STATUSES or normalized_status in NON_TERMINAL_STATUSES:
            state["status"] = normalized_status

        context = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        self._update_goal_state_after_step(
            context=context,
            state=state,
            step_index=idx,
            step_result=sanitized_step_result,
            failed=True,
            current_tick=current_tick,
        )
        state["repair_context"] = context

        state["updated_at"] = self._now()
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "record_step_failure",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "current_tick": current_tick,
                "current_step_index": state.get("current_step_index", 0),
                "steps_total": state.get("steps_total", 0),
                "status": state.get("status"),
                "last_error": state.get("last_error"),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        result = {
            "ok": False,
            "status": state.get("status", "running"),
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }
        normalized_status = str(state.get("status") or "").strip().lower()
        if normalized_status in {"failed", "error"}:
            self._emit_task_runtime_evidence(
                "failed",
                task=task,
                state=state,
                error=sanitized_step_result.get("error"),
            )
        elif normalized_status in {"blocked", "denied", "replanning"}:
            self._emit_task_runtime_evidence(
                "blocked",
                task=task,
                state=state,
                reason=state.get("last_error") or normalized_status,
            )
        return result

    def mark_finished(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        final_answer: str = "",
        final_result: Optional[Dict[str, Any]] = None,
        completion_authority: Any = None,
    ) -> Dict[str, Any]:
        task_id = str(task.get("task_id") or task.get("id") or task.get("task_name") or "")
        if not is_task_completion_authority(
            completion_authority,
            task_id=task_id,
            package_id=str(task.get("package_id") or task.get("work_package_id") or ""),
            session_id=str(task.get("session_id") or task.get("runtime_session") or ""),
        ):
            raise PermissionError("taskrunner_completion_authority_required")
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)
        state = self._stamp_runtime_ownership(state, owner="task_runtime", action="mark_finished")

        validation = state.get("terminal_validation") if isinstance(state.get("terminal_validation"), dict) else {}
        if bool(state.get("terminal_validation_required")) and not self._terminal_validation_ready(validation):
            state["status"] = "needs_observation"
            state["next_action"] = "observe_terminal_result"
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {
                "ok": True,
                "status": "needs_observation",
                "action": "terminal_validation_pending",
                "task": copy.deepcopy(task),
                "runtime_state": state,
            }

        state["status"] = "finished"
        state["current_step_index"] = int(state.get("steps_total", 0) or 0)
        state["finished_at_tick"] = current_tick
        state["finished_tick"] = current_tick
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
        context = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        subgoals = goal_state.get("subgoals") if isinstance(goal_state.get("subgoals"), list) else []
        for subgoal in subgoals:
            if isinstance(subgoal, dict) and subgoal.get("status") in {"pending", "running"}:
                subgoal["status"] = "finished"
                subgoal["result_summary"] = self._truncate_text(resolved_final_answer or "finished", 500)
        context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="finished")
        self._finalize_repair_session(context=context, status="finished", terminal_reason=resolved_final_answer or "finished")
        state["repair_context"] = context

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

        result = {
            "ok": True,
            "status": "finished",
            "task": copy.deepcopy(task),
            "runtime_state": state,
            "final_answer": state.get("final_answer", ""),
            "task_completion_authority": completion_authority,
            **self._runtime_transition_metadata(state, "mark_finished"),
        }
        self._emit_task_runtime_evidence("completed", task=task, state=state)
        return result

    def begin_terminal_validation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state["terminal_validation_required"] = True
        validation = state.get("terminal_validation") if isinstance(state.get("terminal_validation"), dict) else {}
        validation.setdefault("execution_succeeded", False)
        validation.setdefault("observation_completed", False)
        validation.setdefault("artifact_validation_passed", False)
        validation.setdefault("evidence_persisted", False)
        validation.setdefault("deviation_detected", False)
        validation.setdefault("confirmed_finished", False)
        state["terminal_validation"] = validation
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        return state

    def record_terminal_observation(
        self,
        task: Dict[str, Any],
        *,
        deviation_report: Dict[str, Any],
        evidence_persisted: bool,
        current_tick: int = 0,
        deviation_step_index: int = 0,
        blocked: bool = False,
        completion_authority: Any = None,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        report = copy.deepcopy(deviation_report if isinstance(deviation_report, dict) else {})
        deviation_detected = bool(report.get("deviation_detected"))
        validation = state.get("terminal_validation") if isinstance(state.get("terminal_validation"), dict) else {}
        validation.update({
            "execution_succeeded": bool(validation.get("execution_succeeded", True)),
            "observation_completed": True,
            "artifact_validation_passed": not deviation_detected,
            "evidence_persisted": bool(evidence_persisted),
            "deviation_detected": deviation_detected,
            "deviation_reason": str(report.get("reason") or ""),
            "confirmed_finished": False,
        })
        state["terminal_validation_required"] = True
        state["terminal_validation"] = validation

        if deviation_detected:
            status = "blocked" if blocked or not bool(report.get("recoverable", True)) else "needs_resume"
            state["status"] = status
            state["current_step_index"] = max(0, int(deviation_step_index))
            state["next_action"] = "wait_for_external_event" if status == "blocked" else "run_next_tick"
            state["last_error"] = str(report.get("reason") or "terminal_deviation")
            for key in ("finished_at", "finished_tick", "finished_at_tick", "final_result", "terminal_reason"):
                state.pop(key, None)
            self._synchronize_terminal_subgoal_state(state, status=status, reason=state["last_error"])
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {"ok": status != "blocked", "status": status, "task": copy.deepcopy(task), "runtime_state": state}

        validation["confirmed_finished"] = self._terminal_validation_ready(validation)
        state["terminal_validation"] = validation
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        return self.mark_finished(
            task=task,
            current_tick=current_tick,
            completion_authority=completion_authority,
            final_result=state.get("last_step_result", {}).get("result")
            if isinstance(state.get("last_step_result"), dict)
            else None,
        )

    @staticmethod
    def _terminal_validation_ready(validation: Dict[str, Any]) -> bool:
        return all(
            bool(validation.get(key))
            for key in (
                "execution_succeeded",
                "observation_completed",
                "artifact_validation_passed",
                "evidence_persisted",
            )
        ) and not bool(validation.get("deviation_detected"))

    def _synchronize_terminal_subgoal_state(self, state: Dict[str, Any], *, status: str, reason: str) -> None:
        context = self._normalize_repair_context_for_task(state.get("repair_context"), task=state, state=state)
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        current_subgoal_id = str(goal_state.get("current_subgoal_id") or "")
        if not current_subgoal_id:
            steps = state.get("steps") if isinstance(state.get("steps"), list) else []
            subgoal = self._subgoal_for_step_index(
                goal_state,
                steps,
                self._safe_int(state.get("current_step_index"), 0),
            )
            current_subgoal_id = str(subgoal.get("subgoal_id") or "") if isinstance(subgoal, dict) else ""
            if current_subgoal_id:
                goal_state["current_subgoal_id"] = current_subgoal_id
        if current_subgoal_id:
            self._set_subgoal_status(goal_state, current_subgoal_id, status, reason=reason)
        goal_state["status"] = status
        context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status=status)
        session = context.get("repair_session") if isinstance(context.get("repair_session"), dict) else {}
        if session:
            session["status"] = status
            session.pop("finished_at", None)
            terminal = session.get("terminal_node_id")
            if terminal:
                session["previous_terminal_node_id"] = terminal
                session["terminal_node_id"] = ""
            context["repair_session"] = session
        state["repair_context"] = context


    # ============================================================
    # blocker / waiting states
    # ============================================================

    def mark_waiting_blocker(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        blocker: Optional[Dict[str, Any]] = None,
        status: str = "waiting_blocker",
        reason: str = "",
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)

        if isinstance(blocker, dict):
            state["blockers"] = self._upsert_blocker(state.get("blockers", []), blocker)

        state["blockers"] = self._normalize_blockers(state.get("blockers", []))
        active = self._active_blockers(state.get("blockers", []))
        state["active_blocker_count"] = len(active)
        state["status"] = status if status in NON_TERMINAL_STATUSES else "waiting_blocker"

        review_blocker = next((item for item in active if item.get("type") == "review"), None)
        state["requires_review"] = bool(review_blocker)
        state["review_status"] = "pending_review" if review_blocker else ""
        state["review_id"] = str(review_blocker.get("id") or "") if review_blocker else ""
        state["review_payload"] = copy.deepcopy(review_blocker.get("payload") or {}) if review_blocker else {}
        state["last_run_tick"] = current_tick
        state["updated_at"] = self._now()
        state["waiting_reason"] = str(reason or (active[0].get("reason") if active else "") or "")
        state["next_action"] = "wait_for_external_event"
        state["last_decision"] = "wait"
        if state["waiting_reason"]:
            state["last_decision_reason"] = state["waiting_reason"]

        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "mark_waiting_blocker",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "current_tick": current_tick,
                "status": state.get("status"),
                "active_blocker_count": state.get("active_blocker_count", 0),
                "waiting_reason": state.get("waiting_reason", ""),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )
        self.audit.log_event(
            task,
            "blocker_added",
            {
                "current_tick": current_tick,
                "status": state.get("status"),
                "active_blocker_count": state.get("active_blocker_count", 0),
                "waiting_reason": state.get("waiting_reason", ""),
                "blockers": copy.deepcopy(state.get("blockers", [])),
                "next_action": state.get("next_action", ""),
            },
            source="task_runtime",
        )

        result = {
            "ok": True,
            "status": state.get("status", "waiting_blocker"),
            "task": copy.deepcopy(task),
            "runtime_state": state,
            # Compatibility fields for callers/tests that read the immediate result.
            # The source of truth remains runtime_state + blockers.
            "blockers": copy.deepcopy(state.get("blockers", [])),
            "active_blocker_count": state.get("active_blocker_count", 0),
            "requires_review": bool(state.get("requires_review", False)),
            "review_status": state.get("review_status", ""),
            "review_id": state.get("review_id", ""),
            "review_payload": copy.deepcopy(state.get("review_payload", {})),
            "next_action": state.get("next_action", ""),
            "waiting_reason": state.get("waiting_reason", ""),
        }
        requested_status = str(status or "").strip().lower()
        current_status = str(state.get("status") or "").strip().lower()
        if requested_status in {"blocked", "denied", "replanning"} or current_status in {
            "blocked",
            "denied",
            "replanning",
            "waiting_blocker",
            "waiting_review",
        }:
            self._emit_task_runtime_evidence(
                "blocked",
                task=task,
                state=state,
                reason=state.get("waiting_reason") or requested_status or current_status,
            )
        return result

    def mark_waiting_review(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        review_id: str = "",
        review_payload: Optional[Dict[str, Any]] = None,
        reason: str = "pending review",
    ) -> Dict[str, Any]:
        blocker = {
            "type": "review",
            "status": "pending",
            "id": str(review_id or ""),
            "reason": reason or "pending review",
            "payload": copy.deepcopy(review_payload) if isinstance(review_payload, dict) else {},
        }
        return self.mark_waiting_blocker(
            task=task,
            current_tick=current_tick,
            blocker=blocker,
            status="waiting_review",
            reason=reason or "pending review",
        )

    def add_blocker(
        self,
        task: Dict[str, Any],
        blocker: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        return self.mark_waiting_blocker(
            task=task,
            current_tick=current_tick,
            blocker=blocker,
            status="waiting_review" if str(blocker.get("type") or "") == "review" else "waiting_blocker",
            reason=str(blocker.get("reason") or ""),
        )

    def remove_blocker(
        self,
        task: Dict[str, Any],
        blocker_id: str,
        current_tick: int = 0,
        resolution_status: str = "resolved",
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        blockers = self._normalize_blockers(state.get("blockers", []))
        target_id = str(blocker_id or "").strip()

        updated: List[Dict[str, Any]] = []
        removed = False
        for item in blockers:
            if target_id and str(item.get("id") or "") == target_id:
                resolved = copy.deepcopy(item)
                resolved["status"] = str(resolution_status or "resolved")
                resolved["resolved_at"] = self._now()
                updated.append(resolved)
                removed = True
            else:
                updated.append(item)

        state["blockers"] = self._normalize_blockers(updated)
        active = self._active_blockers(state.get("blockers", []))
        state["active_blocker_count"] = len(active)
        state["updated_at"] = self._now()

        review_blocker = next((item for item in active if item.get("type") == "review"), None)
        state["requires_review"] = bool(review_blocker)
        state["review_status"] = "pending_review" if review_blocker else ""
        state["review_id"] = str(review_blocker.get("id") or "") if review_blocker else ""
        state["review_payload"] = copy.deepcopy(review_blocker.get("payload") or {}) if review_blocker else {}

        if active:
            state["status"] = "waiting_review" if any(b.get("type") == "review" for b in active) else "waiting_blocker"
            state["waiting_reason"] = str(active[0].get("reason") or "")
            state["next_action"] = "wait_for_external_event"
        else:
            state["waiting_reason"] = ""
            state["next_action"] = "run_next_tick"
            if str(state.get("status") or "") in {"waiting_review", "waiting_blocker", "blocked", "waiting"}:
                state["status"] = "running"

        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)

        self._trace(
            "remove_blocker",
            {
                "task_id": state.get("task_id"),
                "task_name": state.get("task_name"),
                "blocker_id": target_id,
                "removed": removed,
                "active_blocker_count": state.get("active_blocker_count", 0),
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )
        self.audit.log_event(
            task,
            "blocker_resolved",
            {
                "current_tick": current_tick,
                "blocker_id": target_id,
                "removed": removed,
                "resolution_status": str(resolution_status or "resolved"),
                "active_blocker_count": state.get("active_blocker_count", 0),
                "status": state.get("status"),
                "next_action": state.get("next_action", ""),
            },
            source="task_runtime",
        )

        return {
            "ok": removed,
            "status": state.get("status", "running"),
            "removed": removed,
            "blocker_id": target_id,
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }

    def has_active_blockers(self, task: Dict[str, Any]) -> bool:
        state = self.load_runtime_state(task)
        return bool(self._active_blockers(state.get("blockers", [])))

    def list_active_blockers(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        state = self.load_runtime_state(task)
        return self._active_blockers(state.get("blockers", []))

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
        state = self._stamp_runtime_ownership(state, owner="task_runtime", action="mark_failed")

        failure_type = self._normalize_failure_type(failure_type)
        decision = FailurePolicy.decide(failure_type)

        state["status"] = "failed"
        state["last_failure_tick"] = current_tick
        state["last_error"] = failure_message
        state["failure_type"] = failure_type
        state["failure_message"] = failure_message
        state["updated_at"] = self._now()
        context = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        if failure_message:
            context["last_error"] = failure_message
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        current_subgoal_id = str(goal_state.get("current_subgoal_id") or "")
        if current_subgoal_id:
            self._set_subgoal_status(goal_state, current_subgoal_id, "failed", reason=failure_message or failure_type)
            goal_state["replan_request"] = {
                "request_id": self._build_replan_request_id(
                    failed_subgoal_id=current_subgoal_id,
                    reason=failure_message or failure_type,
                    tick=current_tick,
                ),
                "failed_subgoal_id": current_subgoal_id,
                "reason": self._truncate_text(failure_message or failure_type, 500),
                "suggested_next_action": "review failure and provide a replan or confirmation",
                "tick": current_tick,
            }
            goal_state["replan_count"] = self._safe_int(goal_state.get("replan_count"), 0) + 1
        context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="failed")
        self._ensure_replan_proposal(
            context=context,
            task=task,
            state=state,
            current_tick=current_tick,
            reason=failure_message or failure_type,
            failed_subgoal_id=current_subgoal_id,
        )
        self._finalize_repair_session(context=context, status="failed", terminal_reason=failure_message or failure_type)
        state["repair_context"] = context

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
        self.audit.log_event(
            task,
            "task_failed",
            {
                "current_tick": current_tick,
                "failure_type": failure_type,
                "failure_message": failure_message,
                "decision": copy.deepcopy(state.get("failure_decision", {})),
            },
            source="task_runtime",
        )

        result = {
            "ok": False,
            "status": "failed",
            "failure_type": failure_type,
            "decision": state["failure_decision"],
            "task": copy.deepcopy(task),
            "runtime_state": state,
        }
        self._emit_task_runtime_evidence(
            "failed",
            task=task,
            state=state,
            error={"failure_type": failure_type, "message": failure_message},
        )
        return result

    # ============================================================
    # runtime ownership
    # ============================================================

    def apply_runtime_transition(
        self,
        task: Dict[str, Any],
        state: Dict[str, Any],
        *,
        owner: str,
        action: str,
        updates: Optional[Dict[str, Any]] = None,
        save: bool = False,
        allow_terminal_write: bool = False,
    ) -> Dict[str, Any]:
        """
        Apply controlled runtime-state updates through RuntimeStateGuard.

        This is the phase-2 runtime ownership funnel:
        callers may request updates, but TaskRuntime remains the authority that
        stamps ownership metadata, validates state, optionally persists it, and
        syncs the task snapshot.

        The method intentionally accepts only a small dict of top-level runtime
        fields for now. Nested repair_context edits remain owned by the existing
        repair/runtime helpers until later phases.
        """

        if not isinstance(state, dict):
            state = {}

        next_state = copy.deepcopy(state)
        transition_owner = str(owner or "task_runtime").strip().lower() or "task_runtime"
        transition_action = str(action or "runtime_transition").strip() or "runtime_transition"

        transition_updates = copy.deepcopy(updates or {})
        policy_decision = self.transition_policy.check_transition(
            current_state=next_state,
            updates=transition_updates,
            owner=transition_owner,
            action=transition_action,
        )
        if not policy_decision.ok:
            raise RuntimeTransitionPolicyError(policy_decision.reason)

        if "status" in transition_updates:
            raw_status = transition_updates.get("status")
            requested_status_text = str(raw_status or "").strip().lower().replace("-", "_").replace(" ", "_")
            if not self.state_machine.is_known_status(raw_status):
                raise RuntimeTransitionPolicyError(
                    f"runtime_state_machine_rejected_unknown_status:{requested_status_text}"
                )
            requested_status = self.state_machine.normalize_status(raw_status)
            transition_updates["status"] = requested_status
            machine_state, machine_result = self.state_machine.transition(
                next_state,
                requested_status,
                reason=transition_action,
                message=f"authorized runtime transition by {transition_owner}",
            )
            if not machine_result.ok:
                raise RuntimeTransitionPolicyError(machine_result.message)
            next_state = machine_state

        next_state.setdefault("runtime_transition_policy", {})
        if isinstance(next_state.get("runtime_transition_policy"), dict):
            next_state["runtime_transition_policy"]["last_decision"] = policy_decision.to_dict()

        for key, value in transition_updates.items():
            section = str(key or "").strip()
            if not section:
                continue
            mutation = self.state_guard.update_section(
                next_state,
                section=section,
                owner=transition_owner,
                patch=value,
                action="set",
                allow_terminal_write=allow_terminal_write,
            )
            next_state = mutation.state

        next_state = self._stamp_runtime_ownership(
            next_state,
            owner=transition_owner,
            action=transition_action,
        )
        next_state["updated_at"] = self._now()

        if save:
            next_state = self.save_runtime_state(task, next_state)
            self._sync_task_from_runtime_state(task, next_state)

        status_value = str(next_state.get("status") or "").strip().lower()
        if status_value in {"running"}:
            self._emit_task_runtime_evidence("started", task=task, state=next_state)
        elif status_value in {"finished", "completed"}:
            self._emit_task_runtime_evidence("completed", task=task, state=next_state)
        elif status_value in {"failed", "error"}:
            self._emit_task_runtime_evidence(
                "failed",
                task=task,
                state=next_state,
                error=next_state.get("last_error") or status_value,
            )
        elif status_value in {"blocked", "denied", "replanning"}:
            self._emit_task_runtime_evidence(
                "blocked",
                task=task,
                state=next_state,
                reason=next_state.get("waiting_reason") or status_value,
            )

        return next_state

    def _stamp_runtime_ownership(self, state: Dict[str, Any], *, owner: str, action: str) -> Dict[str, Any]:
        stamped = copy.deepcopy(state if isinstance(state, dict) else {})
        stamped["runtime_owner"] = str(owner or "task_runtime")
        stamped["last_transition_owner"] = str(owner or "task_runtime")
        stamped["last_transition_action"] = str(action or "runtime_state_update")
        stamped["last_transition_at"] = self._now()
        return stamped

    def _runtime_transition_metadata(self, state: Dict[str, Any], action: str) -> Dict[str, Any]:
        return {
            "runtime_owner": str((state or {}).get("runtime_owner") or "task_runtime"),
            "transition_owner": str((state or {}).get("last_transition_owner") or "task_runtime"),
            "transition_action": str((state or {}).get("last_transition_action") or action),
        }

    def _emit_task_runtime_evidence(
        self,
        phase: str,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        error: Any = None,
        reason: Any = None,
    ) -> None:
        adapter = getattr(self, "evidence_adapter", None)
        if adapter is None:
            return

        phase_name = str(phase or "").strip().lower()
        method_name = {
            "created": "emit_created",
            "started": "emit_started",
            "completed": "emit_completed",
            "failed": "emit_failed",
            "blocked": "emit_blocked",
        }.get(phase_name)
        if not method_name:
            return

        method = getattr(adapter, method_name, None)
        if not callable(method):
            return

        task_id = str((state or {}).get("task_id") or self._task_id(task)).strip()
        runtime_status = str((state or {}).get("status") or "").strip()
        if not runtime_status:
            runtime_status = str((task or {}).get("status") or "unknown").strip()

        try:
            if phase_name == "failed":
                method(task_id, runtime_status, error)
            elif phase_name == "blocked":
                method(task_id, runtime_status, reason)
            else:
                method(task_id, runtime_status)
        except Exception:
            return

    # ============================================================
    # utils
    # ============================================================

    def _build_initial_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_steps = task.get("steps", [])
        if not isinstance(task_steps, list):
            task_steps = []
        terminal_validation_required = bool(task.get("terminal_validation_required")) or any(
            isinstance(step, dict) and (
                bool(step.get("expected_artifacts"))
                or isinstance(step.get("expected"), dict)
            )
            for step in task_steps
        )

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
            "repair_context": self._normalize_repair_context(task.get("repair_context")),
            "blockers": self._normalize_blockers(task.get("blockers", [])),
            "active_blocker_count": 0,
            "waiting_reason": str(task.get("waiting_reason") or ""),
            "terminal_validation_required": terminal_validation_required,
            "terminal_validation": copy.deepcopy(task.get("terminal_validation", {}))
            if isinstance(task.get("terminal_validation"), dict)
            else {},
        }
        for key in (
            "lifecycle",
            "lifecycle_state",
            "engineering_session_state",
            "transition_history",
            "last_transition",
            "session_id",
            "operator_runtime_id",
            "evidence",
            "reason",
            "trigger",
            "source",
            "schema",
            "timestamp",
        ):
            if key in task:
                state[key] = copy.deepcopy(task.get(key))
        operator_session_id = self._operator_bridge_session_id(task=task, state=state)
        if operator_session_id:
            state["operator_session_id"] = operator_session_id
            state.setdefault("metadata", {})
            if isinstance(state["metadata"], dict):
                state["metadata"]["operator_session_id"] = operator_session_id
        active = self._active_blockers(state.get("blockers", []))
        state["active_blocker_count"] = len(active)
        review_blocker = next((item for item in active if item.get("type") == "review"), None)
        state["requires_review"] = bool(review_blocker)
        state["review_status"] = "pending_review" if review_blocker else str(task.get("review_status") or "")
        state["review_id"] = str(review_blocker.get("id") or "") if review_blocker else str(task.get("review_id") or "")
        state["review_payload"] = copy.deepcopy(review_blocker.get("payload") or {}) if review_blocker else copy.deepcopy(task.get("review_payload") or {}) if isinstance(task.get("review_payload"), dict) else {}
        if not state["requires_review"] and bool(task.get("requires_review")) and state["review_id"]:
            state["requires_review"] = True
        state["repair_context"] = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        return state

    def _normalize_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(state if isinstance(state, dict) else {})

        # Lifecycle/session payload is durable resume evidence. Runtime state is
        # authoritative once present; otherwise preserve the inbound task value.
        for key in (
            "lifecycle",
            "lifecycle_state",
            "engineering_session_state",
            "transition_history",
            "last_transition",
            "session_id",
            "operator_runtime_id",
            "evidence",
            "reason",
            "trigger",
            "source",
            "schema",
            "timestamp",
        ):
            if key not in normalized and key in task:
                normalized[key] = copy.deepcopy(task.get(key))

        normalized["task_name"] = normalized.get("task_name") or self._task_name(task)
        normalized["task_id"] = normalized.get("task_id") or self._task_id(task)
        normalized["goal"] = normalized.get("goal") or self._task_goal(task)
        normalized["task_dir"] = normalized.get("task_dir") or self._task_dir(task)
        operator_session_id = self._operator_bridge_session_id(task=task, state=normalized)
        if operator_session_id:
            normalized["operator_session_id"] = operator_session_id
            metadata = normalized.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["operator_session_id"] = operator_session_id
            normalized["metadata"] = metadata

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

        # Runtime steps are the source of truth after runtime_state.json exists.
        # This is required for repair-step injection: injected repair steps are written
        # into runtime_state.steps first, and must not be overwritten by the older
        # task.steps snapshot on the next load/save cycle.
        if current_steps:
            normalized["steps"] = copy.deepcopy(current_steps)
        else:
            normalized["steps"] = copy.deepcopy(task_steps)

        normalized["steps_total"] = len(normalized["steps"])
        normalized["current_step_index"] = int(normalized.get("current_step_index", 0) or 0)
        if normalized["current_step_index"] < 0:
            normalized["current_step_index"] = 0
        if normalized["current_step_index"] > normalized["steps_total"]:
            normalized["current_step_index"] = normalized["steps_total"]
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

        normalized["repair_context"] = self._normalize_repair_context(
            normalized.get("repair_context", task.get("repair_context"))
        )
        normalized["repair_context"] = self._normalize_repair_context_for_task(normalized.get("repair_context"), task=task, state=normalized)

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

        blockers = normalized.get("blockers")
        if not isinstance(blockers, list) or not blockers:
            blockers = task.get("blockers")
        normalized["blockers"] = self._normalize_blockers(blockers)
        normalized["active_blocker_count"] = len(self._active_blockers(normalized.get("blockers", [])))
        normalized["waiting_reason"] = self._prefer_nonempty_str(
            normalized.get("waiting_reason"),
            task.get("waiting_reason"),
        )

        return normalized

    def _sync_steps_from_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        synced = copy.deepcopy(state)

        task_steps = task.get("steps", [])
        if not isinstance(task_steps, list):
            task_steps = []

        runtime_steps = synced.get("steps", [])
        if not isinstance(runtime_steps, list):
            runtime_steps = []

        # Runtime owns the active execution plan once state exists.
        # Do not blindly copy task.steps over runtime_state.steps, because repair
        # injection lands in runtime_state.steps before the task snapshot is synced.
        # If we overwrite here, injected repair steps disappear before execution.
        if runtime_steps:
            synced["steps"] = copy.deepcopy(runtime_steps)
            synced["steps_total"] = len(runtime_steps)
        else:
            synced["steps"] = copy.deepcopy(task_steps)
            synced["steps_total"] = len(task_steps)

        try:
            current_index = int(synced.get("current_step_index", 0) or 0)
        except Exception:
            current_index = 0

        if current_index < 0:
            current_index = 0
        if current_index > synced["steps_total"]:
            current_index = synced["steps_total"]

        synced["current_step_index"] = current_index

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

    def _compact_runtime_state_for_storage(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {}

        compact = self._make_storage_safe(state)
        if not isinstance(compact, dict):
            return {}

        for key in ("results", "step_results", "execution_log"):
            value = compact.get(key)
            compact[key] = self._compact_list_for_storage(value, limit=MAX_STORED_LIST_ITEMS)

        trace_value = compact.get("execution_trace")
        compact["execution_trace"] = self._compact_list_for_storage(trace_value, limit=MAX_STORED_TRACE_ITEMS)

        loop_history = compact.get("loop_history")
        compact["loop_history"] = self._compact_list_for_storage(loop_history, limit=MAX_STORED_LIST_ITEMS)

        compact.pop("runtime_state", None)
        return compact

    def _compact_list_for_storage(self, value: Any, limit: int) -> List[Any]:
        if not isinstance(value, list):
            return []
        items = value[-max(1, int(limit)):]
        return [self._make_storage_safe(item) for item in items]

    def _make_storage_safe(self, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "<truncated: max depth reached>"

        if value is None or isinstance(value, (bool, int, float)):
            return value

        if isinstance(value, str):
            if len(value) <= MAX_STORED_TEXT_CHARS:
                return value
            return (
                value[:MAX_STORED_TEXT_CHARS]
                + f"\n<truncated: {len(value) - MAX_STORED_TEXT_CHARS} characters omitted>"
            )

        if isinstance(value, tuple):
            value = list(value)

        if isinstance(value, list):
            return [self._make_storage_safe(item, depth + 1) for item in value[-MAX_STORED_LIST_ITEMS:]]

        if isinstance(value, dict):
            safe: Dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text in DROP_RECURSIVE_KEYS:
                    safe[key_text] = "<omitted: recursive/heavy payload>"
                    continue
                safe[key_text] = self._make_storage_safe(item, depth + 1)
            return safe

        return str(value)

    def _sync_task_from_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if not isinstance(task, dict):
            return

        safe_state = self._compact_runtime_state_for_storage(state if isinstance(state, dict) else {})

        task["status"] = safe_state.get("status", task.get("status"))
        task["current_step_index"] = safe_state.get("current_step_index", task.get("current_step_index", 0))
        task["steps_total"] = safe_state.get("steps_total", task.get("steps_total", 0))
        task["steps"] = copy.deepcopy(safe_state.get("steps", task.get("steps", [])))
        task["results"] = copy.deepcopy(safe_state.get("results", task.get("results", [])))
        task["step_results"] = copy.deepcopy(safe_state.get("step_results", task.get("step_results", [])))
        task["execution_log"] = copy.deepcopy(safe_state.get("execution_log", task.get("execution_log", [])))
        task["execution_trace"] = copy.deepcopy(safe_state.get("execution_trace", task.get("execution_trace", [])))
        task["last_step_result"] = copy.deepcopy(safe_state.get("last_step_result"))
        task["last_error"] = safe_state.get("last_error")
        task["final_answer"] = safe_state.get("final_answer", task.get("final_answer", ""))
        task["final_result"] = copy.deepcopy(safe_state.get("final_result"))
        task["failure_type"] = safe_state.get("failure_type")
        task["failure_message"] = safe_state.get("failure_message")
        task["failure_decision"] = copy.deepcopy(safe_state.get("failure_decision"))
        for key in (
            "lifecycle",
            "lifecycle_state",
            "engineering_session_state",
            "transition_history",
            "last_transition",
            "session_id",
            "operator_runtime_id",
            "evidence",
            "reason",
            "trigger",
            "source",
            "schema",
            "timestamp",
        ):
            if key in safe_state:
                task[key] = copy.deepcopy(safe_state.get(key))
        operator_session_id = self._operator_bridge_session_id(task=task, state=safe_state)
        if operator_session_id:
            task["operator_session_id"] = operator_session_id
            metadata = task.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["operator_session_id"] = operator_session_id
            operator_state = task.setdefault("operator", {})
            if isinstance(operator_state, dict):
                operator_state["session_id"] = operator_session_id

        # Do not embed the whole runtime_state back into task.
        # That creates recursive task -> runtime_state -> task-like payload growth.
        task.pop("runtime_state", None)

        task["last_observation"] = copy.deepcopy(safe_state.get("last_observation", {}))
        task["last_decision"] = safe_state.get("last_decision", "")
        task["last_decision_reason"] = safe_state.get("last_decision_reason", "")
        task["next_action"] = safe_state.get("next_action", "")
        task["terminal_reason"] = safe_state.get("terminal_reason", "")
        task["loop_cycle_count"] = safe_state.get("loop_cycle_count", 0)
        task["loop_history"] = copy.deepcopy(safe_state.get("loop_history", []))

        task["capability"] = safe_state.get("capability", task.get("capability", ""))
        task["operation"] = safe_state.get("operation", task.get("operation", ""))
        task["capability_hint"] = copy.deepcopy(safe_state.get("capability_hint", task.get("capability_hint", {})))
        task["capability_registry_hint"] = copy.deepcopy(
            safe_state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
        )
        task["capability_execution"] = copy.deepcopy(
            safe_state.get("capability_execution", task.get("capability_execution", {}))
        )
        task["repair_context"] = copy.deepcopy(safe_state.get("repair_context", task.get("repair_context", {})))
        task["blockers"] = copy.deepcopy(safe_state.get("blockers", task.get("blockers", [])))
        task["active_blocker_count"] = safe_state.get("active_blocker_count", task.get("active_blocker_count", 0))
        task["waiting_reason"] = safe_state.get("waiting_reason", task.get("waiting_reason", ""))

        # Compatibility review fields mirrored from runtime_state.
        # Source of truth is still blockers + runtime_state, but task-level fields
        # are kept for existing scheduler / smoke tests / status display paths.
        task["requires_review"] = bool(safe_state.get("requires_review", task.get("requires_review", False)))
        task["review_status"] = safe_state.get("review_status", task.get("review_status", ""))
        task["review_id"] = safe_state.get("review_id", task.get("review_id", ""))
        task["review_payload"] = copy.deepcopy(safe_state.get("review_payload", task.get("review_payload", {})))

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
            return self._make_storage_safe(step_result)

        sanitized = self._make_storage_safe(step_result)
        if not isinstance(sanitized, dict):
            return sanitized

        outer_trace = self._extract_execution_trace_from_step_result(sanitized)
        if outer_trace:
            sanitized["execution_trace"] = self._compact_list_for_storage(outer_trace, limit=MAX_STORED_TRACE_ITEMS)

        result_payload = sanitized.get("result")
        if isinstance(result_payload, dict):
            result_payload.pop("execution_trace", None)

            nested_result = result_payload.get("result")
            if isinstance(nested_result, dict):
                nested_result.pop("execution_trace", None)

        return sanitized

    def _sanitize_step_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = self._make_storage_safe(record)
        if not isinstance(sanitized, dict):
            return {}
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

    def _stringify_failure_message(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(value)


    # ============================================================
    # blocker helpers
    # ============================================================

    def _normalize_blockers(self, blockers: Any) -> List[Dict[str, Any]]:
        if not isinstance(blockers, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(blockers, start=1):
            if not isinstance(item, dict):
                continue

            blocker_type = str(item.get("type") or "generic").strip().lower() or "generic"
            status = str(item.get("status") or "pending").strip().lower() or "pending"
            blocker_id = str(item.get("id") or item.get("blocker_id") or f"{blocker_type}_{index}").strip()

            payload = item.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            normalized.append(
                {
                    "type": blocker_type,
                    "status": status,
                    "id": blocker_id,
                    "reason": str(item.get("reason") or "").strip(),
                    "payload": copy.deepcopy(payload),
                    "created_at": str(item.get("created_at") or self._now()),
                    "resolved_at": str(item.get("resolved_at") or ""),
                }
            )

        return normalized

    def _active_blockers(self, blockers: Any) -> List[Dict[str, Any]]:
        normalized = self._normalize_blockers(blockers)
        resolved_statuses = {"resolved", "applied", "rejected", "cancelled", "done", "cleared"}
        return [item for item in normalized if str(item.get("status") or "") not in resolved_statuses]

    def _upsert_blocker(self, blockers: Any, blocker: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized = self._normalize_blockers(blockers)
        incoming = self._normalize_blockers([blocker])
        if not incoming:
            return normalized

        item = incoming[0]
        item_id = str(item.get("id") or "").strip()
        item_type = str(item.get("type") or "").strip()

        replaced = False
        result: List[Dict[str, Any]] = []
        for existing in normalized:
            same_id = bool(item_id and str(existing.get("id") or "") == item_id)
            same_type_without_id = not item_id and item_type and str(existing.get("type") or "") == item_type
            if same_id or same_type_without_id:
                result.append(item)
                replaced = True
            else:
                result.append(existing)

        if not replaced:
            result.append(item)

        return result

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

    def _normalize_repair_context(self, value: Any) -> Dict[str, Any]:
        context = copy.deepcopy(value) if isinstance(value, dict) else {}
        if not isinstance(context.get("flow"), list):
            context["flow"] = []
        else:
            context["flow"] = [copy.deepcopy(item) for item in context["flow"] if isinstance(item, dict)][-MAX_STORED_LIST_ITEMS:]

        if not isinstance(context.get("phase_results"), dict):
            context["phase_results"] = {}

        for key in (
            "original_failed_step",
            "failed_step",
            "failed_file",
            "failed_reason",
            "repair_result",
            "apply_result",
            "verify_result",
            "original_file_content",
            "proposed_fix",
            "final_edit_payload",
            "requested_functions",
            "failed_functions",
            "verification_result",
            "rollback",
            "rollback_result",
            "per_file_rollback_metadata",
            "dependency_graph",
            "repo_impact",
            "regression_verify",
            "multi_file_plan",
            "repair_session",
            "engineering_goal_state",
            "strategy",
            "last_phase",
            "last_error",
        ):
            context.setdefault(key, None if key.endswith("_result") or key in {"original_failed_step", "failed_step"} else "")
        context["strategy"] = self._normalize_repair_strategy(context.get("strategy"))
        context["repair_session"] = self._normalize_repair_session(context.get("repair_session"))
        context["engineering_goal_state"] = self._normalize_engineering_goal_state(context.get("engineering_goal_state"))

        return context

    def _normalize_repair_context_for_task(self, value: Any, *, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        context = self._normalize_repair_context(value)
        steps = state.get("steps") if isinstance(state.get("steps"), list) else task.get("steps") if isinstance(task.get("steps"), list) else []
        goal_source = context.get("engineering_goal_state")
        task_subgoals = task.get("subgoals") if isinstance(task.get("subgoals"), list) else []
        if task_subgoals and isinstance(goal_source, dict):
            existing_subgoals = goal_source.get("subgoals")
            if (
                not isinstance(existing_subgoals, list)
                or not existing_subgoals
                or (
                    len(existing_subgoals) == 1
                    and isinstance(existing_subgoals[0], dict)
                    and existing_subgoals[0].get("subgoal_id") == "default"
                    and not existing_subgoals[0].get("steps")
                )
            ):
                goal_source = copy.deepcopy(goal_source)
                goal_source["subgoals"] = copy.deepcopy(task_subgoals)
        context["engineering_goal_state"] = self._normalize_engineering_goal_state(
            goal_source,
            task=task,
            steps=steps,
        )
        return context

    def _normalize_engineering_goal_state(self, value: Any, *, task: Optional[Dict[str, Any]] = None, steps: Optional[List[Any]] = None) -> Dict[str, Any]:
        source = copy.deepcopy(value) if isinstance(value, dict) else {}
        task = task if isinstance(task, dict) else {}
        steps = steps if isinstance(steps, list) else task.get("steps") if isinstance(task.get("steps"), list) else []
        task_subgoals = task.get("subgoals")
        raw_subgoals = source.get("subgoals")
        if not isinstance(raw_subgoals, list) or not raw_subgoals:
            raw_subgoals = task_subgoals if isinstance(task_subgoals, list) and task_subgoals else []
        if not raw_subgoals:
            raw_subgoals = [
                {
                    "subgoal_id": "default",
                    "title": "Default repair flow",
                    "description": str(task.get("goal") or source.get("goal_text") or "Run repair steps"),
                    "steps": list(range(len(steps))),
                    "related_files": self._infer_related_files_from_steps(steps),
                    "risk_level": "low",
                    "requires_confirmation": False,
                }
            ]

        normalized_subgoals: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_subgoals):
            if not isinstance(item, dict):
                continue
            subgoal_id = str(item.get("subgoal_id") or item.get("id") or f"subgoal_{index + 1}").strip()
            step_refs = item.get("steps")
            if not isinstance(step_refs, list):
                step_refs = []
            normalized_steps = []
            for ref in step_refs:
                if isinstance(ref, int):
                    normalized_steps.append(ref)
                else:
                    text = str(ref or "").strip()
                    if text:
                        normalized_steps.append(text)
            status = str(item.get("status") or "pending").strip().lower()
            if status not in {"pending", "running", "needs_observation", "needs_resume", "recoverable", "finished", "failed", "blocked", "skipped"}:
                status = "pending"
            normalized_subgoals.append(
                {
                    "subgoal_id": subgoal_id,
                    "title": str(item.get("title") or subgoal_id),
                    "description": self._truncate_text(item.get("description") or "", 500),
                    "status": status,
                    "depends_on": [str(dep).strip() for dep in item.get("depends_on", []) if str(dep).strip()] if isinstance(item.get("depends_on"), list) else [],
                    "related_files": self._normalize_file_list(item.get("related_files")),
                    "risk_level": str(item.get("risk_level") or "low"),
                    "requires_confirmation": bool(item.get("requires_confirmation", False)),
                    "steps": normalized_steps,
                    "result_summary": self._truncate_text(item.get("result_summary"), 500),
                    "failure_reason": self._truncate_text(item.get("failure_reason"), 500),
                    "blocked_reason": self._truncate_text(item.get("blocked_reason"), 500),
                }
            )

        completed = [item["subgoal_id"] for item in normalized_subgoals if item.get("status") in {"finished", "skipped"}]
        failed = [item["subgoal_id"] for item in normalized_subgoals if item.get("status") == "failed"]
        blocked = [item["subgoal_id"] for item in normalized_subgoals if item.get("status") == "blocked"]
        current_subgoal_id = str(source.get("current_subgoal_id") or "").strip()
        if not current_subgoal_id:
            current = next((item for item in normalized_subgoals if item.get("status") == "running"), None)
            if current:
                current_subgoal_id = current["subgoal_id"]
            else:
                pending = next((item for item in normalized_subgoals if item.get("status") == "pending"), None)
                current_subgoal_id = pending["subgoal_id"] if pending else (normalized_subgoals[-1]["subgoal_id"] if normalized_subgoals else "")

        status = str(source.get("status") or "").strip().lower()
        if status not in {"running", "needs_observation", "needs_resume", "recoverable", "finished", "failed", "blocked"}:
            if failed:
                status = "failed"
            elif blocked:
                status = "blocked"
            elif normalized_subgoals and len(completed) == len(normalized_subgoals):
                status = "finished"
            else:
                status = "running"

        summary = copy.deepcopy(source.get("summary")) if isinstance(source.get("summary"), dict) else {}
        result = {
            "goal_id": str(source.get("goal_id") or task.get("task_id") or task.get("id") or task.get("task_name") or "goal"),
            "goal_text": str(source.get("goal_text") or task.get("goal") or task.get("title") or ""),
            "status": status,
            "subgoals": normalized_subgoals[-MAX_STORED_LIST_ITEMS:],
            "current_subgoal_id": current_subgoal_id,
            "completed_subgoals": completed,
            "failed_subgoals": failed,
            "blocked_subgoals": blocked,
            "replan_count": self._safe_int(source.get("replan_count"), 0),
            "summary": summary,
        }
        if isinstance(source.get("replan_request"), dict):
            result["replan_request"] = copy.deepcopy(source["replan_request"])
        if isinstance(source.get("replan_proposal"), dict):
            result["replan_proposal"] = self._normalize_replan_proposal(source["replan_proposal"])
        return result

    def _infer_related_files_from_steps(self, steps: List[Any]) -> List[str]:
        files: List[str] = []
        for step in steps if isinstance(steps, list) else []:
            if not isinstance(step, dict):
                continue
            for key in ("target_path", "path", "file_path", "target"):
                value = str(step.get(key) or "").strip().replace("\\", "/")
                if value and value not in files:
                    files.append(value)
        return files

    def _subgoal_for_step_index(self, goal_state: Dict[str, Any], steps: List[Any], step_index: int) -> Dict[str, Any]:
        subgoals = goal_state.get("subgoals") if isinstance(goal_state, dict) else []
        current_step = steps[step_index] if isinstance(steps, list) and 0 <= step_index < len(steps) else {}
        current_step_id = str(current_step.get("id") or current_step.get("step_id") or "") if isinstance(current_step, dict) else ""
        for subgoal in subgoals if isinstance(subgoals, list) else []:
            if not isinstance(subgoal, dict):
                continue
            refs = subgoal.get("steps")
            if not isinstance(refs, list):
                continue
            if step_index in refs or (current_step_id and current_step_id in [str(item) for item in refs]):
                return subgoal
        return subgoals[0] if isinstance(subgoals, list) and subgoals and isinstance(subgoals[0], dict) else {}

    def _subgoal_step_indices(self, subgoal: Dict[str, Any], steps: List[Any]) -> List[int]:
        refs = subgoal.get("steps") if isinstance(subgoal, dict) else []
        if not isinstance(refs, list):
            return []
        ids_to_indices: Dict[str, int] = {}
        for index, step in enumerate(steps if isinstance(steps, list) else []):
            if isinstance(step, dict):
                step_id = str(step.get("id") or step.get("step_id") or "").strip()
                if step_id:
                    ids_to_indices[step_id] = index
        indices: List[int] = []
        for ref in refs:
            if isinstance(ref, int):
                indices.append(ref)
            else:
                text = str(ref or "").strip()
                if text in ids_to_indices:
                    indices.append(ids_to_indices[text])
        return sorted(index for index in set(indices) if 0 <= index < len(steps))

    def prepare_current_subgoal(self, task: Dict[str, Any], *, current_tick: int = 0) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)
        context = self._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        goal_state = context.get("engineering_goal_state")
        steps = state.get("steps") if isinstance(state.get("steps"), list) else []
        idx = self._safe_int(state.get("current_step_index"), 0)

        while idx < len(steps):
            candidate = self._subgoal_for_step_index(goal_state, steps, idx)
            if candidate and candidate.get("status") in {"finished", "skipped"}:
                indices = self._subgoal_step_indices(candidate, steps)
                idx = max(indices) + 1 if indices else idx + 1
                state["current_step_index"] = idx
                continue
            break

        if idx >= len(steps):
            pending_status = "needs_observation" if bool(state.get("terminal_validation_required")) else "finished"
            context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status=pending_status)
            state["repair_context"] = context
            state = self.apply_runtime_transition(
                task,
                state,
                owner="task_runtime",
                action="subgoal_flow_finished",
                updates={
                    "current_step_index": len(steps),
                    "status": pending_status,
                },
                save=True,
            )
            return {"ok": True, "status": pending_status, "runtime_state": state, "task": copy.deepcopy(task)}

        subgoal = self._subgoal_for_step_index(goal_state, steps, idx)
        subgoal_id = str(subgoal.get("subgoal_id") or "") if isinstance(subgoal, dict) else ""
        completed = set(goal_state.get("completed_subgoals", [])) if isinstance(goal_state.get("completed_subgoals"), list) else set()
        missing = [dep for dep in subgoal.get("depends_on", []) if dep not in completed] if isinstance(subgoal, dict) else []
        if missing:
            reason = f"subgoal dependency unmet: {', '.join(missing)}"
            self._set_subgoal_status(goal_state, subgoal_id, "blocked", reason=reason)
            goal_state["status"] = "blocked"
            goal_state["current_subgoal_id"] = subgoal_id
            goal_state["blocked_reason"] = reason
            goal_state["replan_request"] = {
                "request_id": self._build_replan_request_id(
                    failed_subgoal_id=subgoal_id,
                    reason=reason,
                    tick=current_tick,
                ),
                "failed_subgoal_id": subgoal_id,
                "reason": self._truncate_text(reason, 500),
                "blocked_reason": self._truncate_text(reason, 500),
                "suggested_next_action": "review blocker and provide a replan or confirmation",
                "tick": current_tick,
            }
            goal_state["replan_count"] = self._safe_int(goal_state.get("replan_count"), 0) + 1
            context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="blocked")
            self._ensure_replan_proposal(
                context=context,
                task=task,
                state=state,
                current_tick=current_tick,
                reason=reason,
                failed_subgoal_id=subgoal_id,
                blocked_reason=reason,
            )
            state["repair_context"] = context
            state = self.apply_runtime_transition(
                task,
                state,
                owner="task_runtime",
                action="subgoal_dependency_blocked",
                updates={
                    "status": "blocked",
                    "last_error": reason,
                },
                save=True,
            )
            return {"ok": False, "blocked": True, "status": "blocked", "reason": reason, "runtime_state": state, "task": copy.deepcopy(task)}

        self._set_subgoal_status(goal_state, subgoal_id, "running")
        goal_state["status"] = "running"
        goal_state["current_subgoal_id"] = subgoal_id
        context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state)
        state["repair_context"] = context
        state["current_step_index"] = idx
        state["updated_at"] = self._now()
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        return {"ok": True, "status": state.get("status", "running"), "runtime_state": state, "task": copy.deepcopy(task)}

    def _set_subgoal_status(self, goal_state: Dict[str, Any], subgoal_id: str, status: str, *, result_summary: Any = "", reason: Any = "") -> None:
        if not isinstance(goal_state, dict) or not subgoal_id:
            return
        for subgoal in goal_state.get("subgoals", []) if isinstance(goal_state.get("subgoals"), list) else []:
            if isinstance(subgoal, dict) and subgoal.get("subgoal_id") == subgoal_id:
                subgoal["status"] = status
                if result_summary:
                    subgoal["result_summary"] = self._truncate_text(result_summary, 500)
                if reason:
                    if status == "blocked":
                        subgoal["blocked_reason"] = self._truncate_text(reason, 500)
                    else:
                        subgoal["failure_reason"] = self._truncate_text(reason, 500)
                break

    def _refresh_goal_state_summary(self, goal_state: Dict[str, Any], final_status: str = "") -> Dict[str, Any]:
        goal_state = copy.deepcopy(goal_state if isinstance(goal_state, dict) else {})
        subgoals = [item for item in goal_state.get("subgoals", []) if isinstance(item, dict)]
        completed = [item["subgoal_id"] for item in subgoals if item.get("status") in {"finished", "skipped"}]
        failed = [item["subgoal_id"] for item in subgoals if item.get("status") == "failed"]
        blocked = [item["subgoal_id"] for item in subgoals if item.get("status") == "blocked"]
        goal_state["completed_subgoals"] = completed
        goal_state["failed_subgoals"] = failed
        goal_state["blocked_subgoals"] = blocked
        if final_status:
            goal_state["status"] = final_status
        elif failed:
            goal_state["status"] = "failed"
        elif blocked:
            goal_state["status"] = "blocked"
        elif subgoals and len(completed) == len(subgoals):
            goal_state["status"] = "finished"
        else:
            goal_state["status"] = "running"
        goal_state["summary"] = {
            "total_subgoals": len(subgoals),
            "completed_subgoals": len(completed),
            "failed_subgoals": len(failed),
            "blocked_subgoals": len(blocked),
            "current_subgoal_id": str(goal_state.get("current_subgoal_id") or ""),
            "goal_status": goal_state["status"],
        }
        return goal_state

    def _normalize_replan_proposal(self, value: Any) -> Dict[str, Any]:
        source = copy.deepcopy(value) if isinstance(value, dict) else {}
        action = str(source.get("proposed_action") or "retry_same_subgoal").strip()
        if action not in {"retry_same_subgoal", "switch_strategy", "split_subgoal", "require_confirmation", "abort_goal"}:
            action = "retry_same_subgoal"
        status = str(source.get("status") or "proposed").strip().lower()
        if status not in {"proposed", "accepted", "rejected", "expired"}:
            status = "proposed"
        return {
            "proposal_id": str(source.get("proposal_id") or ""),
            "source_replan_request": copy.deepcopy(source.get("source_replan_request")) if isinstance(source.get("source_replan_request"), dict) else {},
            "failed_subgoal_id": str(source.get("failed_subgoal_id") or ""),
            "reason": self._truncate_text(source.get("reason"), 500),
            "proposed_action": action,
            "proposed_subgoals": [copy.deepcopy(item) for item in source.get("proposed_subgoals", []) if isinstance(item, dict)] if isinstance(source.get("proposed_subgoals"), list) else [],
            "proposed_steps": [copy.deepcopy(item) for item in source.get("proposed_steps", []) if isinstance(item, dict)] if isinstance(source.get("proposed_steps"), list) else [],
            "risk_level": str(source.get("risk_level") or "low"),
            "requires_confirmation": bool(source.get("requires_confirmation", False)),
            "blocked_reason": self._truncate_text(source.get("blocked_reason"), 500),
            "status": status,
            "created_at": str(source.get("created_at") or self._now()),
            "summary": self._truncate_text(source.get("summary"), 500),
        }

    def _build_replan_request_id(self, *, failed_subgoal_id: Any, reason: Any, tick: int = 0) -> str:
        seed = f"{failed_subgoal_id}:{tick}:{self._truncate_text(reason, 160)}"
        return "replan-request-" + "".join(ch if ch.isalnum() or ch in {"-", "_", ":"} else "_" for ch in seed)[:180]

    def _ensure_replan_request_id(self, request: Dict[str, Any]) -> Dict[str, Any]:
        payload = copy.deepcopy(request if isinstance(request, dict) else {})
        if not str(payload.get("request_id") or "").strip():
            payload["request_id"] = self._build_replan_request_id(
                failed_subgoal_id=payload.get("failed_subgoal_id") or payload.get("blocked_subgoal_id") or "",
                reason=payload.get("reason") or payload.get("blocked_reason") or "",
                tick=self._safe_int(payload.get("tick"), 0),
            )
        return payload

    def _ensure_replan_proposal(
        self,
        *,
        context: Dict[str, Any],
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int = 0,
        reason: Any = "",
        failed_subgoal_id: str = "",
        blocked_reason: Any = "",
    ) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        replan_request = goal_state.get("replan_request") if isinstance(goal_state.get("replan_request"), dict) else {}
        if not replan_request:
            replan_request = {
                "failed_subgoal_id": failed_subgoal_id or str(goal_state.get("current_subgoal_id") or ""),
                "reason": self._truncate_text(reason or blocked_reason or "replan requested", 500),
                "blocked_reason": self._truncate_text(blocked_reason, 500),
                "tick": current_tick,
            }
        replan_request = self._ensure_replan_request_id(replan_request)
        goal_state["replan_request"] = replan_request

        existing = goal_state.get("replan_proposal") if isinstance(goal_state.get("replan_proposal"), dict) else {}
        existing_status = str(existing.get("status") or "").strip().lower()
        source_id = str(replan_request.get("request_id") or "")
        existing_source = existing.get("source_replan_request") if isinstance(existing.get("source_replan_request"), dict) else {}
        if existing and str(existing_source.get("request_id") or "") == source_id:
            strategy = context.get("strategy") if isinstance(context.get("strategy"), dict) else {}
            if existing_status != "proposed" or not bool(strategy.get("exhausted", False)):
                context["engineering_goal_state"] = goal_state
                return self._normalize_replan_proposal(existing)
        if existing and existing_status and existing_status != "proposed":
            context["engineering_goal_state"] = goal_state
            return self._normalize_replan_proposal(existing)

        proposal = self._build_replan_proposal(
            context=context,
            task=task,
            state=state,
            replan_request=replan_request,
            current_tick=current_tick,
            reason=reason,
            failed_subgoal_id=failed_subgoal_id or str(replan_request.get("failed_subgoal_id") or goal_state.get("current_subgoal_id") or ""),
            blocked_reason=blocked_reason,
        )
        goal_state["replan_proposal"] = proposal
        context["engineering_goal_state"] = goal_state
        self._append_repair_session_node(
            context=context,
            node_type="replan_proposal",
            status="proposed",
            tick=current_tick,
            step_index=-1,
            step_id=proposal["proposal_id"],
            input_summary=f"source={source_id}",
            output_summary=f"action={proposal['proposed_action']}; risk={proposal['risk_level']}; confirmation={proposal['requires_confirmation']}",
            error=proposal.get("blocked_reason") or proposal.get("reason") or "",
            related_files=self._proposal_related_files(context=context, task=task, state=state),
            strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
            subgoal_id=proposal.get("failed_subgoal_id", ""),
            reason="replan_request produced reviewable proposal",
            node_id=self._repair_session_node_id(node_type="replan_proposal", step_index=-1, step_id=proposal["proposal_id"], tick=current_tick),
        )
        return proposal

    def _build_replan_proposal(
        self,
        *,
        context: Dict[str, Any],
        task: Dict[str, Any],
        state: Dict[str, Any],
        replan_request: Dict[str, Any],
        current_tick: int,
        reason: Any,
        failed_subgoal_id: str,
        blocked_reason: Any,
    ) -> Dict[str, Any]:
        strategy = self._normalize_repair_strategy(context.get("strategy"))
        multi_file_plan = context.get("multi_file_plan") if isinstance(context.get("multi_file_plan"), dict) else {}
        repo_impact = context.get("repo_impact") if isinstance(context.get("repo_impact"), dict) else {}
        blocked_text = self._first_nonempty_str(
            blocked_reason,
            replan_request.get("blocked_reason"),
            multi_file_plan.get("blocked_reason") if isinstance(multi_file_plan, dict) else "",
            repo_impact.get("blocked_reason") if isinstance(repo_impact, dict) else "",
            reason,
            replan_request.get("reason"),
        )
        risk_level = str(multi_file_plan.get("risk_level") or repo_impact.get("risk_level") or "low")
        exhausted = bool(strategy.get("exhausted", False))
        blocked_lower = blocked_text.lower()
        requires_confirmation = bool(
            multi_file_plan.get("requires_confirmation")
            or repo_impact.get("requires_confirmation")
            or any(token in blocked_lower for token in ("confirmation", "repo source", "high risk"))
        )

        if exhausted:
            action = "abort_goal"
        elif requires_confirmation:
            action = "require_confirmation"
        elif multi_file_plan:
            action = "split_subgoal"
        elif self._subgoal_can_switch_strategy(strategy):
            action = "switch_strategy"
        else:
            action = "retry_same_subgoal"

        proposed_subgoals = self._proposed_subgoals_for_action(action=action, failed_subgoal_id=failed_subgoal_id, multi_file_plan=multi_file_plan)
        proposed_steps = self._proposed_steps_for_action(action=action, strategy=strategy, blocked_reason=blocked_text, multi_file_plan=multi_file_plan)
        request_id = str(replan_request.get("request_id") or self._build_replan_request_id(failed_subgoal_id=failed_subgoal_id, reason=blocked_text, tick=current_tick))
        proposal_id = "replan-proposal-" + request_id.replace("replan-request-", "", 1)
        return self._normalize_replan_proposal(
            {
                "proposal_id": proposal_id,
                "source_replan_request": copy.deepcopy(replan_request),
                "failed_subgoal_id": failed_subgoal_id,
                "reason": self._truncate_text(reason or replan_request.get("reason") or blocked_text, 500),
                "proposed_action": action,
                "proposed_subgoals": proposed_subgoals,
                "proposed_steps": proposed_steps,
                "risk_level": risk_level,
                "requires_confirmation": requires_confirmation or action in {"require_confirmation", "abort_goal"},
                "blocked_reason": blocked_text,
                "status": "proposed",
                "created_at": self._now(),
                "summary": f"{action}: {self._truncate_text(blocked_text or 'review replan request', 220)}",
            }
        )

    def _subgoal_can_switch_strategy(self, strategy: Dict[str, Any]) -> bool:
        strategies = strategy.get("available_strategies") if isinstance(strategy.get("available_strategies"), list) else []
        max_attempts = self._safe_int(strategy.get("max_strategy_attempts"), len(strategies) or 0)
        current_index = self._safe_int(strategy.get("strategy_index"), 0)
        return bool(strategies) and not bool(strategy.get("exhausted", False)) and current_index + 1 < min(len(strategies), max_attempts)

    def _proposed_subgoals_for_action(self, *, action: str, failed_subgoal_id: str, multi_file_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        if action != "split_subgoal" or not isinstance(multi_file_plan, dict):
            return []
        items = []
        for index, path in enumerate(self._normalize_file_list(multi_file_plan.get("failed_impacted_files")), start=1):
            items.append(
                {
                    "subgoal_id": f"{failed_subgoal_id or 'subgoal'}_split_{index}",
                    "title": f"Repair impacted file {path}",
                    "description": "Proposed metadata-only split for impacted regression failure",
                    "status": "pending",
                    "related_files": [path],
                    "risk_level": str(multi_file_plan.get("risk_level") or "medium"),
                    "requires_confirmation": bool(multi_file_plan.get("requires_confirmation", False)),
                    "steps": [],
                }
            )
        return items

    def _proposed_steps_for_action(self, *, action: str, strategy: Dict[str, Any], blocked_reason: str, multi_file_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        if action == "abort_goal":
            return []
        if action == "require_confirmation":
            return [
                {"type": "review_blocker", "description": self._truncate_text(blocked_reason or "review required", 300)},
                {"type": "wait_for_confirmation", "description": "Pause until an explicit approval or revised plan is provided"},
            ]
        if action == "split_subgoal":
            return [
                {"type": "review_multi_file_plan", "description": self._truncate_text(multi_file_plan.get("blocked_reason") or "review impacted files", 300)},
                {"type": "prepare_per_file_repairs", "description": "Draft per-file repair steps for confirmation before any apply phase"},
            ]
        if action == "switch_strategy":
            strategies = strategy.get("available_strategies") if isinstance(strategy.get("available_strategies"), list) else []
            next_index = self._safe_int(strategy.get("strategy_index"), 0) + 1
            next_strategy = strategies[next_index] if 0 <= next_index < len(strategies) else ""
            return [
                {"type": "repair", "strategy": next_strategy, "description": "Draft repair using the next available strategy"},
                {"type": "apply", "strategy": next_strategy, "description": "Apply only after normal runtime gates allow it"},
                {"type": "verify", "strategy": next_strategy, "description": "Run existing verification and regression checks"},
            ]
        return [
            {"type": "retry_same_subgoal", "description": "Retry the failed subgoal after review"},
            {"type": "verify", "description": "Run existing verification checks"},
        ]

    def _proposal_related_files(self, *, context: Dict[str, Any], task: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
        repo_impact = context.get("repo_impact") if isinstance(context.get("repo_impact"), dict) else {}
        multi_file_plan = context.get("multi_file_plan") if isinstance(context.get("multi_file_plan"), dict) else {}
        files = self._normalize_file_list(repo_impact.get("changed_files"))
        files.extend(path for path in self._normalize_file_list(repo_impact.get("impacted_files")) if path not in files)
        files.extend(path for path in self._normalize_file_list(multi_file_plan.get("failed_impacted_files")) if path not in files)
        steps = state.get("steps") if isinstance(state.get("steps"), list) else task.get("steps") if isinstance(task.get("steps"), list) else []
        files.extend(path for path in self._infer_related_files_from_steps(steps) if path not in files)
        return files

    def _update_goal_state_after_step(self, *, context: Dict[str, Any], state: Dict[str, Any], step_index: int, step_result: Dict[str, Any], failed: bool, current_tick: int = 0) -> None:
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        steps = state.get("steps") if isinstance(state.get("steps"), list) else []
        subgoal = self._subgoal_for_step_index(goal_state, steps, step_index)
        subgoal_id = str(subgoal.get("subgoal_id") or "") if isinstance(subgoal, dict) else ""
        if not subgoal_id:
            return
        if failed:
            reason = self._stringify_failure_message(step_result.get("error") or step_result.get("message") or "subgoal failed")
            self._set_subgoal_status(goal_state, subgoal_id, "failed", reason=reason)
            goal_state["current_subgoal_id"] = subgoal_id
            goal_state["replan_request"] = {
                "request_id": self._build_replan_request_id(
                    failed_subgoal_id=subgoal_id,
                    reason=reason,
                    tick=current_tick,
                ),
                "failed_subgoal_id": subgoal_id,
                "reason": self._truncate_text(reason, 500),
                "suggested_next_action": "review failure and provide a replan or confirmation",
                "tick": current_tick,
            }
            goal_state["replan_count"] = self._safe_int(goal_state.get("replan_count"), 0) + 1
            context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="failed")
            self._ensure_replan_proposal(
                context=context,
                task={},
                state=state,
                current_tick=current_tick,
                reason=reason,
                failed_subgoal_id=subgoal_id,
            )
            return

        indices = self._subgoal_step_indices(subgoal, steps)
        next_index = self._safe_int(state.get("current_step_index"), step_index + 1)
        if indices and all(index < next_index for index in indices):
            if bool(state.get("terminal_validation_required")) and next_index >= len(steps):
                self._set_subgoal_status(goal_state, subgoal_id, "needs_observation", result_summary="subgoal execution completed; terminal validation pending")
            else:
                self._set_subgoal_status(goal_state, subgoal_id, "finished", result_summary="subgoal steps completed")
        else:
            self._set_subgoal_status(goal_state, subgoal_id, "running")
        goal_state["current_subgoal_id"] = subgoal_id
        context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state)

    def _normalize_repair_session(self, value: Any) -> Dict[str, Any]:
        session = copy.deepcopy(value) if isinstance(value, dict) else {}
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            session_id = f"repair-session-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        nodes = session.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
        normalized_nodes = []
        for item in nodes:
            if isinstance(item, dict):
                normalized_nodes.append(self._compact_repair_session_node(item))
        normalized_nodes = normalized_nodes[-MAX_STORED_LIST_ITEMS:]

        edges = session.get("edges")
        if not isinstance(edges, list):
            edges = []
        normalized_edges = []
        for item in edges:
            if not isinstance(item, dict):
                continue
            source = str(item.get("from") or "").strip()
            target = str(item.get("to") or "").strip()
            if not source or not target:
                continue
            normalized_edges.append(
                {
                    "from": source,
                    "to": target,
                    "reason": self._truncate_text(item.get("reason"), 240),
                    "tick": self._safe_int(item.get("tick"), 0),
                }
            )
        normalized_edges = normalized_edges[-MAX_STORED_LIST_ITEMS:]

        status = str(session.get("status") or "running").strip().lower()
        if status not in {"running", "finished", "failed"}:
            status = "running"

        return {
            "session_id": session_id,
            "started_at": str(session.get("started_at") or self._now()),
            "finished_at": str(session.get("finished_at") or ""),
            "status": status,
            "nodes": normalized_nodes,
            "edges": normalized_edges,
            "current_node_id": str(session.get("current_node_id") or ""),
            "terminal_node_id": str(session.get("terminal_node_id") or ""),
            "summary": copy.deepcopy(session.get("summary")) if isinstance(session.get("summary"), dict) else {},
        }

    def _compact_repair_session_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        safe = {
            "node_id": str(node.get("node_id") or ""),
            "type": str(node.get("type") or ""),
            "step_index": self._safe_int(node.get("step_index"), -1),
            "step_id": str(node.get("step_id") or ""),
            "tick": self._safe_int(node.get("tick"), 0),
            "status": str(node.get("status") or "running"),
            "input_summary": self._truncate_text(node.get("input_summary"), 500),
            "output_summary": self._truncate_text(node.get("output_summary"), 500),
            "error": self._truncate_text(node.get("error"), 500),
            "related_files": self._normalize_file_list(node.get("related_files")),
            "strategy": str(node.get("strategy") or ""),
            "rollback_link": str(node.get("rollback_link") or ""),
            "parent_node_id": str(node.get("parent_node_id") or ""),
            "subgoal_id": str(node.get("subgoal_id") or ""),
        }
        return safe

    def _truncate_text(self, value: Any, limit: int = 500) -> str:
        text = self._stringify_failure_message(value) if not isinstance(value, str) else value
        text = str(text or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 24)] + f"... <truncated {len(text) - max(0, limit - 24)} chars>"

    def _normalize_file_list(self, value: Any) -> List[str]:
        items: List[str] = []
        if isinstance(value, list):
            raw_items = value
        elif value is None:
            raw_items = []
        else:
            raw_items = [value]
        for item in raw_items:
            text = str(item or "").strip().replace("\\", "/")
            if text and text not in items:
                items.append(text)
        return items[:50]

    def _repair_session_is_terminal(self, context: Dict[str, Any]) -> bool:
        session = context.get("repair_session") if isinstance(context, dict) else None
        return isinstance(session, dict) and str(session.get("status") or "").strip().lower() in {"finished", "failed"}

    def _repair_session_node_id(self, *, node_type: str, step_index: int = -1, step_id: str = "", tick: int = 0, suffix: str = "") -> str:
        raw = f"{node_type}:{step_index}:{step_id}:{tick}:{suffix}"
        return "".join(ch if ch.isalnum() or ch in {"-", "_", ":"} else "_" for ch in raw)

    def _append_repair_session_node(
        self,
        *,
        context: Dict[str, Any],
        node_type: str,
        status: str,
        tick: int = 0,
        step_index: int = -1,
        step_id: str = "",
        input_summary: Any = "",
        output_summary: Any = "",
        error: Any = "",
        related_files: Any = None,
        strategy: str = "",
        rollback_link: str = "",
        subgoal_id: str = "",
        reason: str = "",
        node_id: str = "",
    ) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        session = self._normalize_repair_session(context.get("repair_session"))
        if str(session.get("status") or "") in {"finished", "failed"}:
            context["repair_session"] = session
            return session

        if not node_id:
            node_id = self._repair_session_node_id(node_type=node_type, step_index=step_index, step_id=step_id, tick=tick)
        if not subgoal_id:
            goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
            subgoal_id = str(goal_state.get("current_subgoal_id") or "")
        parent_node_id = str(session.get("current_node_id") or "")
        nodes = session.setdefault("nodes", [])
        existing = next((item for item in nodes if isinstance(item, dict) and item.get("node_id") == node_id), None)
        node = self._compact_repair_session_node(
            {
                "node_id": node_id,
                "type": node_type,
                "step_index": step_index,
                "step_id": step_id,
                "tick": tick,
                "status": status,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "error": error,
                "related_files": related_files,
                "strategy": strategy,
                "rollback_link": rollback_link,
                "subgoal_id": subgoal_id,
                "parent_node_id": parent_node_id if not existing else existing.get("parent_node_id", parent_node_id),
            }
        )
        if existing:
            existing.update(node)
        else:
            nodes.append(node)
            if parent_node_id and parent_node_id != node_id:
                edges = session.setdefault("edges", [])
                edge = {
                    "from": parent_node_id,
                    "to": node_id,
                    "reason": self._truncate_text(reason or f"{parent_node_id} -> {node_type}", 240),
                    "tick": self._safe_int(tick, 0),
                }
                if not any(item.get("from") == edge["from"] and item.get("to") == edge["to"] for item in edges if isinstance(item, dict)):
                    edges.append(edge)
                    session["edges"] = edges[-MAX_STORED_LIST_ITEMS:]
        session["nodes"] = nodes[-MAX_STORED_LIST_ITEMS:]
        session["current_node_id"] = node_id
        context["repair_session"] = session
        return session

    def _finalize_repair_session(self, *, context: Dict[str, Any], status: str, terminal_reason: Any = "") -> None:
        if not isinstance(context, dict):
            return
        session = self._normalize_repair_session(context.get("repair_session"))
        final_status = "finished" if str(status or "").strip().lower() == "finished" else "failed"
        session["status"] = final_status
        session["finished_at"] = self._now()
        session["terminal_node_id"] = str(session.get("current_node_id") or session.get("terminal_node_id") or "")
        session["summary"] = self._build_repair_session_summary(context=context, final_status=final_status, terminal_reason=terminal_reason)
        context["repair_session"] = session

    def _build_repair_session_summary(self, *, context: Dict[str, Any], final_status: str, terminal_reason: Any = "") -> Dict[str, Any]:
        session = self._normalize_repair_session(context.get("repair_session") if isinstance(context, dict) else {})
        nodes = [item for item in session.get("nodes", []) if isinstance(item, dict)]
        repo_impact = context.get("repo_impact") if isinstance(context, dict) and isinstance(context.get("repo_impact"), dict) else {}
        changed_files = self._normalize_file_list(repo_impact.get("changed_files"))
        impacted_files = self._normalize_file_list(repo_impact.get("impacted_files"))
        strategies = []
        for node in nodes:
            strategy = str(node.get("strategy") or "").strip()
            if strategy and strategy not in strategies:
                strategies.append(strategy)
        strategy_context = context.get("strategy") if isinstance(context, dict) and isinstance(context.get("strategy"), dict) else {}
        current_strategy = str(strategy_context.get("current_strategy") or "").strip()
        if current_strategy and current_strategy not in strategies:
            strategies.append(current_strategy)
        for item in strategy_context.get("strategy_history", []) if isinstance(strategy_context.get("strategy_history"), list) else []:
            if isinstance(item, dict):
                strategy = str(item.get("strategy") or "").strip()
                if strategy and strategy not in strategies:
                    strategies.append(strategy)
        engineering_goal_state = (
            context.get("engineering_goal_state")
            if isinstance(context, dict) and isinstance(context.get("engineering_goal_state"), dict)
            else {}
        )
        goal_summary = (
            engineering_goal_state.get("summary")
            if isinstance(engineering_goal_state.get("summary"), dict)
            else {}
        )
        repair_session = (
            context.get("repair_session")
            if isinstance(context, dict) and isinstance(context.get("repair_session"), dict)
            else {}
        )

        return {
            "total_nodes": len(nodes),
            "failed_nodes": len([item for item in nodes if str(item.get("status") or "") in {"failed", "blocked"}]),
            "rollback_count": len([item for item in nodes if item.get("type") == "rollback"]),
            "repair_depth": len([item for item in nodes if item.get("type") in {"repair", "apply", "rollback", "strategy_switch", "regression_verify"}]),
            "strategy_retry_count": len([item for item in nodes if item.get("type") == "strategy_switch"]),
            "quarantined": bool(repair_session.get("quarantined", False)),
            "strategies_used": strategies,
            "changed_files": changed_files,
            "impacted_files": impacted_files,
            "final_status": final_status,
            "terminal_reason": self._truncate_text(terminal_reason, 500),
            "total_subgoals": int(goal_summary.get("total_subgoals", 0) or 0),
            "completed_subgoals": int(goal_summary.get("completed_subgoals", 0) or 0),
            "failed_subgoals": int(goal_summary.get("failed_subgoals", 0) or 0),
            "blocked_subgoals": int(goal_summary.get("blocked_subgoals", 0) or 0),
            "current_subgoal_id": str(engineering_goal_state.get("current_subgoal_id") or ""),
            "goal_status": str(engineering_goal_state.get("status") or final_status),
        }

    def _link_latest_apply_to_rollback(self, *, context: Dict[str, Any], rollback_node_id: str) -> None:
        session = context.get("repair_session") if isinstance(context, dict) else None
        if not isinstance(session, dict):
            return
        nodes = session.get("nodes")
        if not isinstance(nodes, list):
            return
        for node in reversed(nodes):
            if isinstance(node, dict) and node.get("type") == "apply" and not str(node.get("rollback_link") or "").strip():
                node["rollback_link"] = rollback_node_id
                break

    def _update_repair_context_from_step_record(
        self,
        *,
        state: Dict[str, Any],
        task: Dict[str, Any],
        step_record: Dict[str, Any],
        failed: bool,
    ) -> None:
        if not isinstance(state, dict) or not isinstance(step_record, dict):
            return

        step = step_record.get("step") if isinstance(step_record.get("step"), dict) else {}
        result = step_record.get("result") if isinstance(step_record.get("result"), dict) else {}
        step_type = str(step.get("type") or result.get("step_type") or "").strip().lower()
        repair_types = {
            "verify",
            "verify_file",
            "verify_unified_diff",
            "verify_patch",
            "code_chain_analyze",
            "code_chain_verify",
            "code_chain_repair",
            "autonomous_code_repair",
            "code_chain_repair_preflight_failed",
            "apply_unified_diff",
            "apply_patch",
            "write_file",
            "workspace_write",
        }

        task_repair_context = task.get("repair_context") if isinstance(task, dict) else None
        has_repair_metadata = bool(task_repair_context) or bool(
            any(str(task.get(key) or "").strip() for key in ("failed_file", "failed_reason", "repair_intent"))
            if isinstance(task, dict)
            else False
        )
        if step_type not in repair_types and not has_repair_metadata:
            return

        context = self._normalize_repair_context(state.get("repair_context", task_repair_context))

        original_failed_step = task.get("failed_step") if isinstance(task, dict) else None
        if isinstance(original_failed_step, dict) and not isinstance(context.get("original_failed_step"), dict):
            context["original_failed_step"] = copy.deepcopy(original_failed_step)
            context["failed_step"] = copy.deepcopy(original_failed_step)

        failed_file = self._first_nonempty_str(
            context.get("failed_file"),
            task.get("failed_file") if isinstance(task, dict) else "",
            step.get("target_path"),
            step.get("file_path"),
            step.get("path") if step_type not in {"verify_unified_diff", "verify_patch", "apply_unified_diff", "apply_patch"} else "",
            step.get("target"),
        )
        if failed_file:
            context["failed_file"] = failed_file

        failed_reason = self._first_nonempty_str(
            context.get("failed_reason"),
            task.get("failed_reason") if isinstance(task, dict) else "",
            task.get("last_error") if isinstance(task, dict) else "",
            task.get("failure_message") if isinstance(task, dict) else "",
            result.get("error"),
            result.get("message") if failed else "",
        )
        if failed_reason:
            context["failed_reason"] = failed_reason

        phase = self._repair_phase_for_step_type(step_type)
        compact_record = self._sanitize_step_record(step_record)
        context["last_phase"] = phase
        if failed:
            context["last_error"] = self._stringify_failure_message(result.get("error") or result.get("message"))

        repair_payload = self._extract_repair_payload(result)
        if repair_payload.get("original_file_content"):
            context["original_file_content"] = repair_payload["original_file_content"]
        if repair_payload.get("proposed_fix"):
            context["proposed_fix"] = repair_payload["proposed_fix"]
        if isinstance(repair_payload.get("final_edit_payload"), dict):
            context["final_edit_payload"] = copy.deepcopy(repair_payload["final_edit_payload"])
        if isinstance(repair_payload.get("requested_functions"), list):
            context["requested_functions"] = copy.deepcopy(repair_payload["requested_functions"])
        if isinstance(repair_payload.get("failed_functions"), list):
            context["failed_functions"] = copy.deepcopy(repair_payload["failed_functions"])
        if isinstance(repair_payload.get("verification_result"), dict):
            context["verification_result"] = copy.deepcopy(repair_payload["verification_result"])
        if isinstance(repair_payload.get("repo_impact"), dict):
            context["repo_impact"] = copy.deepcopy(repair_payload["repo_impact"])
            if isinstance(repair_payload["repo_impact"].get("dependency_graph"), dict):
                context["dependency_graph"] = copy.deepcopy(repair_payload["repo_impact"]["dependency_graph"])
        if isinstance(repair_payload.get("dependency_graph"), dict):
            context["dependency_graph"] = copy.deepcopy(repair_payload["dependency_graph"])
        if isinstance(repair_payload.get("per_file_rollback_metadata"), list):
            existing = context.get("per_file_rollback_metadata")
            if not isinstance(existing, list):
                existing = []
            merged = existing + [copy.deepcopy(item) for item in repair_payload["per_file_rollback_metadata"] if isinstance(item, dict)]
            seen = set()
            deduped = []
            for item in merged:
                key = (str(item.get("target_path") or ""), str(item.get("backup_path") or ""))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            context["per_file_rollback_metadata"] = deduped[-MAX_STORED_LIST_ITEMS:]
        if isinstance(repair_payload.get("strategy"), str) and repair_payload["strategy"]:
            strategy = self._normalize_repair_strategy(context.get("strategy"))
            strategy["current_strategy"] = repair_payload["strategy"]
            context["strategy"] = strategy
        if phase == "apply":
            rollback = self._extract_rollback_metadata(
                result=result,
                step=step,
                step_record=step_record,
                current=context.get("rollback"),
            )
            if rollback.get("restore_available"):
                context["rollback"] = rollback

        phase_results = context.get("phase_results")
        if not isinstance(phase_results, dict):
            phase_results = {}
            context["phase_results"] = phase_results
        phase_results[phase] = copy.deepcopy(compact_record)

        if phase == "repair":
            context["repair_result"] = copy.deepcopy(compact_record)
        elif phase == "apply":
            context["apply_result"] = copy.deepcopy(compact_record)
        elif phase == "verify":
            context["verify_result"] = copy.deepcopy(compact_record)

        flow = context.get("flow")
        if not isinstance(flow, list):
            flow = []
            context["flow"] = flow
        flow.append(
            {
                "step_index": step_record.get("step_index"),
                "step_type": step_type,
                "phase": phase,
                "ok": not failed,
                "tick": step_record.get("tick"),
                "ts": step_record.get("ts"),
                "message": self._first_nonempty_str(result.get("message"), result.get("final_answer")),
                "error": self._stringify_failure_message(result.get("error")) if failed else "",
            }
        )
        context["flow"] = flow[-MAX_STORED_LIST_ITEMS:]
        self._record_repair_session_step_node(
            context=context,
            step=step,
            result=result,
            step_record=step_record,
            phase=phase,
            failed=failed,
        )
        state["repair_context"] = context

    def _record_repair_session_step_node(
        self,
        *,
        context: Dict[str, Any],
        step: Dict[str, Any],
        result: Dict[str, Any],
        step_record: Dict[str, Any],
        phase: str,
        failed: bool,
    ) -> None:
        step_type = str(step.get("type") or result.get("step_type") or "").strip().lower()
        if step_type not in {
            "code_chain_verify",
            "verify",
            "verify_file",
            "code_chain_repair",
            "autonomous_code_repair",
            "apply_patch",
            "apply_unified_diff",
        }:
            return

        node_type = phase
        if step_type in {"code_chain_repair", "autonomous_code_repair"}:
            node_type = "repair"
        elif step_type in {"apply_patch", "apply_unified_diff"}:
            node_type = "apply"
        elif step_type in {"code_chain_verify", "verify", "verify_file"}:
            node_type = "final_verify" if isinstance(context.get("apply_result"), dict) else "verify"

        result_block = result.get("result") if isinstance(result.get("result"), dict) else {}
        related_files = self._normalize_file_list(
            [
                step.get("target_path"),
                step.get("path"),
                result.get("target_path"),
                result_block.get("target_path") if isinstance(result_block, dict) else "",
            ]
        )
        repo_impact = context.get("repo_impact") if isinstance(context.get("repo_impact"), dict) else {}
        related_files.extend(path for path in self._normalize_file_list(repo_impact.get("changed_files")) if path not in related_files)
        related_files.extend(path for path in self._normalize_file_list(repo_impact.get("impacted_files")) if path not in related_files)

        strategy = ""
        strategy_context = context.get("strategy") if isinstance(context.get("strategy"), dict) else {}
        if isinstance(strategy_context, dict):
            strategy = str(strategy_context.get("current_strategy") or "")
        if isinstance(result.get("strategy"), str):
            strategy = str(result.get("strategy") or strategy)
        elif isinstance(result_block, dict) and isinstance(result_block.get("strategy"), str):
            strategy = str(result_block.get("strategy") or strategy)

        status = "failed" if failed else "success"
        error = result.get("error") if failed else ""
        output_summary = self._first_nonempty_str(result.get("message"), result.get("final_answer"), result_block.get("message") if isinstance(result_block, dict) else "")
        if not output_summary and isinstance(result_block, dict):
            output_summary = self._truncate_text({key: result_block.get(key) for key in ("verification_passed", "failed_functions", "changed_files") if key in result_block})

        self._append_repair_session_node(
            context=context,
            node_type=node_type,
            status=status,
            tick=self._safe_int(step_record.get("tick"), 0),
            step_index=self._safe_int(step_record.get("step_index"), -1),
            step_id=str(step.get("id") or step.get("step_id") or ""),
            input_summary=self._first_nonempty_str(step.get("task_text"), step.get("instruction"), step.get("goal"), step.get("target_path"), step.get("path")),
            output_summary=output_summary,
            error=error,
            related_files=related_files,
            strategy=strategy,
            rollback_link=str((context.get("rollback") or {}).get("target_path") or "") if isinstance(context.get("rollback"), dict) else "",
            reason=f"{node_type} after {phase}",
        )

    def _repair_phase_for_step_type(self, step_type: str) -> str:
        value = str(step_type or "").strip().lower()
        if "apply" in value or value in {"write_file", "workspace_write"}:
            return "apply"
        if "repair" in value or value in {"llm", "llm_generate", "verify_unified_diff", "verify_patch"}:
            return "repair"
        return "verify"

    def _extract_repair_payload(self, result: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if not isinstance(result, dict):
            return payload

        sources: List[Dict[str, Any]] = [result]
        result_block = result.get("result")
        if isinstance(result_block, dict):
            sources.append(result_block)
            nested = result_block.get("result")
            if isinstance(nested, dict):
                sources.append(nested)

        for source in sources:
            for key in ("original_file_content", "original_content"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    payload["original_file_content"] = value
                    break
            for key in ("proposed_fix", "new_text", "content"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    payload["proposed_fix"] = value
                    break
            for key in ("final_edit_payload", "edit_payload", "apply_payload"):
                value = source.get(key)
                if isinstance(value, dict) and value:
                    payload["final_edit_payload"] = copy.deepcopy(value)
                    break
            for key in ("requested_functions", "failed_functions"):
                value = source.get(key)
                if isinstance(value, list):
                    payload[key] = [str(item).strip() for item in value if str(item).strip()]
            value = source.get("strategy")
            if isinstance(value, str) and value.strip():
                payload["strategy"] = value.strip()
            value = source.get("verification")
            if isinstance(value, dict):
                payload["verification_result"] = copy.deepcopy(value)
            value = source.get("repo_impact")
            if isinstance(value, dict):
                payload["repo_impact"] = copy.deepcopy(value)
                if isinstance(value.get("dependency_graph"), dict):
                    payload["dependency_graph"] = copy.deepcopy(value["dependency_graph"])
            value = source.get("dependency_graph")
            if isinstance(value, dict):
                payload["dependency_graph"] = copy.deepcopy(value)
            value = source.get("per_file_rollback_metadata")
            if isinstance(value, list):
                payload["per_file_rollback_metadata"] = [copy.deepcopy(item) for item in value if isinstance(item, dict)]
            error = source.get("error")
            if isinstance(error, dict):
                details = error.get("details")
                if isinstance(details, dict) and isinstance(details.get("repo_impact"), dict):
                    payload["repo_impact"] = copy.deepcopy(details["repo_impact"])
                    if isinstance(details["repo_impact"].get("dependency_graph"), dict):
                        payload["dependency_graph"] = copy.deepcopy(details["repo_impact"]["dependency_graph"])
                if isinstance(details, dict) and isinstance(details.get("per_file_rollback_metadata"), list):
                    payload["per_file_rollback_metadata"] = [
                        copy.deepcopy(item) for item in details["per_file_rollback_metadata"] if isinstance(item, dict)
                    ]

        return payload

    def _extract_rollback_metadata(
        self,
        *,
        result: Dict[str, Any],
        step: Dict[str, Any],
        step_record: Dict[str, Any],
        current: Any = None,
    ) -> Dict[str, Any]:
        rollback = copy.deepcopy(current) if isinstance(current, dict) else {}
        sources: List[Dict[str, Any]] = []
        if isinstance(result, dict):
            sources.append(result)
            result_block = result.get("result")
            if isinstance(result_block, dict):
                sources.append(result_block)

        for source in sources:
            value = source.get("rollback_metadata")
            if isinstance(value, dict):
                rollback.update(copy.deepcopy(value))
                per_file = value.get("per_file")
                if isinstance(per_file, list):
                    rollback["per_file"] = [copy.deepcopy(item) for item in per_file if isinstance(item, dict)]
            for key in ("target_path", "full_target_path", "backup_path"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    rollback[key] = value.strip()
            edit_payload = source.get("edit_payload")
            if isinstance(edit_payload, dict):
                if isinstance(edit_payload.get("old_text"), str):
                    rollback["old_text"] = edit_payload.get("old_text")
                if isinstance(edit_payload.get("new_text"), str):
                    rollback["new_text"] = edit_payload.get("new_text")
                if isinstance(edit_payload.get("schema"), str):
                    rollback["schema"] = edit_payload.get("schema")

        rollback["step_id"] = str(step.get("id") or step.get("step_id") or "")
        rollback["step_index"] = self._safe_int(step_record.get("step_index"), 0)
        rollback["applied_at_tick"] = self._safe_int(step_record.get("tick"), 0)
        rollback.setdefault("schema", "replacement_pair_v1")
        rollback["restore_available"] = bool(
            (
                str(rollback.get("target_path") or rollback.get("full_target_path") or "").strip()
                and (
                    str(rollback.get("backup_path") or "").strip()
                    or isinstance(rollback.get("old_text"), str)
                )
            )
            or bool(rollback.get("per_file"))
        )
        return rollback

    def _normalize_repair_strategy(self, value: Any) -> Dict[str, Any]:
        strategies = ["minimal_patch", "function_rewrite", "full_file_rewrite_safe"]
        strategy = copy.deepcopy(value) if isinstance(value, dict) else {}
        attempted = strategy.get("attempted_strategies")
        if not isinstance(attempted, list):
            attempted = []
        history = strategy.get("strategy_history")
        if not isinstance(history, list):
            history = []
        index = self._safe_int(strategy.get("strategy_index"), 0)
        if index < 0:
            index = 0
        if index >= len(strategies):
            index = len(strategies) - 1
        current = str(strategy.get("current_strategy") or strategies[index]).strip()
        if current not in strategies:
            current = strategies[index]
        return {
            "current_strategy": current,
            "attempted_strategies": [str(item) for item in attempted if str(item).strip()],
            "max_strategy_attempts": self._safe_int(strategy.get("max_strategy_attempts"), len(strategies)),
            "strategy_index": strategies.index(current),
            "strategy_history": [copy.deepcopy(item) for item in history if isinstance(item, dict)],
            "last_strategy_failure": copy.deepcopy(strategy.get("last_strategy_failure", {})) if isinstance(strategy.get("last_strategy_failure"), dict) else {},
            "exhausted": bool(strategy.get("exhausted", False)),
            "available_strategies": strategies,
        }

    def advance_repair_strategy_after_failure(
        self,
        task: Dict[str, Any],
        *,
        current_tick: int = 0,
        failure_reason: Any = None,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        context = self._normalize_repair_context(state.get("repair_context"))
        strategy = self._normalize_repair_strategy(context.get("strategy"))
        strategies = list(strategy.get("available_strategies") or ["minimal_patch", "function_rewrite", "full_file_rewrite_safe"])
        current = str(strategy.get("current_strategy") or strategies[0])
        failure_text = self._stringify_failure_message(failure_reason)
        repair_step_index = self._find_repair_step_index(state)
        if repair_step_index < 0:
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = failure_text
            self._finalize_repair_session(context=context, status="failed", terminal_reason="repair strategy retry requires a repair step")
            state["repair_context"] = context
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {
                "ok": False,
                "exhausted": False,
                "no_retry": True,
                "reason": "repair strategy retry requires a repair step",
                "runtime_state": state,
                "task": copy.deepcopy(task),
            }

        history = strategy.get("strategy_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "strategy": current,
                "outcome": "failed",
                "reason": failure_text,
                "tick": current_tick,
                "ts": self._now(),
            }
        )
        attempted = strategy.get("attempted_strategies")
        if not isinstance(attempted, list):
            attempted = []
        if current not in attempted:
            attempted.append(current)

        next_index = strategies.index(current) + 1 if current in strategies else 1
        can_continue = next_index < min(len(strategies), self._safe_int(strategy.get("max_strategy_attempts"), len(strategies)))
        if not can_continue:
            strategy.update(
                {
                    "attempted_strategies": attempted,
                    "strategy_history": history,
                    "last_strategy_failure": {"strategy": current, "reason": failure_text, "tick": current_tick},
                    "exhausted": True,
                }
            )
            context["strategy"] = strategy
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = failure_text
            goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
            current_subgoal_id = str(goal_state.get("current_subgoal_id") or "")
            if current_subgoal_id:
                goal_state["replan_request"] = {
                    "request_id": self._build_replan_request_id(
                        failed_subgoal_id=current_subgoal_id,
                        reason=failure_text or "strategy exhausted",
                        tick=current_tick,
                    ),
                    "failed_subgoal_id": current_subgoal_id,
                    "reason": self._truncate_text(failure_text or "strategy exhausted", 500),
                    "strategy_exhausted": True,
                    "suggested_next_action": "review exhausted strategy and decide whether to abort or manually replan",
                    "tick": current_tick,
                }
                context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="failed")
            self._ensure_replan_proposal(
                context=context,
                task=task,
                state=state,
                current_tick=current_tick,
                reason=failure_text or "strategy exhausted",
                failed_subgoal_id=current_subgoal_id,
            )
            self._finalize_repair_session(context=context, status="failed", terminal_reason=failure_text)
            state["repair_context"] = context
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {"ok": False, "exhausted": True, "runtime_state": state, "task": copy.deepcopy(task)}

        next_strategy = strategies[next_index]
        history.append(
            {
                "strategy": next_strategy,
                "outcome": "selected",
                "previous_strategy": current,
                "tick": current_tick,
                "ts": self._now(),
            }
        )
        strategy.update(
            {
                "current_strategy": next_strategy,
                "attempted_strategies": attempted,
                "strategy_index": next_index,
                "strategy_history": history,
                "last_strategy_failure": {"strategy": current, "reason": failure_text, "tick": current_tick},
                "exhausted": False,
            }
        )
        context["strategy"] = strategy
        self._append_repair_session_node(
            context=context,
            node_type="strategy_switch",
            status="success",
            tick=current_tick,
            step_index=repair_step_index,
            step_id="strategy_switch",
            input_summary=f"previous_strategy={current}",
            output_summary=f"next_strategy={next_strategy}",
            error=failure_text,
            related_files=self._normalize_file_list((context.get("repo_impact") or {}).get("changed_files") if isinstance(context.get("repo_impact"), dict) else []),
            strategy=next_strategy,
            reason="rollback completed; selecting next repair strategy",
            node_id=self._repair_session_node_id(node_type="strategy_switch", step_index=repair_step_index, step_id=f"{current}_to_{next_strategy}", tick=current_tick),
        )
        # Clear per-apply phase artifacts so the next strategy gets fresh
        # apply/regression/rollback state, while retaining history in logs.
        context.pop("rollback", None)
        context.pop("rollback_result", None)
        context.pop("regression_verify", None)
        context.pop("repo_impact", None)
        context.pop("final_edit_payload", None)
        context.pop("repair_result", None)
        context.pop("apply_result", None)

        state["repair_context"] = context
        state["status"] = "running"
        state["last_error"] = None
        state["current_step_index"] = repair_step_index
        state["updated_at"] = self._now()
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        return {"ok": True, "exhausted": False, "next_strategy": next_strategy, "runtime_state": state, "task": copy.deepcopy(task)}

    def _find_repair_step_index(self, state: Dict[str, Any]) -> int:
        steps = state.get("steps")
        if isinstance(steps, list):
            for index, step in enumerate(steps):
                if isinstance(step, dict) and str(step.get("type") or "").strip().lower() in {"code_chain_repair", "autonomous_code_repair"}:
                    return index
        return -1

    def rollback_last_apply(
        self,
        task: Dict[str, Any],
        *,
        current_tick: int = 0,
        verify_error: Any = None,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        context = self._normalize_repair_context(state.get("repair_context"))
        existing_result = context.get("rollback_result")
        if isinstance(existing_result, dict) and existing_result.get("ok") is True:
            return {
                "ok": True,
                "status": state.get("status", "failed"),
                "skipped": True,
                "reason": "rollback already completed",
                "rollback_result": copy.deepcopy(existing_result),
                "runtime_state": state,
                "task": copy.deepcopy(task),
            }

        rollback = context.get("rollback")
        if not isinstance(rollback, dict) or not rollback.get("restore_available"):
            rollback_result = {
                "ok": False,
                "error": "rollback failed: restore metadata unavailable",
                "verify_error": self._stringify_failure_message(verify_error),
                "tick": current_tick,
            }
            context["rollback_result"] = rollback_result
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = self._combine_error_messages(verify_error, rollback_result.get("error"))
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {"ok": False, "status": "failed", "rollback_result": rollback_result, "runtime_state": state, "task": copy.deepcopy(task)}

        per_file = rollback.get("per_file")
        if not isinstance(per_file, list) or not per_file:
            per_file = context.get("per_file_rollback_metadata")

        if not isinstance(per_file, list) or not per_file:
            snapshot_sources = [
                rollback.get("backup_snapshot") if isinstance(rollback, dict) else None,
                context.get("backup_snapshot") if isinstance(context, dict) else None,
            ]

            apply_result = context.get("apply_result") if isinstance(context, dict) else None
            if isinstance(apply_result, dict):
                transaction = apply_result.get("transaction")
                if isinstance(transaction, dict):
                    snapshot_sources.append(transaction.get("backup_snapshot"))

            generated_per_file = []
            for snapshot in snapshot_sources:
                if not isinstance(snapshot, dict):
                    continue
                for key, item in snapshot.items():
                    if not isinstance(item, dict):
                        continue
                    target_path = str(item.get("target_path") or key or "").strip()
                    full_target_path = str(item.get("full_target_path") or target_path or "").strip()
                    backup_path = str(item.get("backup_path") or "").strip()
                    old_text = item.get("old_text")
                    generated_per_file.append(
                        {
                            "target_path": target_path,
                            "full_target_path": full_target_path,
                            "backup_path": backup_path,
                            "old_text": old_text,
                        }
                    )

            if generated_per_file:
                per_file = generated_per_file
                rollback["per_file"] = generated_per_file
                context["per_file_rollback_metadata"] = generated_per_file

        if isinstance(per_file, list) and per_file:
            restored_files: List[str] = []
            failed_files: List[Dict[str, Any]] = []
            for item in reversed([copy.deepcopy(entry) for entry in per_file if isinstance(entry, dict)]):
                item_target = str(item.get("target_path") or item.get("full_target_path") or "").strip()
                item_full_target = str(item.get("full_target_path") or item.get("target_path") or "").strip()
                item_backup = str(item.get("backup_path") or "").strip()
                try:
                    if item_backup:
                        if not os.path.exists(item_backup):
                            raise FileNotFoundError(f"backup_path not found: {item_backup}")
                        restore_text = self._persistence_for_path(item_backup).read_text(item_backup, default="")
                    elif isinstance(item.get("old_text"), str):
                        restore_text = item["old_text"]
                    else:
                        raise ValueError("rollback old_text unavailable")
                    if not item_full_target:
                        raise ValueError("rollback target_path unavailable")
                    self._persistence_for_path(item_full_target).write_text(
                        item_full_target,
                        restore_text,
                        reason="task_runtime_multi_file_rollback_restore",
                        lineage={
                            "source": "task_runtime",
                            "operation": "rollback_restore",
                            "target_path": str(item_full_target),
                        },
                        provenance={
                            "source": "task_runtime",
                            "operation": "rollback_restore",
                            "target_path": str(item_full_target),
                        },
                        metadata={"rollback": True, "multi_file": True},
                    )
                    restored_files.append(item_target)
                except Exception as exc:
                    failed_files.append({"target_path": item_target, "error": str(exc)})

            rollback_result = {
                "ok": not failed_files,
                "target_path": rollback.get("target_path", ""),
                "restored_files": restored_files,
                "failed_files": failed_files,
                "rolled_back_at_tick": current_tick,
                "verify_error": self._stringify_failure_message(verify_error),
                "multi_file": True,
            }
            context["rollback_result"] = rollback_result
            rollback_node_id = self._repair_session_node_id(node_type="rollback", step_index=self._safe_int(rollback.get("step_index"), -1), step_id="rollback", tick=current_tick)
            self._append_repair_session_node(
                context=context,
                node_type="rollback",
                status="success" if not failed_files else "failed",
                tick=current_tick,
                step_index=self._safe_int(rollback.get("step_index"), -1),
                step_id="rollback",
                input_summary=f"restore {len(per_file)} file(s)",
                output_summary=f"restored={len(restored_files)}; failed={len(failed_files)}",
                error="multi-file rollback failed" if failed_files else "",
                related_files=self._normalize_file_list(restored_files + [item.get("target_path", "") for item in failed_files]),
                strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
                reason="rollback after verification failure",
                node_id=rollback_node_id,
            )
            self._link_latest_apply_to_rollback(context=context, rollback_node_id=rollback_node_id)
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = self._combine_error_messages(verify_error, "" if not failed_files else "multi-file rollback failed")
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {
                "ok": not failed_files,
                "status": "failed",
                "rollback_result": rollback_result,
                "runtime_state": state,
                "task": copy.deepcopy(task),
            }

        target_path = str(rollback.get("full_target_path") or rollback.get("target_path") or "").strip()
        backup_path = str(rollback.get("backup_path") or "").strip()
        old_text = rollback.get("old_text")
        restore_source = ""

        try:
            if backup_path:
                if not os.path.exists(backup_path):
                    raise FileNotFoundError(f"backup_path not found: {backup_path}")
                restore_text = self._persistence_for_path(backup_path).read_text(backup_path, default="")
                restore_source = "backup_path"
            elif isinstance(old_text, str):
                restore_text = old_text
                restore_source = "old_text"
            else:
                raise ValueError("rollback old_text unavailable")

            if not target_path:
                raise ValueError("rollback target_path unavailable")
            self._persistence_for_path(target_path).write_text(
                target_path,
                restore_text,
                reason="task_runtime_rollback_restore",
                lineage={
                    "source": "task_runtime",
                    "operation": "rollback_restore",
                    "target_path": str(target_path),
                },
                provenance={
                    "source": "task_runtime",
                    "operation": "rollback_restore",
                    "target_path": str(target_path),
                },
                metadata={"rollback": True},
            )

            rollback_result = {
                "ok": True,
                "target_path": rollback.get("target_path", ""),
                "full_target_path": target_path,
                "backup_path": backup_path,
                "restore_source": restore_source,
                "restored_files": [rollback.get("target_path", "")],
                "failed_files": [],
                "rolled_back_at_tick": current_tick,
                "verify_error": self._stringify_failure_message(verify_error),
            }
            context["rollback_result"] = rollback_result
            rollback_node_id = self._repair_session_node_id(node_type="rollback", step_index=self._safe_int(rollback.get("step_index"), -1), step_id="rollback", tick=current_tick)
            self._append_repair_session_node(
                context=context,
                node_type="rollback",
                status="success",
                tick=current_tick,
                step_index=self._safe_int(rollback.get("step_index"), -1),
                step_id="rollback",
                input_summary=f"restore {rollback.get('target_path', '')}",
                output_summary=f"restore_source={restore_source}",
                error="",
                related_files=self._normalize_file_list([rollback.get("target_path", "")]),
                strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
                reason="rollback after verification failure",
                node_id=rollback_node_id,
            )
            self._link_latest_apply_to_rollback(context=context, rollback_node_id=rollback_node_id)
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = self._stringify_failure_message(verify_error)
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {"ok": True, "status": "failed", "rollback_result": rollback_result, "runtime_state": state, "task": copy.deepcopy(task)}
        except Exception as exc:
            rollback_error = f"rollback failed: {exc}"
            rollback_result = {
                "ok": False,
                "target_path": rollback.get("target_path", ""),
                "full_target_path": target_path,
                "backup_path": backup_path,
                "restored_files": [],
                "failed_files": [{"target_path": rollback.get("target_path", ""), "error": rollback_error}],
                "error": rollback_error,
                "rolled_back_at_tick": current_tick,
                "verify_error": self._stringify_failure_message(verify_error),
            }
            context["rollback_result"] = rollback_result
            rollback_node_id = self._repair_session_node_id(node_type="rollback", step_index=self._safe_int(rollback.get("step_index"), -1), step_id="rollback", tick=current_tick)
            self._append_repair_session_node(
                context=context,
                node_type="rollback",
                status="failed",
                tick=current_tick,
                step_index=self._safe_int(rollback.get("step_index"), -1),
                step_id="rollback",
                input_summary=f"restore {rollback.get('target_path', '')}",
                output_summary="rollback failed",
                error=rollback_error,
                related_files=self._normalize_file_list([rollback.get("target_path", "")]),
                strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
                reason="rollback after verification failure",
                node_id=rollback_node_id,
            )
            self._link_latest_apply_to_rollback(context=context, rollback_node_id=rollback_node_id)
            state["repair_context"] = context
            state["status"] = "failed"
            state["last_error"] = self._combine_error_messages(verify_error, rollback_error)
            state["updated_at"] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {"ok": False, "status": "failed", "rollback_result": rollback_result, "runtime_state": state, "task": copy.deepcopy(task)}

    def _combine_error_messages(self, primary: Any, secondary: Any) -> str:
        first = self._stringify_failure_message(primary)
        second = self._stringify_failure_message(secondary)
        if first and second:
            return f"{first}; {second}"
        return first or second

    def record_regression_verify(
        self,
        task: Dict[str, Any],
        *,
        regression_result: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        context = self._normalize_repair_context(state.get("repair_context"))
        payload = copy.deepcopy(regression_result if isinstance(regression_result, dict) else {})
        payload["tick"] = current_tick
        context["regression_verify"] = payload
        repo_impact = context.get("repo_impact") if isinstance(context.get("repo_impact"), dict) else {}
        regression_status = "success" if bool(payload.get("passed", False)) else "failed"
        failed_commands = payload.get("failed_commands") if isinstance(payload.get("failed_commands"), list) else []
        blocked_commands = payload.get("blocked_commands") if isinstance(payload.get("blocked_commands"), list) else []
        if blocked_commands:
            regression_status = "blocked"
        self._append_repair_session_node(
            context=context,
            node_type="regression_verify",
            status=regression_status,
            tick=current_tick,
            step_index=self._safe_int(context.get("apply_result", {}).get("step_index"), -1) if isinstance(context.get("apply_result"), dict) else -1,
            step_id="regression_verify",
            input_summary=f"{len(payload.get('commands', [])) if isinstance(payload.get('commands'), list) else 0} regression command(s)",
            output_summary=f"passed={bool(payload.get('passed', False))}; failed={len(failed_commands)}; blocked={len(blocked_commands)}",
            error=payload.get("error") or "",
            related_files=self._normalize_file_list(repo_impact.get("changed_files")) + [
                path for path in self._normalize_file_list(repo_impact.get("impacted_files"))
                if path not in self._normalize_file_list(repo_impact.get("changed_files"))
            ],
            strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
            reason="regression verification after apply",
            node_id=self._repair_session_node_id(node_type="regression_verify", step_index=self._safe_int(context.get("apply_result", {}).get("step_index"), -1) if isinstance(context.get("apply_result"), dict) else -1, step_id="regression_verify", tick=current_tick),
        )
        if not bool(payload.get("passed", False)):
            plan = self._build_multi_file_plan(context=context, regression_result=payload)
            if plan:
                context["multi_file_plan"] = plan
                self._append_repair_session_node(
                    context=context,
                    node_type="multi_file_plan",
                    status="blocked" if plan.get("requires_confirmation") else "success",
                    tick=current_tick,
                    step_index=-1,
                    step_id="multi_file_plan",
                    input_summary=f"root={plan.get('root_changed_file', '')}",
                    output_summary=f"failed_impacted_files={len(plan.get('failed_impacted_files', []))}; risk={plan.get('risk_level', '')}",
                    error=plan.get("blocked_reason", ""),
                    related_files=self._normalize_file_list([plan.get("root_changed_file")] + list(plan.get("failed_impacted_files", []))),
                    strategy=str((context.get("strategy") or {}).get("current_strategy") or "") if isinstance(context.get("strategy"), dict) else "",
                    reason="regression failure produced multi-file plan",
                    node_id=self._repair_session_node_id(node_type="multi_file_plan", step_index=-1, step_id="multi_file_plan", tick=current_tick),
                )
                goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
                failed_subgoal_id = str(goal_state.get("current_subgoal_id") or "")
                goal_state["replan_request"] = {
                    "request_id": self._build_replan_request_id(
                        failed_subgoal_id=failed_subgoal_id,
                        reason=plan.get("blocked_reason") or payload.get("error") or "multi-file plan blocked",
                        tick=current_tick,
                    ),
                    "failed_subgoal_id": failed_subgoal_id,
                    "reason": self._truncate_text(plan.get("blocked_reason") or payload.get("error") or "multi-file plan blocked", 500),
                    "blocked_reason": self._truncate_text(plan.get("blocked_reason"), 500),
                    "suggested_next_action": "review proposed split subgoals before applying any multi-file repair",
                    "tick": current_tick,
                }
                goal_state["replan_count"] = self._safe_int(goal_state.get("replan_count"), 0) + 1
                context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="blocked")
                self._ensure_replan_proposal(
                    context=context,
                    task=task,
                    state=state,
                    current_tick=current_tick,
                    reason=plan.get("blocked_reason") or payload.get("error") or "multi-file plan blocked",
                    failed_subgoal_id=failed_subgoal_id,
                    blocked_reason=plan.get("blocked_reason") or "",
                )
        state["repair_context"] = context
        if not bool(payload.get("passed", False)):
            state["last_error"] = str(payload.get("error") or "regression verification failed")
        state["updated_at"] = self._now()
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        return {
            "ok": bool(payload.get("passed", False)),
            "status": state.get("status", "running"),
            "runtime_state": state,
            "task": copy.deepcopy(task),
            "regression_verify": payload,
        }

    def _build_multi_file_plan(self, *, context: Dict[str, Any], regression_result: Dict[str, Any]) -> Dict[str, Any]:
        repo_impact = context.get("repo_impact")
        if not isinstance(repo_impact, dict):
            return {}
        impacted_files = [
            str(item).replace("\\", "/")
            for item in repo_impact.get("impacted_files", [])
            if str(item).strip()
        ]
        if not impacted_files:
            return {}

        failed_paths: List[str] = []
        failed_commands = regression_result.get("failed_commands")
        if isinstance(failed_commands, list):
            for item in failed_commands:
                if not isinstance(item, dict):
                    continue
                command = str(item.get("command") or "")
                for token in command.replace("\\", "/").split():
                    clean = token.strip().strip("'\"")
                    if clean in impacted_files and clean not in failed_paths:
                        failed_paths.append(clean)
        if not failed_paths:
            return {}

        changed_files = [
            str(item).replace("\\", "/")
            for item in repo_impact.get("changed_files", [])
            if str(item).strip()
        ]
        root_changed_file = changed_files[0] if changed_files else str(repo_impact.get("target_path") or "")
        sensitive_prefixes = ("core/", "runtime/", "tasks/", "planning/", "services/", "tests/")
        requires_confirmation = any(path.startswith(sensitive_prefixes) for path in failed_paths + changed_files)
        risk_level = "low"
        if requires_confirmation:
            risk_level = "high" if any(path.startswith(("core/", "runtime/", "tasks/", "planning/", "services/")) for path in failed_paths + changed_files) else "medium"
        elif len(failed_paths) > 1:
            risk_level = "medium"
        blocked_reason = ""
        if requires_confirmation:
            blocked_reason = "impacted repo source repair requires confirmation"
        elif risk_level != "low":
            blocked_reason = "multi-file repair plan requires controlled per-file apply"
        else:
            blocked_reason = "impacted shared file failed regression; prepare controlled per-file repair"

        return {
            "root_changed_file": root_changed_file,
            "failed_impacted_files": failed_paths,
            "suggested_repairs": [
                {
                    "target_path": path,
                    "reason": "py_compile failed after dependency impact expansion",
                    "allowed_auto_apply": path.startswith("workspace/shared/") and risk_level == "low",
                }
                for path in failed_paths
            ],
            "risk_level": risk_level,
            "requires_confirmation": bool(requires_confirmation),
            "blocked_reason": blocked_reason,
        }

    def _first_nonempty_str(self, *values: Any) -> str:
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _is_path_under_root(self, path: str, root: str) -> bool:
        try:
            absolute_path = os.path.abspath(str(path))
            absolute_root = os.path.abspath(str(root))
            return os.path.commonpath([absolute_path, absolute_root]) == absolute_root
        except Exception:
            return False

    def _persistence_for_path(self, file_path: str) -> RuntimePersistenceService:
        """Return a persistence service whose workspace root covers file_path.

        TaskRuntime can be constructed with a workspace root such as
        ``<tmp>/workspace`` while tests and legacy callers pass task_dir values
        under sibling directories such as ``<tmp>/tasks/<name>``.  The governed
        mutation gateway must receive a workspace root that actually covers the
        mutation target, otherwise legitimate runtime_state.json writes are
        rejected as outside the workspace.

        Keep the default service for normal in-workspace paths.  For explicit
        absolute task/runtime artifact paths outside the default workspace, use
        the target file's parent directory as the narrowest safe governed root.
        """
        if not str(file_path or "").strip():
            return self.persistence

        try:
            target_path = os.path.abspath(str(file_path))
        except Exception:
            return self.persistence

        if self._is_path_under_root(target_path, self.workspace_root):
            return self.persistence

        parent_dir = os.path.dirname(target_path)
        if not parent_dir:
            return self.persistence

        return RuntimePersistenceService(
            workspace_root=parent_dir,
            source="task_runtime",
        )

    def _classify_persistence_domain(self, file_path: str) -> str:
        try:
            target = os.path.abspath(str(file_path))
        except Exception:
            return "unknown"

        basename = os.path.basename(target).lower()
        if basename == "runtime_state.json":
            return "runtime_state"

        normalized = target.replace("\\", "/").lower()
        parts = [part for part in normalized.split("/") if part]
        workspace_root = os.path.abspath(str(self.workspace_root)).replace("\\", "/").lower()

        repo_source_names = {
            "core",
            "services",
            "tests",
            "docs",
            "tools",
            "ui",
            "scripts",
        }
        repo_source_files = {
            "app.py",
            "main.py",
            "readme.md",
            "pyproject.toml",
            "pytest.ini",
            "setup.cfg",
            "setup.py",
            "requirements.txt",
        }
        if basename in repo_source_files:
            return "repo_source"
        try:
            rel_to_cwd = os.path.relpath(target, os.getcwd())
            rel_parts = [part.lower() for part in rel_to_cwd.split(os.sep) if part and part != os.curdir]
            if rel_parts and rel_parts[0] in repo_source_names:
                return "repo_source"
        except Exception:
            pass

        rollback_tokens = {"rollback", "rollbacks", "backup", "backups", "restore", "restores"}
        if any(token in parts or token in basename for token in rollback_tokens):
            return "rollback_artifact"

        evidence_tokens = {"runtime_evidence", "evidence", "audit", "journal", "journals"}
        if any(token in parts or token in basename for token in evidence_tokens):
            return "evidence"

        mutation_tokens = {
            "mutation",
            "mutations",
            "runtime_transaction",
            "runtime_transactions",
            "sandbox",
            "patch",
            "patches",
            "transaction",
            "transactions",
        }
        if any(token in parts or token in basename for token in mutation_tokens):
            return "mutation_artifact"

        generated_roots = {"shared", "generated", "outbox", "outputs", "artifacts"}
        if workspace_root and normalized.startswith(workspace_root + "/"):
            try:
                rel_workspace = os.path.relpath(target, os.path.abspath(str(self.workspace_root)))
                workspace_parts = [
                    part.lower()
                    for part in rel_workspace.split(os.sep)
                    if part and part != os.curdir
                ]
            except Exception:
                workspace_parts = []
            if workspace_parts and workspace_parts[0] in generated_roots:
                return "workspace_generated"

        return "unknown"

    def _is_repo_source_path(self, file_path: str) -> bool:
        return self._classify_persistence_domain(file_path) == "repo_source"

    def _runtime_write_scope(self, file_path: str) -> str:
        domain = self._classify_persistence_domain(file_path)
        if domain in {
            "runtime_state",
            "rollback_artifact",
            "evidence",
            "mutation_artifact",
            "workspace_generated",
        }:
            return "runtime"
        if domain == "repo_source":
            return "repo_source"
        return "blocked"

    def _persistence_policy_for_domain(self, domain: str) -> dict:
        policies = {
            "runtime_state": {
                "allow_legacy_json_fallback": True,
                "allow_runtime_write": True,
                "allow_repo_source_write": False,
            },
            "rollback_artifact": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": True,
                "allow_repo_source_write": False,
            },
            "evidence": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": True,
                "allow_repo_source_write": False,
            },
            "mutation_artifact": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": True,
                "allow_repo_source_write": False,
            },
            "workspace_generated": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": True,
                "allow_repo_source_write": False,
            },
            "repo_source": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": False,
                "allow_repo_source_write": False,
            },
            "unknown": {
                "allow_legacy_json_fallback": False,
                "allow_runtime_write": False,
                "allow_repo_source_write": False,
            },
        }
        normalized = str(domain or "unknown")
        return {"domain": normalized, **dict(policies.get(normalized, policies["unknown"]))}

    def _validate_repo_source_write_metadata(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        has_reason = bool(str(reason or "").strip())
        has_lineage = isinstance(lineage, dict) and bool(lineage)
        has_provenance = isinstance(provenance, dict) and bool(provenance)
        if not (has_reason or has_lineage or has_provenance):
            raise PermissionError("repo source writes require governance metadata")
        return {
            "has_reason": has_reason,
            "has_lineage": has_lineage,
            "has_provenance": has_provenance,
            "reason": str(reason or "").strip(),
        }

    def _is_governed_mutation_write(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> bool:
        reason_text = str(reason or "").strip().lower()
        reason_tokens = {
            "mutation",
            "repair",
            "governed",
            "patch",
            "apply",
            "transaction",
            "runtime_update",
            "source_update",
        }
        if any(token in reason_text for token in reason_tokens):
            return True

        def mapping_matches(value: Any) -> bool:
            if not isinstance(value, dict):
                return False
            for key in ("operation", "mutation_id", "repair_id", "transaction_id"):
                if value.get(key):
                    return True
            source = str(value.get("source") or "").strip().lower()
            return source in {"task_runtime", "governed_mutation"}

        return mapping_matches(lineage) or mapping_matches(provenance)

    def _build_governed_mutation_context(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        domain = self._classify_persistence_domain(file_path)
        scope = self._runtime_write_scope(file_path)
        transaction_context = self._extract_transaction_governance_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_flags = transaction_context.get("lifecycle_flags")
        if not isinstance(lifecycle_flags, dict):
            lifecycle_flags = self._transaction_lifecycle_flags(str(transaction_context.get("gate_state") or "unknown"))
        ownership = transaction_context.get("ownership")
        if not isinstance(ownership, dict):
            ownership = self._extract_runtime_ownership_chain(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        ownership_flags = transaction_context.get("ownership_flags")
        if not isinstance(ownership_flags, dict):
            ownership_flags = self._ownership_chain_flags(ownership)
        ownership_validation = transaction_context.get("ownership_validation")
        if not isinstance(ownership_validation, dict):
            ownership_validation = self._validate_runtime_ownership_for_state(
                str(transaction_context.get("gate_state") or "unknown"),
                ownership,
            )
        execution_review = transaction_context.get("execution_review")
        if not isinstance(execution_review, dict):
            execution_review = self._extract_execution_review_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        execution_review_flags = transaction_context.get("execution_review_flags")
        if not isinstance(execution_review_flags, dict):
            execution_review_flags = self._execution_review_flags(execution_review)
        execution_review_validation = transaction_context.get("execution_review_validation")
        if not isinstance(execution_review_validation, dict):
            execution_review_validation = self._validate_execution_review_for_state(
                str(transaction_context.get("gate_state") or "unknown"),
                execution_review,
            )
        return {
            "path": str(file_path),
            "domain": domain,
            "scope": scope,
            "reason": str(reason or "").strip(),
            "governed_mutation": self._is_governed_mutation_write(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "lineage_keys": sorted(str(key) for key in lineage.keys()) if isinstance(lineage, dict) else [],
            "provenance_keys": sorted(str(key) for key in provenance.keys()) if isinstance(provenance, dict) else [],
            "has_transaction_context": self._has_transaction_governance_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "transaction_id": transaction_context.get("transaction_id"),
            "repair_id": transaction_context.get("repair_id"),
            "mutation_id": transaction_context.get("mutation_id"),
            "gate_state": transaction_context.get("gate_state"),
            "gate_flags": transaction_context.get("gate_flags"),
            "lifecycle_stage": transaction_context.get("lifecycle_stage"),
            "lifecycle_flags": lifecycle_flags,
            "can_commit": bool(lifecycle_flags.get("can_commit")),
            "can_rollback": bool(lifecycle_flags.get("can_rollback")),
            "ownership": ownership,
            "ownership_flags": ownership_flags,
            "ownership_validation": ownership_validation,
            "execution_review": execution_review,
            "execution_review_flags": execution_review_flags,
            "execution_review_validation": execution_review_validation,
            "transaction_record_preview": self._build_runtime_transaction_record(
                file_path,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "is_terminal": bool(transaction_context.get("gate_flags", {}).get("is_terminal"))
            if isinstance(transaction_context.get("gate_flags"), dict)
            else False,
        }

    def _extract_transaction_governance_context(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        def first_value(*keys: str) -> Any:
            for source in (lineage, provenance):
                if not isinstance(source, dict):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value is not None and str(value).strip():
                        return value
            return None

        def bool_value(*keys: str) -> bool:
            value = first_value(*keys)
            if isinstance(value, bool):
                return value
            if isinstance(value, dict):
                return bool(value)
            text = str(value or "").strip().lower()
            return text in {"1", "true", "yes", "required", "enabled", "available", "ready"}

        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_stage = self._transaction_lifecycle_stage(gate_state)
        lifecycle_flags = self._transaction_lifecycle_flags(gate_state)
        ownership = self._extract_runtime_ownership_chain(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        ownership_flags = self._ownership_chain_flags(ownership)
        ownership_validation = self._validate_runtime_ownership_for_state(gate_state, ownership)
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        execution_review_flags = self._execution_review_flags(execution_review)
        execution_review_validation = self._validate_execution_review_for_state(gate_state, execution_review)
        return {
            "reason": str(reason).strip() if reason is not None and str(reason).strip() else None,
            "operation": str(first_value("operation") or "").strip() or None,
            "source": str(first_value("source") or "").strip() or None,
            "mutation_id": str(first_value("mutation_id", "mutationId") or "").strip() or None,
            "repair_id": str(first_value("repair_id", "repairId") or "").strip() or None,
            "transaction_id": str(first_value("transaction_id", "transactionId") or "").strip() or None,
            "approval_id": str(first_value("approval_id", "approvalId") or "").strip() or None,
            "previous_gate_state": str(first_value("previous_gate_state", "previous_state") or "").strip() or None,
            "verification_required": bool_value("verification_required", "requires_verification", "verification"),
            "commit_required": bool_value("commit_required", "requires_commit", "commit"),
            "rollback_available": bool_value("rollback_available", "can_rollback", "rollback"),
            "gate_state": gate_state,
            "gate_flags": self._transaction_gate_flags(gate_state),
            "lifecycle_stage": lifecycle_stage,
            "lifecycle_flags": lifecycle_flags,
            "ownership": ownership,
            "ownership_flags": ownership_flags,
            "ownership_validation": ownership_validation,
            "execution_review": execution_review,
            "execution_review_flags": execution_review_flags,
            "execution_review_validation": execution_review_validation,
        }

    def _normalize_transaction_gate_state(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> str:
        def first_state() -> str:
            for source in (lineage, provenance):
                if not isinstance(source, dict):
                    continue
                for key in (
                    "gate_state",
                    "transaction_state",
                    "mutation_state",
                    "approval_state",
                    "review_state",
                    "verification_state",
                    "commit_state",
                    "status",
                    "state",
                ):
                    value = source.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip().lower()
            return str(reason or "").strip().lower()

        raw = first_state()
        if not raw:
            return "unknown"
        aliases = {
            "reviewed": "reviewed",
            "review_passed": "reviewed",
            "reviewed_ok": "reviewed",
            "verified": "verified",
            "verification_passed": "verified",
            "tests_passed": "verified",
            "approved": "approved",
            "approval_granted": "approved",
            "commit_ready": "commit_ready",
            "ready_to_commit": "commit_ready",
            "can_commit": "commit_ready",
            "committed": "committed",
            "applied": "committed",
            "merged": "committed",
            "rolled_back": "rolled_back",
            "rollback_complete": "rolled_back",
            "reverted": "rolled_back",
            "rejected": "rejected",
            "denied": "rejected",
            "blocked": "rejected",
            "pending": "pending",
            "created": "pending",
            "staged": "pending",
        }
        if raw in aliases:
            return aliases[raw]
        for token, normalized in aliases.items():
            if token in raw:
                return normalized
        return "unknown"

    def _transaction_gate_flags(self, gate_state: str) -> dict:
        state = str(gate_state or "unknown").strip().lower()
        return {
            "is_pending": state == "pending",
            "is_reviewed": state == "reviewed",
            "is_verified": state == "verified",
            "is_approved": state == "approved",
            "is_commit_ready": state == "commit_ready",
            "is_committed": state == "committed",
            "is_rolled_back": state == "rolled_back",
            "is_rejected": state == "rejected",
            "is_terminal": state in {"committed", "rolled_back", "rejected"},
        }

    def _transaction_lifecycle_stage(self, gate_state: str) -> str:
        state = str(gate_state or "unknown").strip().lower()
        stages = {
            "pending": "creation",
            "reviewed": "review",
            "verified": "verification",
            "approved": "approval",
            "commit_ready": "commit",
            "committed": "commit",
            "rolled_back": "rollback",
            "rejected": "rejection",
            "unknown": "unknown",
        }
        return stages.get(state, "unknown")

    def _transaction_lifecycle_transition_allowed(
        self,
        previous_state: str,
        next_state: str,
    ) -> bool:
        previous = str(previous_state or "unknown").strip().lower()
        next_value = str(next_state or "unknown").strip().lower()
        allowed = {
            "pending": {"reviewed", "verified", "approved", "commit_ready", "rejected"},
            "reviewed": {"verified", "approved", "commit_ready", "rejected"},
            "verified": {"approved", "commit_ready", "rejected"},
            "approved": {"commit_ready", "committed", "rejected"},
            "commit_ready": {"committed", "rolled_back"},
            "committed": {"committed"},
            "rolled_back": {"rolled_back"},
            "rejected": {"rejected"},
            "unknown": set(),
        }
        return next_value in allowed.get(previous, set())

    def _transaction_lifecycle_flags(self, gate_state: str) -> dict:
        stage = self._transaction_lifecycle_stage(gate_state)
        state = str(gate_state or "unknown").strip().lower()
        return {
            "is_creation_stage": stage == "creation",
            "is_review_stage": stage == "review",
            "is_verification_stage": stage == "verification",
            "is_approval_stage": stage == "approval",
            "is_commit_stage": stage == "commit",
            "is_rollback_stage": stage == "rollback",
            "is_rejection_stage": stage == "rejection",
            "is_terminal_stage": state in {"committed", "rolled_back", "rejected"},
            "can_commit": state in {"approved", "commit_ready"},
            "can_rollback": state in {"pending", "reviewed", "verified", "approved", "commit_ready", "committed"},
        }

    def _build_transaction_lifecycle_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        ownership = self._extract_runtime_ownership_chain(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return {
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "gate_state": gate_state,
            "lifecycle_stage": self._transaction_lifecycle_stage(gate_state),
            "lifecycle_flags": self._transaction_lifecycle_flags(gate_state),
            "ownership": ownership,
            "ownership_flags": self._ownership_chain_flags(ownership),
            "ownership_validation": self._validate_runtime_ownership_for_state(gate_state, ownership),
            "execution_review": execution_review,
            "execution_review_flags": self._execution_review_flags(execution_review),
            "execution_review_validation": self._validate_execution_review_for_state(gate_state, execution_review),
        }

    def _extract_execution_review_context(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        def first_value(*keys: str) -> Any:
            for source in (lineage, provenance):
                if not isinstance(source, dict):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value is not None and str(value).strip():
                        return value
            return None

        def bool_value(*keys: str) -> bool:
            value = first_value(*keys)
            if isinstance(value, bool):
                return value
            if isinstance(value, dict):
                return bool(value)
            text = str(value or "").strip().lower()
            return text in {"1", "true", "yes", "required", "enabled", "available", "ready", "passed", "done"}

        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_flags = self._transaction_lifecycle_flags(gate_state)
        executed = bool_value("executed", "execution_done", "has_executed")
        observed = bool_value("observed", "observation_done", "has_observation")
        verified = bool_value("verified", "verification_done", "tests_passed")
        reviewed = bool_value("reviewed", "review_done", "review_passed")
        approved = bool_value("approved", "approval_done", "approval_granted")
        commit_ready = bool_value("commit_ready", "ready_to_commit", "can_commit")
        rollback_ready = bool_value("rollback_ready", "rollback_available", "can_rollback")

        if gate_state == "verified":
            verified = True
        if gate_state == "reviewed":
            reviewed = True
        if gate_state == "approved":
            approved = True
        if gate_state == "commit_ready":
            commit_ready = True
        if gate_state == "committed":
            executed = True
            commit_ready = True
        if lifecycle_flags.get("can_rollback"):
            rollback_ready = True

        return {
            "executed": bool(executed),
            "observed": bool(observed),
            "verified": bool(verified),
            "reviewed": bool(reviewed),
            "approved": bool(approved),
            "commit_ready": bool(commit_ready),
            "rollback_ready": bool(rollback_ready),
            "review_id": str(first_value("review_id", "reviewId") or "").strip() or None,
            "execution_id": str(first_value("execution_id", "executionId") or "").strip() or None,
            "verification_id": str(first_value("verification_id", "verificationId") or "").strip() or None,
            "observation_id": str(first_value("observation_id", "observationId") or "").strip() or None,
        }

    def _execution_review_flags(self, review_context: dict) -> dict:
        source = review_context if isinstance(review_context, dict) else {}
        flags = {
            "has_execution": bool(source.get("executed")),
            "has_observation": bool(source.get("observed")),
            "has_verification": bool(source.get("verified")),
            "has_review": bool(source.get("reviewed")),
            "has_approval": bool(source.get("approved")),
            "is_commit_ready": bool(source.get("commit_ready")),
            "is_rollback_ready": bool(source.get("rollback_ready")),
        }
        flags["has_any_review_signal"] = any(flags.values())
        return flags

    def _build_execution_review_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return {
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "execution_review": execution_review,
            "execution_review_flags": self._execution_review_flags(execution_review),
        }

    def _execution_review_required_for_state(self, gate_state: str) -> List[str]:
        state = str(gate_state or "unknown").strip().lower()
        requirements = {
            "pending": [],
            "reviewed": ["reviewed"],
            "verified": ["verified"],
            "approved": ["reviewed", "approved"],
            "commit_ready": ["verified", "commit_ready"],
            "committed": ["executed", "commit_ready"],
            "rolled_back": ["rollback_ready"],
            "rejected": [],
            "unknown": [],
        }
        return list(requirements.get(state, []))

    def _validate_execution_review_for_state(
        self,
        gate_state: str,
        review_context: dict,
    ) -> dict:
        required = self._execution_review_required_for_state(gate_state)
        source = review_context if isinstance(review_context, dict) else {}
        missing = [key for key in required if not bool(source.get(key))]
        return {
            "required": required,
            "missing": missing,
            "valid": not missing,
        }

    def _extract_runtime_ownership_chain(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        del reason

        def first_text(keys: List[str]) -> Optional[str]:
            for source in (lineage, provenance):
                if not isinstance(source, dict):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip()
            return None

        return {
            "initiator": first_text(["initiator", "initiated_by", "actor", "requested_by", "source_actor"]),
            "reviewer": first_text(["reviewer", "reviewed_by", "review_owner"]),
            "verifier": first_text(["verifier", "verified_by", "verification_owner", "test_owner"]),
            "approver": first_text(["approver", "approved_by", "approval_owner"]),
            "committer": first_text(["committer", "committed_by", "commit_owner", "applied_by"]),
            "rollback_owner": first_text(["rollback_owner", "rollback_by", "reverted_by", "rollback_actor"]),
            "owner_source": first_text(["owner_source", "ownership_source", "source"]),
        }

    def _ownership_chain_flags(self, ownership: dict) -> dict:
        source = ownership if isinstance(ownership, dict) else {}
        flags = {
            "has_initiator": bool(str(source.get("initiator") or "").strip()),
            "has_reviewer": bool(str(source.get("reviewer") or "").strip()),
            "has_verifier": bool(str(source.get("verifier") or "").strip()),
            "has_approver": bool(str(source.get("approver") or "").strip()),
            "has_committer": bool(str(source.get("committer") or "").strip()),
            "has_rollback_owner": bool(str(source.get("rollback_owner") or "").strip()),
        }
        flags["has_any_owner"] = any(flags.values())
        return flags

    def _build_runtime_ownership_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        ownership = self._extract_runtime_ownership_chain(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return {
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "ownership": ownership,
            "ownership_flags": self._ownership_chain_flags(ownership),
            "execution_review": execution_review,
            "execution_review_flags": self._execution_review_flags(execution_review),
            "execution_review_validation": self._validate_execution_review_for_state(
                gate_state,
                execution_review,
            ),
        }

    def _ownership_required_for_gate_state(self, gate_state: str) -> List[str]:
        state = str(gate_state or "unknown").strip().lower()
        requirements = {
            "pending": ["initiator"],
            "reviewed": ["initiator", "reviewer"],
            "verified": ["initiator", "verifier"],
            "approved": ["initiator", "approver"],
            "commit_ready": ["initiator", "verifier"],
            "committed": ["initiator", "committer"],
            "rolled_back": ["initiator", "rollback_owner"],
            "rejected": ["initiator"],
            "unknown": [],
        }
        return list(requirements.get(state, []))

    def _validate_runtime_ownership_for_state(
        self,
        gate_state: str,
        ownership: dict,
    ) -> dict:
        required = self._ownership_required_for_gate_state(gate_state)
        source = ownership if isinstance(ownership, dict) else {}
        missing = [role for role in required if not str(source.get(role) or "").strip()]
        return {
            "required": required,
            "missing": missing,
            "valid": not missing,
        }

    def _extract_previous_transaction_gate_state(
        self,
        *,
        lineage: Any = None,
        provenance: Any = None,
    ) -> Optional[str]:
        for source in (lineage, provenance):
            if not isinstance(source, dict):
                continue
            for key in ("previous_gate_state", "previous_state"):
                value = source.get(key)
                if value is not None and str(value).strip():
                    return self._normalize_transaction_gate_state(
                        provenance={"gate_state": str(value).strip()},
                    )
        return None

    def _has_transaction_governance_context(
        self,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> bool:
        context = self._extract_transaction_governance_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        if any(context.get(key) for key in ("mutation_id", "repair_id", "transaction_id", "operation")):
            return True
        source = str(context.get("source") or "").strip().lower()
        if any(token in source for token in ("governed_mutation", "task_runtime", "repair", "transaction")):
            return True
        return False

    def _build_transaction_governance_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_flags = self._transaction_lifecycle_flags(gate_state)
        ownership = self._extract_runtime_ownership_chain(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return {
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "governed_mutation": self._is_governed_mutation_write(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "has_transaction_context": self._has_transaction_governance_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "transaction_context": self._extract_transaction_governance_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "gate_state": gate_state,
            "gate_flags": self._transaction_gate_flags(gate_state),
            "lifecycle_stage": self._transaction_lifecycle_stage(gate_state),
            "lifecycle_flags": lifecycle_flags,
            "can_commit": lifecycle_flags["can_commit"],
            "can_rollback": lifecycle_flags["can_rollback"],
            "ownership": ownership,
            "ownership_flags": self._ownership_chain_flags(ownership),
            "ownership_validation": self._validate_runtime_ownership_for_state(gate_state, ownership),
            "execution_review": execution_review,
            "execution_review_flags": self._execution_review_flags(execution_review),
            "execution_review_validation": self._validate_execution_review_for_state(gate_state, execution_review),
            "transaction_record_preview": self._build_runtime_transaction_record(
                file_path,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "is_terminal": self._transaction_gate_flags(gate_state)["is_terminal"],
        }

    def _build_transaction_gate_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        gate_state = self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_flags = self._transaction_lifecycle_flags(gate_state)
        ownership = self._extract_runtime_ownership_chain(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        execution_review = self._extract_execution_review_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return {
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "gate_state": gate_state,
            "gate_flags": self._transaction_gate_flags(gate_state),
            "lifecycle_stage": self._transaction_lifecycle_stage(gate_state),
            "lifecycle_flags": lifecycle_flags,
            "can_commit": lifecycle_flags["can_commit"],
            "can_rollback": lifecycle_flags["can_rollback"],
            "ownership": ownership,
            "ownership_flags": self._ownership_chain_flags(ownership),
            "ownership_validation": self._validate_runtime_ownership_for_state(gate_state, ownership),
            "execution_review": execution_review,
            "execution_review_flags": self._execution_review_flags(execution_review),
            "execution_review_validation": self._validate_execution_review_for_state(gate_state, execution_review),
        }

    def _runtime_write_requires_governance(self, file_path: str) -> bool:
        return self._runtime_write_scope(file_path) == "repo_source"

    def _runtime_write_governance_summary(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        domain = self._classify_persistence_domain(file_path)
        scope = self._runtime_write_scope(file_path)
        transaction_context = self._extract_transaction_governance_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        lifecycle_flags = transaction_context.get("lifecycle_flags")
        if not isinstance(lifecycle_flags, dict):
            lifecycle_flags = self._transaction_lifecycle_flags(str(transaction_context.get("gate_state") or "unknown"))
        ownership = transaction_context.get("ownership")
        if not isinstance(ownership, dict):
            ownership = self._extract_runtime_ownership_chain(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        ownership_flags = transaction_context.get("ownership_flags")
        if not isinstance(ownership_flags, dict):
            ownership_flags = self._ownership_chain_flags(ownership)
        ownership_validation = transaction_context.get("ownership_validation")
        if not isinstance(ownership_validation, dict):
            ownership_validation = self._validate_runtime_ownership_for_state(
                str(transaction_context.get("gate_state") or "unknown"),
                ownership,
            )
        execution_review = transaction_context.get("execution_review")
        if not isinstance(execution_review, dict):
            execution_review = self._extract_execution_review_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        execution_review_flags = transaction_context.get("execution_review_flags")
        if not isinstance(execution_review_flags, dict):
            execution_review_flags = self._execution_review_flags(execution_review)
        execution_review_validation = transaction_context.get("execution_review_validation")
        if not isinstance(execution_review_validation, dict):
            execution_review_validation = self._validate_execution_review_for_state(
                str(transaction_context.get("gate_state") or "unknown"),
                execution_review,
            )
        return {
            "path": str(file_path),
            "domain": domain,
            "scope": scope,
            "requires_governance": self._runtime_write_requires_governance(file_path),
            "governed_mutation": self._is_governed_mutation_write(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "has_transaction_context": self._has_transaction_governance_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "transaction_id": transaction_context.get("transaction_id"),
            "repair_id": transaction_context.get("repair_id"),
            "mutation_id": transaction_context.get("mutation_id"),
            "gate_state": transaction_context.get("gate_state"),
            "gate_flags": transaction_context.get("gate_flags"),
            "lifecycle_stage": transaction_context.get("lifecycle_stage"),
            "lifecycle_flags": lifecycle_flags,
            "can_commit": bool(lifecycle_flags.get("can_commit")),
            "can_rollback": bool(lifecycle_flags.get("can_rollback")),
            "ownership": ownership,
            "ownership_flags": ownership_flags,
            "ownership_validation": ownership_validation,
            "execution_review": execution_review,
            "execution_review_flags": execution_review_flags,
            "execution_review_validation": execution_review_validation,
            "transaction_record_preview": self._build_runtime_transaction_record(
                file_path,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "is_terminal": bool(transaction_context.get("gate_flags", {}).get("is_terminal"))
            if isinstance(transaction_context.get("gate_flags"), dict)
            else False,
        }

    def _runtime_transaction_journal_path(self, transaction_id: str) -> str:
        raw = str(transaction_id or "").strip() or "unknown_transaction"
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)
        safe_name = safe_name.strip("_") or "unknown_transaction"
        return os.path.join(self.workspace_root, "runtime_transactions", f"{safe_name}.json")

    def _build_runtime_transaction_record(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        transaction_context = self._extract_transaction_governance_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        gate_state = str(transaction_context.get("gate_state") or "unknown")
        lifecycle_flags = transaction_context.get("lifecycle_flags")
        if not isinstance(lifecycle_flags, dict):
            lifecycle_flags = self._transaction_lifecycle_flags(gate_state)
        ownership = transaction_context.get("ownership")
        if not isinstance(ownership, dict):
            ownership = self._extract_runtime_ownership_chain(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        execution_review = transaction_context.get("execution_review")
        if not isinstance(execution_review, dict):
            execution_review = self._extract_execution_review_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        return {
            "record_type": "runtime_transaction",
            "path": str(file_path),
            "domain": self._classify_persistence_domain(file_path),
            "scope": self._runtime_write_scope(file_path),
            "transaction_context": transaction_context,
            "gate_state": gate_state,
            "lifecycle_stage": transaction_context.get("lifecycle_stage")
            or self._transaction_lifecycle_stage(gate_state),
            "lifecycle_flags": lifecycle_flags,
            "ownership": ownership,
            "ownership_validation": transaction_context.get("ownership_validation")
            if isinstance(transaction_context.get("ownership_validation"), dict)
            else self._validate_runtime_ownership_for_state(gate_state, ownership),
            "execution_review": execution_review,
            "execution_review_validation": transaction_context.get("execution_review_validation")
            if isinstance(transaction_context.get("execution_review_validation"), dict)
            else self._validate_execution_review_for_state(gate_state, execution_review),
            "governed_mutation": self._is_governed_mutation_write(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ),
            "can_commit": bool(lifecycle_flags.get("can_commit")),
            "can_rollback": bool(lifecycle_flags.get("can_rollback")),
            "created_at": self._now(),
        }

    def _write_runtime_transaction_record(self, record: dict) -> str:
        source = record if isinstance(record, dict) else {}
        transaction_context = source.get("transaction_context")
        if not isinstance(transaction_context, dict):
            transaction_context = {}
        transaction_id = str(transaction_context.get("transaction_id") or "").strip()
        journal_path = self._runtime_transaction_journal_path(transaction_id)
        self._write_json(journal_path, source)
        return journal_path

    def _read_runtime_transaction_record(self, transaction_id: str, default: Any = None) -> dict:
        fallback = copy.deepcopy(default) if default is not None else {}
        record = self._read_json(self._runtime_transaction_journal_path(transaction_id), fallback)
        return record if isinstance(record, dict) else fallback

    def _runtime_continuation_action_from_record(self, record: dict) -> str:
        if not isinstance(record, dict) or not record:
            return "unknown"
        gate_state = str(record.get("gate_state") or "unknown").strip().lower()
        lifecycle_stage = str(record.get("lifecycle_stage") or "unknown").strip().lower()
        can_rollback = bool(record.get("can_rollback"))
        if gate_state == "rejected":
            return "blocked"
        if gate_state in {"rolled_back", "committed"}:
            return "stop_terminal"
        if can_rollback and lifecycle_stage == "rollback":
            return "continue_rollback"
        if gate_state == "pending":
            return "continue_review"
        if gate_state == "reviewed":
            return "continue_verification"
        if gate_state == "verified":
            return "continue_approval"
        if gate_state in {"approved", "commit_ready"}:
            return "continue_commit"
        return "unknown"

    def _build_runtime_continuation_plan_from_record(self, record: dict) -> dict:
        source = record if isinstance(record, dict) else {}
        record_found = bool(source)
        transaction_context = source.get("transaction_context")
        if not isinstance(transaction_context, dict):
            transaction_context = {}
        action = self._runtime_continuation_action_from_record(source)
        gate_state = str(source.get("gate_state") or "unknown").strip().lower()
        lifecycle_stage = str(source.get("lifecycle_stage") or "unknown").strip().lower()
        return {
            "record_found": record_found,
            "transaction_id": str(transaction_context.get("transaction_id") or "").strip() or "unknown_transaction",
            "path": source.get("path"),
            "gate_state": gate_state,
            "lifecycle_stage": lifecycle_stage,
            "can_commit": bool(source.get("can_commit")) if record_found else False,
            "can_rollback": bool(source.get("can_rollback")) if record_found else False,
            "continuation_action": action,
            "requires_review": action == "continue_review",
            "requires_verification": action == "continue_verification",
            "requires_approval": action == "continue_approval",
            "requires_commit": action == "continue_commit",
            "requires_rollback": action == "continue_rollback",
            "terminal": action == "stop_terminal",
            "blocked": action == "blocked",
        }

    def _runtime_continuation_plan(self, transaction_id: str) -> dict:
        record = self._read_runtime_transaction_record(transaction_id, default={})
        plan = self._build_runtime_continuation_plan_from_record(record)
        if not plan.get("record_found"):
            plan["transaction_id"] = str(transaction_id or "unknown_transaction")
            plan["continuation_action"] = "unknown"
        return plan

    def _runtime_replay_action_from_continuation_action(self, action: str) -> str:
        value = str(action or "unknown").strip().lower()
        actions = {
            "continue_review": "review",
            "continue_verification": "verify",
            "continue_approval": "approve",
            "continue_commit": "commit",
            "continue_rollback": "rollback",
            "stop_terminal": "stop",
            "blocked": "blocked",
        }
        return actions.get(value, "unknown")

    def _runtime_replay_required_evidence(self, replay_action: str) -> List[str]:
        action = str(replay_action or "unknown").strip().lower()
        required = {
            "review": ["transaction_record", "mutation_context"],
            "verify": ["transaction_record", "mutation_context", "verification_target"],
            "approve": ["transaction_record", "mutation_context", "review_result"],
            "commit": ["transaction_record", "mutation_context", "verification_result", "commit_target"],
            "rollback": ["transaction_record", "mutation_context", "rollback_target"],
            "stop": ["transaction_record"],
            "blocked": ["transaction_record", "block_reason"],
            "unknown": ["transaction_record"],
        }
        return list(required.get(action, required["unknown"]))

    def _build_runtime_replay_request_from_plan(self, plan: dict) -> dict:
        source = plan if isinstance(plan, dict) else {}
        continuation_action = str(source.get("continuation_action") or "unknown")
        replay_action = self._runtime_replay_action_from_continuation_action(continuation_action)
        terminal = bool(source.get("terminal"))
        blocked = bool(source.get("blocked"))
        can_execute = not terminal and not blocked and replay_action not in {"stop", "blocked", "unknown"}
        if terminal:
            reason = "terminal transaction"
        elif blocked:
            reason = "blocked transaction"
        elif replay_action == "unknown":
            reason = "unknown replay action"
        else:
            reason = "replay action available"
        return {
            "request_type": "runtime_replay_request",
            "transaction_id": str(source.get("transaction_id") or "unknown_transaction"),
            "path": source.get("path"),
            "continuation_action": continuation_action,
            "replay_action": replay_action,
            "required_evidence": self._runtime_replay_required_evidence(replay_action),
            "terminal": terminal,
            "blocked": blocked,
            "can_execute": bool(can_execute),
            "reason": reason,
        }

    def _runtime_replay_request(self, transaction_id: str) -> dict:
        plan = self._runtime_continuation_plan(transaction_id)
        request = self._build_runtime_replay_request_from_plan(plan)
        if not plan.get("record_found"):
            request["transaction_id"] = str(transaction_id or "unknown_transaction")
            request["replay_action"] = "unknown"
            request["required_evidence"] = self._runtime_replay_required_evidence("unknown")
            request["can_execute"] = False
            request["reason"] = "unknown replay action"
        return request

    def _runtime_replay_recovery_summary(self, transaction_id: str) -> dict:
        plan = self._runtime_continuation_plan(transaction_id)
        request = self._build_runtime_replay_request_from_plan(plan)
        if not plan.get("record_found"):
            request["transaction_id"] = str(transaction_id or "unknown_transaction")
            request["replay_action"] = "unknown"
            request["required_evidence"] = self._runtime_replay_required_evidence("unknown")
            request["can_execute"] = False
        return {
            "transaction_id": request.get("transaction_id") or str(transaction_id or "unknown_transaction"),
            "record_found": bool(plan.get("record_found")),
            "continuation_action": request.get("continuation_action") or "unknown",
            "replay_action": request.get("replay_action") or "unknown",
            "can_execute": bool(request.get("can_execute")),
            "terminal": bool(request.get("terminal")),
            "blocked": bool(request.get("blocked")),
            "required_evidence": list(request.get("required_evidence") or []),
        }

    def _normalize_replay_available_evidence(self, available_evidence: Any) -> List[str]:
        if isinstance(available_evidence, dict):
            return sorted(
                str(key)
                for key, value in available_evidence.items()
                if value and str(key).strip()
            )
        if isinstance(available_evidence, (list, tuple, set)):
            return sorted(str(item) for item in available_evidence if str(item).strip())
        if available_evidence is None:
            return []
        text = str(available_evidence).strip()
        return [text] if text else []

    def _runtime_replay_execution_risk_level(self, action: str) -> str:
        normalized = str(action or "unknown").strip().lower()
        if normalized in {"commit", "rollback"}:
            return "high"
        if normalized in {"verify", "approve"}:
            return "medium"
        if normalized == "review":
            return "low"
        return "blocked"

    def _runtime_recovery_is_terminal_or_blocked(self, recovery: dict) -> bool:
        source = recovery if isinstance(recovery, dict) else {}
        status = str(source.get("status") or source.get("recovery_status") or "").strip().lower()
        if status in {"finished", "failed", "cancelled", "blocked", "terminal"}:
            return True
        return bool(source.get("terminal") or source.get("blocked"))

    def _runtime_replay_blocked_reason(
        self,
        *,
        record_found: bool,
        terminal_recovery: bool,
        replay_action: str,
        missing_evidence: List[str],
    ) -> str:
        if not record_found:
            return "missing transaction record"
        if terminal_recovery:
            return "terminal recovery state"
        if str(replay_action or "unknown") == "unknown":
            return "unknown replay action"
        if missing_evidence:
            return "missing required evidence: " + ", ".join(missing_evidence)
        return ""

    def _build_replay_execution_preflight(
        self,
        replay_request: dict,
        *,
        available_evidence: Any = None,
        recovery_summary: Any = None,
        replay_id: Any = None,
    ) -> dict:
        request = replay_request if isinstance(replay_request, dict) else {}
        recovery = recovery_summary if isinstance(recovery_summary, dict) else {}
        transaction_id = str(
            request.get("transaction_id")
            or recovery.get("transaction_id")
            or "unknown_transaction"
        )
        replay_action = str(request.get("replay_action") or "unknown")
        required_evidence = list(request.get("required_evidence") or self._runtime_replay_required_evidence(replay_action))
        normalized_available = self._normalize_replay_available_evidence(available_evidence)
        missing_evidence = [item for item in required_evidence if item not in set(normalized_available)]
        record_found = bool(recovery.get("record_found"))
        terminal_recovery = self._runtime_recovery_is_terminal_or_blocked(recovery)
        action_mapped = replay_action not in {"", "unknown"}
        blocked_reason = self._runtime_replay_blocked_reason(
            record_found=record_found,
            terminal_recovery=terminal_recovery,
            replay_action=replay_action,
            missing_evidence=missing_evidence,
        )
        is_executable = bool(action_mapped and record_found and not missing_evidence and not terminal_recovery)
        status = "executable" if is_executable else "blocked"
        resolved_replay_id = str(replay_id or f"replay_{transaction_id}_{replay_action}").strip()
        debug_context = {
            "source": "runtime_replay_execution_bridge_v2",
            "transaction_id": transaction_id,
            "replay_id": resolved_replay_id,
            "action": replay_action,
            "decision_type": "executable" if is_executable else "blocked",
            "missing_evidence": missing_evidence,
            "required_evidence": required_evidence,
            "available_evidence": normalized_available,
            "blocked_reason": blocked_reason,
        }
        return {
            "replay_id": resolved_replay_id,
            "transaction_id": transaction_id,
            "action": replay_action,
            "status": status,
            "required_evidence": required_evidence,
            "available_evidence": normalized_available,
            "missing_evidence": missing_evidence,
            "is_executable": is_executable,
            "blocked_reason": blocked_reason,
            "risk_level": self._runtime_replay_execution_risk_level(replay_action),
            "debug_context": debug_context,
        }

    def _runtime_replay_execution_preflight(
        self,
        transaction_id: str,
        *,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        replay_request = self._runtime_replay_request(transaction_id)
        recovery_summary = self._runtime_replay_recovery_summary(transaction_id)
        return self._build_replay_execution_preflight(
            replay_request,
            available_evidence=available_evidence,
            recovery_summary=recovery_summary,
            replay_id=replay_id,
        )

    def build_replay_execution_decision(
        self,
        preflight: Optional[dict] = None,
        *,
        transaction_id: Optional[str] = None,
        replay_request: Optional[dict] = None,
        recovery_summary: Optional[dict] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        if not isinstance(preflight, dict):
            if transaction_id is not None and replay_request is None:
                preflight = self._runtime_replay_execution_preflight(
                    transaction_id,
                    available_evidence=available_evidence,
                    replay_id=replay_id,
                )
            else:
                preflight = self._build_replay_execution_preflight(
                    replay_request or {},
                    available_evidence=available_evidence,
                    recovery_summary=recovery_summary or {},
                    replay_id=replay_id,
                )
        action = str(preflight.get("action") or "unknown")
        missing_evidence = list(preflight.get("missing_evidence") or [])
        debug_context = copy.deepcopy(preflight.get("debug_context") if isinstance(preflight.get("debug_context"), dict) else {})
        blocked_reason = str(preflight.get("blocked_reason") or "")
        terminal_block = blocked_reason == "terminal recovery state"
        if bool(preflight.get("is_executable")):
            decision_type = "executable"
        elif blocked_reason == "missing transaction record":
            decision_type = "blocked_missing_transaction"
        elif action == "unknown":
            decision_type = "blocked_unknown_action"
        elif terminal_block:
            decision_type = "blocked_terminal_recovery"
        elif missing_evidence:
            decision_type = "blocked_missing_evidence"
        else:
            decision_type = "blocked_unknown_action"
        debug_context["decision_type"] = decision_type
        return {
            "decision_type": decision_type,
            "replay_id": preflight.get("replay_id"),
            "transaction_id": preflight.get("transaction_id"),
            "action": action,
            "status": "executable" if decision_type == "executable" else "blocked",
            "is_executable": decision_type == "executable",
            "required_evidence": list(preflight.get("required_evidence") or []),
            "available_evidence": list(preflight.get("available_evidence") or []),
            "missing_evidence": missing_evidence,
            "blocked_reason": "" if decision_type == "executable" else blocked_reason,
            "risk_level": preflight.get("risk_level") or self._runtime_replay_execution_risk_level(action),
            "debug_context": debug_context,
        }

    def build_replay_commit_request_preview(
        self,
        decision: Optional[dict] = None,
        *,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
    ) -> dict:
        source = decision if isinstance(decision, dict) else self.build_replay_execution_decision(
            transaction_id=transaction_id,
            available_evidence=available_evidence,
        )
        return {
            "request_type": "runtime_replay_commit_request_preview",
            "transaction_id": source.get("transaction_id"),
            "replay_id": source.get("replay_id"),
            "action": source.get("action"),
            "decision_type": source.get("decision_type"),
            "preview_only": True,
            "mutation_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "executor_dispatch_allowed": False,
            "required_evidence": list(source.get("required_evidence") or []),
            "missing_evidence": list(source.get("missing_evidence") or []),
            "blocked_reason": source.get("blocked_reason") or "",
        }

    def build_governed_replay_execution_gateway_preview(
        self,
        decision: Optional[dict] = None,
        *,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        replay_decision = decision if isinstance(decision, dict) else self.build_replay_execution_decision(
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        decision_type = str(replay_decision.get("decision_type") or "blocked_unknown_action")
        executable = decision_type == "executable"
        gateway_status = "preview_ready" if executable else "blocked"
        policy_gate_status = "review_required" if executable else "blocked"
        action = str(replay_decision.get("action") or "unknown")
        resolved_transaction_id = replay_decision.get("transaction_id") or transaction_id or "unknown_transaction"
        resolved_replay_id = replay_decision.get("replay_id") or replay_id or f"replay_{resolved_transaction_id}_{action}"
        required_evidence = list(replay_decision.get("required_evidence") or [])
        available = list(replay_decision.get("available_evidence") or [])
        missing = list(replay_decision.get("missing_evidence") or [])
        blocked_reason = str(replay_decision.get("blocked_reason") or "")
        execution_contract = {
            "preview_only": True,
            "execution_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "mutation_allowed": False,
            "command_execution_allowed": False,
            "requires_human_approval": True,
            "risk_level": replay_decision.get("risk_level") or self._runtime_replay_execution_risk_level(action),
            "action": action,
            "transaction_id": resolved_transaction_id,
            "replay_id": resolved_replay_id,
        }
        evidence_contract = {
            "required_evidence": required_evidence,
            "available_evidence": available,
            "missing_evidence": missing,
            "evidence_complete": not missing,
            "decision_type": decision_type,
        }
        commit_request_preview = self.build_replay_commit_request_preview(replay_decision)
        debug_context = {
            "source": "governed_replay_execution_gateway_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "decision_type": decision_type,
            "gateway_status": gateway_status,
            "policy_gate_status": policy_gate_status,
            "blocked_reason": blocked_reason,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
        }
        return {
            "source": "governed_replay_execution_gateway_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "decision_type": decision_type,
            "gateway_status": gateway_status,
            "policy_gate_status": policy_gate_status,
            "execution_contract": execution_contract,
            "commit_request_preview": commit_request_preview,
            "evidence_contract": evidence_contract,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "debug_context": debug_context,
        }

    def build_governed_replay_approval_gate(
        self,
        gateway_preview: Optional[dict] = None,
        *,
        decision: Optional[dict] = None,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        gateway = gateway_preview if isinstance(gateway_preview, dict) else self.build_governed_replay_execution_gateway_preview(
            decision,
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        gateway_status = str(gateway.get("gateway_status") or "blocked")
        policy_gate_status = str(gateway.get("policy_gate_status") or "blocked")
        if gateway_status == "preview_ready":
            approval_status = "review_required"
        else:
            approval_status = "blocked"
        resolved_replay_id = gateway.get("replay_id") or replay_id
        resolved_transaction_id = gateway.get("transaction_id") or transaction_id or "unknown_transaction"
        action = str(gateway.get("action") or "unknown")
        decision_type = str(gateway.get("decision_type") or "blocked_unknown_action")
        blocked_reason = str(gateway.get("blocked_reason") or "")
        execution_contract = gateway.get("execution_contract") if isinstance(gateway.get("execution_contract"), dict) else {}
        risk_level = execution_contract.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        debug_context = {
            "source": "governed_replay_approval_gate_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "gateway_status": gateway_status,
            "policy_gate_status": policy_gate_status,
            "approval_status": approval_status,
            "approval_required": True,
            "approval_granted": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "decision_type": decision_type,
            "risk_level": risk_level,
        }
        return {
            "source": "governed_replay_approval_gate_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "gateway_status": gateway_status,
            "policy_gate_status": policy_gate_status,
            "approval_status": approval_status,
            "approval_required": True,
            "approval_granted": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "decision_type": decision_type,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def build_governed_replay_controlled_dispatch_preview(
        self,
        approval_gate: Optional[dict] = None,
        *,
        gateway_preview: Optional[dict] = None,
        decision: Optional[dict] = None,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        approval = approval_gate if isinstance(approval_gate, dict) else self.build_governed_replay_approval_gate(
            gateway_preview,
            decision=decision,
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        gateway = gateway_preview if isinstance(gateway_preview, dict) else {}
        approval_status = str(approval.get("approval_status") or "blocked")
        approval_granted = bool(approval.get("approval_granted"))
        dispatch_status = "blocked" if approval_status == "blocked" else "preview_blocked"
        blocked_reason = str(approval.get("blocked_reason") or "")
        if not approval_granted and not blocked_reason:
            blocked_reason = "approval_not_granted"
        resolved_replay_id = approval.get("replay_id") or replay_id
        resolved_transaction_id = approval.get("transaction_id") or transaction_id or "unknown_transaction"
        action = str(approval.get("action") or "unknown")
        risk_level = approval.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        evidence_contract = gateway.get("evidence_contract") if isinstance(gateway.get("evidence_contract"), dict) else {}
        required_evidence = list(evidence_contract.get("required_evidence") or [])
        available = list(evidence_contract.get("available_evidence") or [])
        missing = list(evidence_contract.get("missing_evidence") or [])
        decision_type = str(approval.get("decision_type") or evidence_contract.get("decision_type") or "blocked_unknown_action")
        evidence_capture_contract = {
            "capture_required": True,
            "capture_mode": "preview_only",
            "required_evidence": required_evidence,
            "available_evidence": available,
            "missing_evidence": missing,
            "evidence_complete": bool(evidence_contract.get("evidence_complete")) if evidence_contract else not missing,
            "decision_type": decision_type,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
        }
        execution_envelope = {
            "preview_only": True,
            "execution_allowed": False,
            "dispatch_eligible": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "mutation_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "requires_human_approval": True,
            "approval_granted": False,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "risk_level": risk_level,
        }
        debug_context = {
            "source": "governed_replay_controlled_dispatch_preview_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "approval_status": approval_status,
            "approval_granted": False,
            "dispatch_status": dispatch_status,
            "dispatch_eligible": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
        }
        return {
            "source": "governed_replay_controlled_dispatch_preview_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "approval_status": approval_status,
            "approval_granted": False,
            "dispatch_status": dispatch_status,
            "dispatch_eligible": False,
            "execution_envelope": execution_envelope,
            "evidence_capture_contract": evidence_capture_contract,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "debug_context": debug_context,
        }

    def build_governed_replay_dispatch_authorization(
        self,
        dispatch_preview: Optional[dict] = None,
        *,
        approval_gate: Optional[dict] = None,
        gateway_preview: Optional[dict] = None,
        decision: Optional[dict] = None,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        dispatch = dispatch_preview if isinstance(dispatch_preview, dict) else self.build_governed_replay_controlled_dispatch_preview(
            approval_gate,
            gateway_preview=gateway_preview,
            decision=decision,
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        dispatch_status = str(dispatch.get("dispatch_status") or "blocked")
        dispatch_eligible = bool(dispatch.get("dispatch_eligible"))
        authorization_status = "blocked" if dispatch_status == "blocked" else "review_required"
        resolved_replay_id = dispatch.get("replay_id") or replay_id
        resolved_transaction_id = dispatch.get("transaction_id") or transaction_id or "unknown_transaction"
        action = str(dispatch.get("action") or "unknown")
        envelope = dispatch.get("execution_envelope") if isinstance(dispatch.get("execution_envelope"), dict) else {}
        risk_level = envelope.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        blocked_reason = str(dispatch.get("blocked_reason") or "")
        sandbox_reason = blocked_reason or "authorization_not_granted"
        sandbox_preview = {
            "preview_only": True,
            "sandbox_eligible": False,
            "sandbox_execution_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "mutation_allowed": False,
            "reason": sandbox_reason,
        }
        execution_ticket = {
            "ticket_type": "dispatch_authorization_preview",
            "preview_only": True,
            "ticket_status": "not_issued",
            "authorization_granted": False,
            "execution_allowed": False,
            "dispatch_eligible": False,
            "sandbox_eligible": False,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "risk_level": risk_level,
        }
        immutable_audit_record = {
            "record_type": "dispatch_authorization_preview",
            "immutable": True,
            "preview_only": True,
            "source": "governed_replay_dispatch_authorization_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "authorization_status": authorization_status,
            "authorization_granted": False,
            "dispatch_status": dispatch_status,
            "dispatch_eligible": False,
            "sandbox_eligible": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "blocked_reason": blocked_reason,
        }
        debug_context = {
            "source": "governed_replay_dispatch_authorization_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "dispatch_status": dispatch_status,
            "dispatch_eligible": False,
            "authorization_status": authorization_status,
            "authorization_required": True,
            "authorization_granted": False,
            "sandbox_eligible": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
        }
        return {
            "source": "governed_replay_dispatch_authorization_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "dispatch_status": dispatch_status,
            "dispatch_eligible": dispatch_eligible and False,
            "authorization_status": authorization_status,
            "authorization_required": True,
            "authorization_granted": False,
            "sandbox_eligible": False,
            "sandbox_preview": sandbox_preview,
            "execution_ticket": execution_ticket,
            "immutable_audit_record": immutable_audit_record,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def build_governed_replay_immutable_journal_preview(
        self,
        dispatch_authorization: Optional[dict] = None,
        *,
        dispatch_preview: Optional[dict] = None,
        approval_gate: Optional[dict] = None,
        gateway_preview: Optional[dict] = None,
        decision: Optional[dict] = None,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        authorization = dispatch_authorization if isinstance(dispatch_authorization, dict) else self.build_governed_replay_dispatch_authorization(
            dispatch_preview,
            approval_gate=approval_gate,
            gateway_preview=gateway_preview,
            decision=decision,
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        dispatch = dispatch_preview if isinstance(dispatch_preview, dict) else {}
        approval = approval_gate if isinstance(approval_gate, dict) else {}
        gateway = gateway_preview if isinstance(gateway_preview, dict) else {}
        replay_decision = decision if isinstance(decision, dict) else {}
        authorization_status = str(authorization.get("authorization_status") or "blocked")
        dispatch_status = str(authorization.get("dispatch_status") or dispatch.get("dispatch_status") or "blocked")
        dispatch_eligible = bool(authorization.get("dispatch_eligible") or dispatch.get("dispatch_eligible"))
        sandbox_eligible = bool(authorization.get("sandbox_eligible"))
        resolved_replay_id = authorization.get("replay_id") or dispatch.get("replay_id") or replay_id
        resolved_transaction_id = authorization.get("transaction_id") or dispatch.get("transaction_id") or transaction_id or "unknown_transaction"
        action = str(authorization.get("action") or dispatch.get("action") or "unknown")
        blocked_reason = str(authorization.get("blocked_reason") or dispatch.get("blocked_reason") or "")
        risk_level = authorization.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        journal_status = "preview_only"
        authorization_granted = False
        journal_entry_preview = {
            "entry_type": "runtime_replay_governance_preview",
            "immutable": True,
            "preview_only": True,
            "write_allowed": False,
            "append_allowed": False,
            "persist_allowed": False,
            "source": "governed_replay_immutable_journal_preview_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "authorization_status": authorization_status,
            "authorization_granted": authorization_granted,
            "authorization_blocked": authorization_status == "blocked",
            "authorization_pending": authorization_status == "review_required",
            "dispatch_status": dispatch_status,
            "dispatch_eligible": False,
            "sandbox_eligible": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
        }

        def stage_record(stage: str, status: Any, source: str, reason: Any = None) -> dict:
            return {
                "stage": stage,
                "status": str(status or "unknown"),
                "source": source,
                "blocked_reason": str(reason or ""),
            }

        dispatch_evidence = dispatch.get("evidence_capture_contract") if isinstance(dispatch.get("evidence_capture_contract"), dict) else {}
        authorization_audit = authorization.get("immutable_audit_record") if isinstance(authorization.get("immutable_audit_record"), dict) else {}
        decision_type = str(
            replay_decision.get("decision_type")
            or gateway.get("decision_type")
            or approval.get("decision_type")
            or dispatch_evidence.get("decision_type")
            or authorization_audit.get("decision_type")
            or "unknown"
        )
        gateway_status = str(gateway.get("gateway_status") or ("blocked" if authorization_status == "blocked" else "preview_ready"))
        approval_status = str(approval.get("approval_status") or ("blocked" if authorization_status == "blocked" else "review_required"))
        replay_lineage = [
            stage_record("replay_request", action, "runtime_replay_execution_bridge_v2", ""),
            stage_record("preflight", replay_decision.get("status") or decision_type, "runtime_replay_execution_bridge_v2", replay_decision.get("blocked_reason")),
            stage_record("decision", decision_type, "runtime_replay_execution_bridge_v2", replay_decision.get("blocked_reason")),
            stage_record("gateway_preview", gateway_status, "governed_replay_execution_gateway_v1", gateway.get("blocked_reason")),
            stage_record("approval_gate", approval_status, "governed_replay_approval_gate_v1", approval.get("blocked_reason")),
            stage_record("controlled_dispatch_preview", dispatch_status, "governed_replay_controlled_dispatch_preview_v1", dispatch.get("blocked_reason")),
            stage_record("dispatch_authorization", authorization_status, "governed_replay_dispatch_authorization_v1", blocked_reason),
            stage_record("immutable_journal_preview", journal_status, "governed_replay_immutable_journal_preview_v1", blocked_reason),
        ]
        terminal_blocked = "terminal" in blocked_reason or decision_type == "blocked_terminal_recovery"
        missing_evidence_blocked = "missing evidence" in blocked_reason or decision_type == "blocked_missing_evidence"
        causality_chain = {
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "root_action": action,
            "decision_type": decision_type,
            "gateway_status": gateway_status,
            "approval_status": approval_status,
            "dispatch_status": dispatch_status,
            "authorization_status": authorization_status,
            "journal_status": journal_status,
            "terminal_blocked": bool(terminal_blocked),
            "missing_evidence_blocked": bool(missing_evidence_blocked),
            "execution_allowed": False,
        }
        sources = [item["source"] for item in replay_lineage]
        runtime_provenance = {
            "provenance_type": "governed_replay_runtime_preview",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "sources": sources,
            "governance_depth": len(replay_lineage),
            "final_status": journal_status,
            "blocked_reason": blocked_reason,
            "immutable_preview": True,
            "write_allowed": False,
        }
        debug_context = {
            "source": "governed_replay_immutable_journal_preview_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "authorization_status": authorization_status,
            "authorization_granted": authorization_granted,
            "journal_status": journal_status,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
        }
        return {
            "source": "governed_replay_immutable_journal_preview_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "authorization_status": authorization_status,
            "authorization_granted": authorization_granted,
            "journal_status": journal_status,
            "journal_entry_preview": journal_entry_preview,
            "replay_lineage": replay_lineage,
            "causality_chain": causality_chain,
            "runtime_provenance": runtime_provenance,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def build_governed_replay_governance_state_snapshot(
        self,
        immutable_journal_preview: Optional[dict] = None,
        *,
        dispatch_authorization: Optional[dict] = None,
        dispatch_preview: Optional[dict] = None,
        approval_gate: Optional[dict] = None,
        gateway_preview: Optional[dict] = None,
        decision: Optional[dict] = None,
        transaction_id: Optional[str] = None,
        available_evidence: Any = None,
        replay_id: Any = None,
    ) -> dict:
        journal = immutable_journal_preview if isinstance(immutable_journal_preview, dict) else self.build_governed_replay_immutable_journal_preview(
            dispatch_authorization,
            dispatch_preview=dispatch_preview,
            approval_gate=approval_gate,
            gateway_preview=gateway_preview,
            decision=decision,
            transaction_id=transaction_id,
            available_evidence=available_evidence,
            replay_id=replay_id,
        )
        journal_entry = journal.get("journal_entry_preview") if isinstance(journal.get("journal_entry_preview"), dict) else {}
        causality = journal.get("causality_chain") if isinstance(journal.get("causality_chain"), dict) else {}
        lineage = list(journal.get("replay_lineage") or [])
        provenance = journal.get("runtime_provenance") if isinstance(journal.get("runtime_provenance"), dict) else {}
        resolved_replay_id = journal.get("replay_id") or replay_id
        resolved_transaction_id = journal.get("transaction_id") or transaction_id or "unknown_transaction"
        action = str(journal.get("action") or "unknown")
        blocked_reason = str(journal.get("blocked_reason") or "")
        risk_level = journal.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        journal_status = str(journal.get("journal_status") or "preview_only")
        authorization_status = str(journal.get("authorization_status") or journal_entry.get("authorization_status") or "blocked")
        dispatch_status = str(journal_entry.get("dispatch_status") or causality.get("dispatch_status") or "blocked")
        approval_status = str(causality.get("approval_status") or ("blocked" if authorization_status == "blocked" else "review_required"))
        gateway_status = str(causality.get("gateway_status") or ("blocked" if authorization_status == "blocked" else "preview_ready"))
        decision_type = str(causality.get("decision_type") or "unknown")
        snapshot_status = "preview_only"
        final_status = snapshot_status
        stage_order = [item.get("stage") for item in lineage if isinstance(item, dict) and item.get("stage")]
        stage_order.append("governance_state_snapshot")
        stage_statuses = {
            str(item.get("stage")): str(item.get("status") or "unknown")
            for item in lineage
            if isinstance(item, dict) and item.get("stage")
        }
        stage_statuses["governance_state_snapshot"] = snapshot_status
        sources = list(provenance.get("sources") or [item.get("source") for item in lineage if isinstance(item, dict) and item.get("source")])
        sources.append("governed_replay_governance_state_snapshot_v1")
        governance_depth = len(stage_order)
        terminal_blocked = bool(causality.get("terminal_blocked"))
        missing_evidence_blocked = bool(causality.get("missing_evidence_blocked"))
        governance_flags = {
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
            "write_allowed": False,
            "persist_allowed": False,
            "append_allowed": False,
        }
        snapshot_preview = {
            "snapshot_type": "governed_replay_state_snapshot_preview",
            "immutable": True,
            "preview_only": True,
            "write_allowed": False,
            "persist_allowed": False,
            "append_allowed": False,
            "source": "governed_replay_governance_state_snapshot_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "journal_status": journal_status,
            "authorization_status": authorization_status,
            "dispatch_status": dispatch_status,
            "approval_status": approval_status,
            "gateway_status": gateway_status,
            "decision_type": decision_type,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
        }
        freeze_frame = {
            "freeze_type": "governance_state_freeze_frame",
            "immutable": True,
            "preview_only": True,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "final_status": final_status,
            "blocked_reason": blocked_reason,
            "governance_depth": governance_depth,
            "terminal_blocked": terminal_blocked,
            "missing_evidence_blocked": missing_evidence_blocked,
            "execution_allowed": False,
            "mutation_allowed": False,
        }
        deterministic_reconstruction_payload = {
            "reconstruction_type": "deterministic_governance_reconstruction_preview",
            "preview_only": True,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "stage_order": stage_order,
            "stage_statuses": stage_statuses,
            "blocked_reason": blocked_reason,
            "final_status": final_status,
            "governance_depth": governance_depth,
            "sources": sources,
        }
        replayable_governance_state = {
            "replayable": True,
            "preview_only": True,
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "current_stage": "governance_state_snapshot",
            "final_status": final_status,
            "blocked_reason": blocked_reason,
            "stage_order": stage_order,
            "governance_flags": governance_flags,
        }
        lineage_digest = {
            "lineage_stage_count": len(stage_order),
            "governance_depth": governance_depth,
            "first_stage": stage_order[0] if stage_order else None,
            "last_stage": stage_order[-1] if stage_order else None,
            "sources_count": len(sources),
            "blocked_reason": blocked_reason,
            "final_status": final_status,
        }
        debug_context = {
            "source": "governed_replay_governance_state_snapshot_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "snapshot_status": snapshot_status,
            "final_status": final_status,
            "governance_depth": governance_depth,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            **governance_flags,
        }
        return {
            "source": "governed_replay_governance_state_snapshot_v1",
            "replay_id": resolved_replay_id,
            "transaction_id": resolved_transaction_id,
            "action": action,
            "snapshot_status": snapshot_status,
            "snapshot_preview": snapshot_preview,
            "freeze_frame": freeze_frame,
            "deterministic_reconstruction_payload": deterministic_reconstruction_payload,
            "replayable_governance_state": replayable_governance_state,
            "lineage_digest": lineage_digest,
            "governance_flags": governance_flags,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def build_governed_replay_governance_state_diff_verification(
        self,
        snapshot_a: dict,
        snapshot_b: Optional[dict] = None,
    ) -> dict:
        left = snapshot_a if isinstance(snapshot_a, dict) else {}
        right = snapshot_b if isinstance(snapshot_b, dict) else left
        compared_fields = [
            "replay_id",
            "transaction_id",
            "action",
            "snapshot_status",
            "blocked_reason",
            "risk_level",
            "execution_allowed",
            "mutation_allowed",
            "executor_dispatch_allowed",
            "scheduler_dispatch_allowed",
            "command_execution_allowed",
            "authorization_granted",
            "auto_commit",
            "auto_rollback",
        ]
        changed_fields = [field for field in compared_fields if left.get(field) != right.get(field)]
        unchanged_fields = [field for field in compared_fields if field not in changed_fields]
        capability_flags = [
            "execution_allowed",
            "mutation_allowed",
            "executor_dispatch_allowed",
            "scheduler_dispatch_allowed",
            "command_execution_allowed",
            "authorization_granted",
            "auto_commit",
            "auto_rollback",
        ]
        drifted_flags = [flag for flag in capability_flags if bool(left.get(flag)) != bool(right.get(flag))]
        unsafe_escalations = [flag for flag in capability_flags if bool(left.get(flag)) is False and bool(right.get(flag)) is True]
        left_payload = left.get("deterministic_reconstruction_payload") if isinstance(left.get("deterministic_reconstruction_payload"), dict) else {}
        right_payload = right.get("deterministic_reconstruction_payload") if isinstance(right.get("deterministic_reconstruction_payload"), dict) else {}
        left_order = list(left_payload.get("stage_order") or [])
        right_order = list(right_payload.get("stage_order") or [])
        stage_order_consistent = left_order == right_order
        final_status_consistent = str(left_payload.get("final_status") or "") == str(right_payload.get("final_status") or "")
        blocked_reason_consistent = str(left.get("blocked_reason") or "") == str(right.get("blocked_reason") or "")
        deterministic = bool(not changed_fields and stage_order_consistent and final_status_consistent and blocked_reason_consistent)
        left_digest = left.get("lineage_digest") if isinstance(left.get("lineage_digest"), dict) else {}
        right_digest = right.get("lineage_digest") if isinstance(right.get("lineage_digest"), dict) else {}
        governance_depth_consistent = left_digest.get("governance_depth") == right_digest.get("governance_depth")
        sources_consistent = list(left_payload.get("sources") or []) == list(right_payload.get("sources") or [])
        lineage_stage_count_consistent = left_digest.get("lineage_stage_count") == right_digest.get("lineage_stage_count")
        reconstruction_consistent = bool(governance_depth_consistent and sources_consistent and lineage_stage_count_consistent and stage_order_consistent)
        replay_id = right.get("replay_id") or left.get("replay_id")
        transaction_id = right.get("transaction_id") or left.get("transaction_id")
        action = str(right.get("action") or left.get("action") or "unknown")
        blocked_reason = str(right.get("blocked_reason") or left.get("blocked_reason") or "")
        risk_level = right.get("risk_level") or left.get("risk_level") or self._runtime_replay_execution_risk_level(action)
        governance_diff = {
            "diff_type": "governance_state_snapshot_diff_preview",
            "preview_only": True,
            "has_diff": bool(changed_fields),
            "changed_fields": changed_fields,
            "unchanged_fields": unchanged_fields,
            "compared_fields": compared_fields,
            "snapshot_a_status": left.get("snapshot_status"),
            "snapshot_b_status": right.get("snapshot_status"),
            "blocked_reason_changed": "blocked_reason" in changed_fields,
            "risk_level_changed": "risk_level" in changed_fields,
            "capability_flags_changed": bool(drifted_flags),
        }
        capability_drift_detection = {
            "drift_type": "capability_flag_drift_detection_preview",
            "preview_only": True,
            "drift_detected": bool(drifted_flags),
            "drifted_flags": drifted_flags,
            "safe_flags_preserved": not unsafe_escalations,
            "unsafe_flag_escalation_detected": bool(unsafe_escalations),
        }
        deterministic_verification = {
            "verification_type": "deterministic_governance_snapshot_verification_preview",
            "preview_only": True,
            "deterministic": deterministic,
            "reason": "deterministic snapshot match" if deterministic else "governance snapshot drift detected",
            "compared_stage_order": {"snapshot_a": left_order, "snapshot_b": right_order},
            "stage_order_consistent": stage_order_consistent,
            "final_status_consistent": final_status_consistent,
            "blocked_reason_consistent": blocked_reason_consistent,
        }
        reconstruction_consistency_check = {
            "check_type": "governance_reconstruction_consistency_preview",
            "preview_only": True,
            "reconstruction_consistent": reconstruction_consistent,
            "governance_depth_consistent": governance_depth_consistent,
            "sources_consistent": sources_consistent,
            "lineage_stage_count_consistent": lineage_stage_count_consistent,
            "reason": "reconstruction inputs consistent" if reconstruction_consistent else "reconstruction input drift detected",
        }
        debug_context = {
            "source": "governed_replay_governance_state_diff_verification_v1",
            "replay_id": replay_id,
            "transaction_id": transaction_id,
            "action": action,
            "verification_status": "preview_only",
            "has_diff": bool(changed_fields),
            "drift_detected": bool(drifted_flags),
            "unsafe_flag_escalation_detected": bool(unsafe_escalations),
            "deterministic": deterministic,
            "reconstruction_consistent": reconstruction_consistent,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
        }
        return {
            "source": "governed_replay_governance_state_diff_verification_v1",
            "replay_id": replay_id,
            "transaction_id": transaction_id,
            "action": action,
            "verification_status": "preview_only",
            "snapshot_a": left,
            "snapshot_b": right,
            "governance_diff": governance_diff,
            "capability_drift_detection": capability_drift_detection,
            "deterministic_verification": deterministic_verification,
            "reconstruction_consistency_check": reconstruction_consistency_check,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def build_governed_replay_policy_resolution(self, diff_verification: dict) -> dict:
        verification = diff_verification if isinstance(diff_verification, dict) else {}
        capability = verification.get("capability_drift_detection") if isinstance(verification.get("capability_drift_detection"), dict) else {}
        deterministic_check = verification.get("deterministic_verification") if isinstance(verification.get("deterministic_verification"), dict) else {}
        reconstruction_check = verification.get("reconstruction_consistency_check") if isinstance(verification.get("reconstruction_consistency_check"), dict) else {}
        unsafe_escalation = bool(capability.get("unsafe_flag_escalation_detected"))
        deterministic = bool(deterministic_check.get("deterministic"))
        reconstruction_consistent = bool(reconstruction_check.get("reconstruction_consistent"))
        deterministic_failure = not deterministic
        reconstruction_inconsistency = not reconstruction_consistent
        if unsafe_escalation:
            risk_category = "capability_escalation"
            escalation_target = "capability_integrity_review"
            recommended_action = "investigate_capability_drift"
        elif deterministic_failure:
            risk_category = "deterministic_drift"
            escalation_target = "deterministic_verification_review"
            recommended_action = "review_deterministic_pipeline"
        elif reconstruction_inconsistency:
            risk_category = "reconstruction_inconsistency"
            escalation_target = "reconstruction_integrity_review"
            recommended_action = "review_reconstruction_consistency"
        else:
            risk_category = "stable_preview"
            escalation_target = "stable_preview_review"
            recommended_action = "maintain_preview_state"
        escalation_required = risk_category != "stable_preview"
        governance_stable = not escalation_required
        capability_integrity_preserved = not unsafe_escalation
        blocked_reason = str(verification.get("blocked_reason") or "")
        risk_level = verification.get("risk_level") or "blocked"
        replay_id = verification.get("replay_id")
        transaction_id = verification.get("transaction_id")
        action = str(verification.get("action") or "unknown")
        risk_classification = {
            "classification_type": "governance_risk_classification_preview",
            "preview_only": True,
            "risk_level": risk_level,
            "risk_category": risk_category,
            "escalation_required": escalation_required,
            "unsafe_flag_escalation_detected": unsafe_escalation,
            "deterministic_failure_detected": deterministic_failure,
            "reconstruction_inconsistency_detected": reconstruction_inconsistency,
        }
        escalation_routing = {
            "routing_type": "governance_escalation_routing_preview",
            "preview_only": True,
            "escalation_required": escalation_required,
            "escalation_target": escalation_target,
            "escalation_reason": risk_category,
            "human_review_required": True,
            "sandbox_review_required": escalation_required,
            "immutable_audit_required": True,
        }
        governance_outcome = {
            "outcome_type": "governance_resolution_preview",
            "preview_only": True,
            "final_governance_state": "blocked" if escalation_required else "stable_preview",
            "blocked": escalation_required,
            "escalation_required": escalation_required,
            "governance_stable": governance_stable,
            "deterministic": deterministic,
            "reconstruction_consistent": reconstruction_consistent,
            "capability_integrity_preserved": capability_integrity_preserved,
        }
        policy_decision = {
            "decision_type": "governance_policy_decision_preview",
            "preview_only": True,
            "execution_allowed": False,
            "mutation_allowed": False,
            "authorization_granted": False,
            "escalation_required": escalation_required,
            "governance_stable": governance_stable,
            "blocked_reason": blocked_reason,
            "recommended_action": recommended_action,
        }

        def integrity_status(stable: bool, escalation_detected: bool) -> dict:
            return {
                "status": "stable" if stable else "escalation_required",
                "stable": stable,
                "escalation_detected": escalation_detected,
                "blocked": escalation_detected,
                "preview_only": True,
            }

        capability_integrity_status = integrity_status(capability_integrity_preserved, unsafe_escalation)
        deterministic_integrity_status = integrity_status(deterministic, deterministic_failure)
        reconstruction_integrity_status = integrity_status(reconstruction_consistent, reconstruction_inconsistency)
        debug_context = {
            "source": "governed_replay_policy_resolution_v1",
            "replay_id": replay_id,
            "transaction_id": transaction_id,
            "action": action,
            "policy_resolution_status": "preview_only",
            "risk_category": risk_category,
            "escalation_required": escalation_required,
            "escalation_target": escalation_target,
            "governance_stable": governance_stable,
            "deterministic": deterministic,
            "reconstruction_consistent": reconstruction_consistent,
            "capability_integrity_preserved": capability_integrity_preserved,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
        }
        return {
            "source": "governed_replay_policy_resolution_v1",
            "replay_id": replay_id,
            "transaction_id": transaction_id,
            "action": action,
            "policy_resolution_status": "preview_only",
            "risk_classification": risk_classification,
            "escalation_routing": escalation_routing,
            "governance_outcome": governance_outcome,
            "policy_decision": policy_decision,
            "capability_integrity_status": capability_integrity_status,
            "deterministic_integrity_status": deterministic_integrity_status,
            "reconstruction_integrity_status": reconstruction_integrity_status,
            "execution_allowed": False,
            "mutation_allowed": False,
            "executor_dispatch_allowed": False,
            "scheduler_dispatch_allowed": False,
            "command_execution_allowed": False,
            "authorization_granted": False,
            "auto_commit": False,
            "auto_rollback": False,
            "blocked_reason": blocked_reason,
            "risk_level": risk_level,
            "debug_context": debug_context,
        }

    def _runtime_continuation_recovery_summary(self, transaction_id: str) -> dict:
        plan = self._runtime_continuation_plan(transaction_id)
        action = str(plan.get("continuation_action") or "unknown")
        terminal = bool(plan.get("terminal"))
        blocked = bool(plan.get("blocked"))
        record_found = bool(plan.get("record_found"))
        replay_request = self._build_runtime_replay_request_from_plan(plan)
        preflight = self._build_replay_execution_preflight(
            replay_request,
            available_evidence=replay_request.get("required_evidence"),
            recovery_summary=self._runtime_replay_recovery_summary(transaction_id),
        )
        decision = self.build_replay_execution_decision(preflight)
        return {
            "transaction_id": plan.get("transaction_id") or str(transaction_id or "unknown_transaction"),
            "record_found": record_found,
            "recoverable": bool(record_found and not terminal and not blocked and action != "unknown"),
            "continuation_action": action,
            "replay_action": replay_request.get("replay_action"),
            "replay_request": replay_request,
            "replay_preflight": preflight,
            "replay_decision": decision,
            "can_execute": bool(replay_request.get("can_execute")),
            "terminal": terminal,
            "blocked": blocked,
            "requires_commit": bool(plan.get("requires_commit")),
            "requires_rollback": bool(plan.get("requires_rollback")),
        }

    def _reconstruct_runtime_transaction_context(self, transaction_id: str) -> dict:
        record = self._read_runtime_transaction_record(transaction_id, default={})
        record_found = bool(record)
        transaction_context = record.get("transaction_context") if isinstance(record.get("transaction_context"), dict) else {}
        resolved_transaction_id = str(
            transaction_context.get("transaction_id")
            or transaction_id
            or ""
        ).strip()
        continuation_plan = self._build_runtime_continuation_plan_from_record(record)
        replay_request = self._build_runtime_replay_request_from_plan(continuation_plan)
        replay_recovery_summary = self._runtime_replay_recovery_summary(resolved_transaction_id or transaction_id)
        replay_preflight = self._build_replay_execution_preflight(
            replay_request,
            available_evidence=replay_request.get("required_evidence"),
            recovery_summary=replay_recovery_summary,
        )
        replay_decision = self.build_replay_execution_decision(replay_preflight)
        return {
            "transaction_id": resolved_transaction_id or "unknown_transaction",
            "gate_state": record.get("gate_state") if record_found else "unknown",
            "lifecycle_stage": record.get("lifecycle_stage") if record_found else "unknown",
            "ownership": record.get("ownership") if isinstance(record.get("ownership"), dict) else {},
            "execution_review": record.get("execution_review") if isinstance(record.get("execution_review"), dict) else {},
            "can_commit": bool(record.get("can_commit")) if record_found else False,
            "can_rollback": bool(record.get("can_rollback")) if record_found else False,
            "continuation_action": continuation_plan.get("continuation_action"),
            "continuation_plan": continuation_plan,
            "replay_action": replay_request.get("replay_action"),
            "replay_request": replay_request,
            "replay_preflight": replay_preflight,
            "replay_decision": replay_decision,
            "can_execute": bool(replay_request.get("can_execute")),
            "terminal": bool(continuation_plan.get("terminal")),
            "blocked": bool(continuation_plan.get("blocked")),
            "record_found": record_found,
        }

    def _runtime_transaction_recovery_summary(self, transaction_id: str) -> dict:
        context = self._reconstruct_runtime_transaction_context(transaction_id)
        gate_state = str(context.get("gate_state") or "unknown").strip().lower()
        record_found = bool(context.get("record_found"))
        can_commit = bool(context.get("can_commit"))
        can_rollback = bool(context.get("can_rollback"))
        continuation_plan = context.get("continuation_plan") if isinstance(context.get("continuation_plan"), dict) else {}
        terminal = bool(context.get("terminal"))
        blocked = bool(context.get("blocked"))
        continuation_action = str(context.get("continuation_action") or "unknown")
        replay_request = context.get("replay_request") if isinstance(context.get("replay_request"), dict) else {}
        replay_preflight = context.get("replay_preflight") if isinstance(context.get("replay_preflight"), dict) else {}
        replay_decision = context.get("replay_decision") if isinstance(context.get("replay_decision"), dict) else {}
        return {
            "transaction_id": context.get("transaction_id") or str(transaction_id or "unknown_transaction"),
            "record_found": record_found,
            "recoverable": bool(
                record_found
                and gate_state not in {"rejected", "rolled_back"}
                and (can_commit or can_rollback)
            ),
            "gate_state": gate_state,
            "lifecycle_stage": context.get("lifecycle_stage") or "unknown",
            "can_commit": can_commit,
            "can_rollback": can_rollback,
            "continuation_action": continuation_action,
            "continuation_plan": continuation_plan,
            "replay_action": replay_request.get("replay_action") or "unknown",
            "replay_request": replay_request,
            "replay_preflight": replay_preflight,
            "replay_decision": replay_decision,
            "can_execute": bool(replay_request.get("can_execute")),
            "terminal": terminal,
            "blocked": blocked,
        }

    def _runtime_continuation_debug_context(self, transaction_id: str) -> dict:
        record = self._read_runtime_transaction_record(transaction_id, default={})
        continuation_plan = self._build_runtime_continuation_plan_from_record(record)
        replay_request = self._build_runtime_replay_request_from_plan(continuation_plan)
        replay_recovery_summary = self._runtime_replay_recovery_summary(transaction_id)
        preflight = self._build_replay_execution_preflight(
            replay_request,
            available_evidence=replay_request.get("required_evidence"),
            recovery_summary=replay_recovery_summary,
        )
        decision = self.build_replay_execution_decision(preflight)
        return {
            "transaction_id": str(transaction_id or "unknown_transaction"),
            "record": record,
            "continuation_plan": continuation_plan,
            "replay_request": replay_request,
            "replay_preflight": preflight,
            "replay_decision": decision,
            "recovery_summary": self._runtime_continuation_recovery_summary(transaction_id),
        }

    def _runtime_replay_debug_context(self, transaction_id: str) -> dict:
        continuation_plan = self._runtime_continuation_plan(transaction_id)
        replay_request = self._build_runtime_replay_request_from_plan(continuation_plan)
        replay_recovery_summary = self._runtime_replay_recovery_summary(transaction_id)
        preflight = self._build_replay_execution_preflight(
            replay_request,
            available_evidence=replay_request.get("required_evidence"),
            recovery_summary=replay_recovery_summary,
        )
        decision = self.build_replay_execution_decision(preflight)
        return {
            "transaction_id": str(transaction_id or "unknown_transaction"),
            "continuation_plan": continuation_plan,
            "replay_request": replay_request,
            "replay_preflight": preflight,
            "replay_decision": decision,
            "replay_recovery_summary": replay_recovery_summary,
        }

    def _maybe_persist_runtime_transaction_record(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> Optional[str]:
        if self._runtime_write_scope(file_path) != "repo_source":
            return None
        if not self._is_governed_mutation_write(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        ):
            return None
        if not self._has_transaction_governance_context(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        ):
            return None
        record = self._build_runtime_transaction_record(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        return self._write_runtime_transaction_record(record)

    def _raise_transaction_governance_error(
        self,
        file_path: str,
        error_type: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        context = self._build_governed_mutation_context(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        messages = {
            "missing_governance_metadata": "repo source writes require governance metadata",
            "missing_governed_mutation_classification": "repo source writes require governed mutation classification",
            "missing_transaction_context": "repo source writes require transaction governance context",
            "blocked_unknown_path": "TaskRuntime runtime write blocked for unknown persistence domain",
            "invalid_repo_source_mutation_attempt": "invalid repo source mutation attempt",
        }
        message = messages.get(error_type, messages["invalid_repo_source_mutation_attempt"])
        raise PermissionError(f"{message}: {context}")

    def _raise_transaction_gate_state_error(
        self,
        file_path: str,
        error_type: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        summary = self._build_transaction_gate_summary(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        messages = {
            "rejected_mutation": "rejected repo source mutation writes are blocked",
            "rolled_back_mutation": "rolled-back repo source mutation writes are blocked",
            "invalid_terminal_mutation_write": "invalid terminal repo source mutation write",
        }
        message = messages.get(error_type, messages["invalid_terminal_mutation_write"])
        raise PermissionError(f"{message}: {summary}")

    def _raise_transaction_lifecycle_error(
        self,
        file_path: str,
        error_type: str,
        *,
        previous_state: Any = None,
        next_state: Any = None,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        summary = self._build_transaction_lifecycle_summary(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        if previous_state is not None:
            summary["previous_gate_state"] = str(previous_state)
            summary["previous_lifecycle_stage"] = self._transaction_lifecycle_stage(str(previous_state))
        if next_state is not None:
            summary["next_gate_state"] = str(next_state)
            summary["next_lifecycle_stage"] = self._transaction_lifecycle_stage(str(next_state))
        messages = {
            "invalid_transition": "invalid transaction lifecycle transition",
            "illegal_lifecycle_mutation": "illegal transaction lifecycle mutation",
            "transition_from_terminal_state": "transaction lifecycle transition from terminal state is blocked",
            "rejected_mutation": "rejected repo source mutation writes are blocked",
            "rolled_back_mutation": "rolled-back repo source mutation writes are blocked",
        }
        message = messages.get(error_type, messages["illegal_lifecycle_mutation"])
        raise PermissionError(f"{message}: {summary}")

    def _raise_runtime_ownership_error(
        self,
        file_path: str,
        error_type: str,
        *,
        gate_state: Any = None,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        summary = self._build_runtime_ownership_summary(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        normalized_gate_state = str(gate_state or self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )).strip().lower()
        ownership = summary.get("ownership") if isinstance(summary.get("ownership"), dict) else {}
        summary["gate_state"] = normalized_gate_state
        summary["ownership_validation"] = self._validate_runtime_ownership_for_state(
            normalized_gate_state,
            ownership,
        )
        messages = {
            "missing_ownership": "repo source writes require runtime ownership metadata",
            "missing_initiator": "repo source writes require runtime ownership initiator",
            "missing_reviewer": "repo source writes require runtime ownership reviewer",
            "missing_verifier": "repo source writes require runtime ownership verifier",
            "missing_approver": "repo source writes require runtime ownership approver",
            "missing_committer": "repo source writes require runtime ownership committer",
            "missing_rollback_owner": "repo source writes require runtime ownership rollback owner",
            "invalid_ownership_for_lifecycle_state": "invalid runtime ownership for lifecycle state",
        }
        message = messages.get(error_type, messages["invalid_ownership_for_lifecycle_state"])
        raise PermissionError(f"{message}: {summary}")

    def _raise_execution_review_error(
        self,
        file_path: str,
        error_type: str,
        *,
        gate_state: Any = None,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        summary = self._build_execution_review_summary(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        normalized_gate_state = str(gate_state or self._normalize_transaction_gate_state(
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )).strip().lower()
        review_context = summary.get("execution_review") if isinstance(summary.get("execution_review"), dict) else {}
        summary["gate_state"] = normalized_gate_state
        summary["execution_review_validation"] = self._validate_execution_review_for_state(
            normalized_gate_state,
            review_context,
        )
        messages = {
            "missing_execution_review": "repo source writes require execution review metadata",
            "missing_execution": "repo source writes require execution review execution",
            "missing_verification": "repo source writes require execution review verification",
            "missing_review": "repo source writes require execution review review",
            "missing_approval": "repo source writes require execution review approval",
            "missing_commit_readiness": "repo source writes require execution review commit readiness",
            "missing_rollback_readiness": "repo source writes require execution review rollback readiness",
            "invalid_execution_review_for_lifecycle_state": "invalid execution review for lifecycle state",
        }
        message = messages.get(error_type, messages["invalid_execution_review_for_lifecycle_state"])
        raise PermissionError(f"{message}: {summary}")

    def _raise_repo_source_governance_error(
        self,
        file_path: str,
        error_type: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> None:
        self._raise_transaction_governance_error(
            file_path,
            error_type,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )

    def _build_runtime_write_audit_record(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        domain = self._classify_persistence_domain(file_path)
        scope = self._runtime_write_scope(file_path)
        return {
            "path": str(file_path),
            "domain": domain,
            "scope": scope,
            "reason": str(reason or "").strip(),
            "has_lineage": isinstance(lineage, dict) and bool(lineage),
            "has_provenance": isinstance(provenance, dict) and bool(provenance),
        }

    def _assert_runtime_write_allowed(
        self,
        file_path: str,
        *,
        reason: Any = None,
        lineage: Any = None,
        provenance: Any = None,
    ) -> dict:
        domain = self._classify_persistence_domain(file_path)
        scope = self._runtime_write_scope(file_path)
        if scope == "runtime":
            return self._build_runtime_write_audit_record(
                file_path,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        if scope == "repo_source":
            try:
                self._validate_repo_source_write_metadata(
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            except PermissionError:
                self._raise_repo_source_governance_error(
                    file_path,
                    "missing_governance_metadata",
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            if not self._is_governed_mutation_write(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ):
                self._raise_repo_source_governance_error(
                    file_path,
                    "missing_governed_mutation_classification",
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            if not self._has_transaction_governance_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            ):
                self._raise_transaction_governance_error(
                    file_path,
                    "missing_transaction_context",
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            gate_state = self._normalize_transaction_gate_state(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
            previous_gate_state = self._extract_previous_transaction_gate_state(
                lineage=lineage,
                provenance=provenance,
            )
            if previous_gate_state is not None and not self._transaction_lifecycle_transition_allowed(
                previous_gate_state,
                gate_state,
            ):
                error_type = "invalid_transition"
                if previous_gate_state in {"committed", "rolled_back", "rejected"} and previous_gate_state != gate_state:
                    error_type = "transition_from_terminal_state"
                self._raise_transaction_lifecycle_error(
                    file_path,
                    error_type,
                    previous_state=previous_gate_state,
                    next_state=gate_state,
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            if gate_state == "rejected":
                self._raise_transaction_lifecycle_error(
                    file_path,
                    "rejected_mutation",
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            if gate_state == "rolled_back":
                self._raise_transaction_lifecycle_error(
                    file_path,
                    "rolled_back_mutation",
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            ownership = self._extract_runtime_ownership_chain(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
            ownership_validation = self._validate_runtime_ownership_for_state(gate_state, ownership)
            if not bool(ownership_validation.get("valid")):
                missing = list(ownership_validation.get("missing") or [])
                ownership_flags = self._ownership_chain_flags(ownership)
                if not ownership_flags.get("has_any_owner"):
                    error_type = "missing_ownership"
                elif "initiator" in missing:
                    error_type = "missing_initiator"
                elif len(missing) == 1:
                    error_type = f"missing_{missing[0]}"
                else:
                    error_type = "invalid_ownership_for_lifecycle_state"
                self._raise_runtime_ownership_error(
                    file_path,
                    error_type,
                    gate_state=gate_state,
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            execution_review = self._extract_execution_review_context(
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
            execution_review_validation = self._validate_execution_review_for_state(gate_state, execution_review)
            if not bool(execution_review_validation.get("valid")):
                missing = list(execution_review_validation.get("missing") or [])
                execution_review_flags = self._execution_review_flags(execution_review)
                missing_error_types = {
                    "executed": "missing_execution",
                    "verified": "missing_verification",
                    "reviewed": "missing_review",
                    "approved": "missing_approval",
                    "commit_ready": "missing_commit_readiness",
                    "rollback_ready": "missing_rollback_readiness",
                }
                if not execution_review_flags.get("has_any_review_signal"):
                    error_type = "missing_execution_review"
                elif len(missing) == 1:
                    error_type = missing_error_types.get(missing[0], "invalid_execution_review_for_lifecycle_state")
                else:
                    error_type = "invalid_execution_review_for_lifecycle_state"
                self._raise_execution_review_error(
                    file_path,
                    error_type,
                    gate_state=gate_state,
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            try:
                self._maybe_persist_runtime_transaction_record(
                    file_path,
                    reason=reason,
                    lineage=lineage,
                    provenance=provenance,
                )
            except (PermissionError, RuntimeError):
                raise
            except Exception:
                pass
            return self._build_runtime_write_audit_record(
                file_path,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
            )
        self._raise_repo_source_governance_error(
            file_path,
            "blocked_unknown_path",
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )

    def _persistence_debug_context(self, file_path: str) -> dict:
        domain = self._classify_persistence_domain(file_path)
        policy = self._persistence_policy_for_domain(domain)
        return {
            "path": str(file_path),
            "domain": domain,
            "policy": policy,
        }

    def _ensure_parent_dir(self, file_path: str) -> None:
        try:
            self._persistence_for_path(file_path).ensure_parent_dir(file_path)
        except Exception:
            parent = os.path.dirname(os.path.abspath(str(file_path)))
            if parent:
                os.makedirs(parent, exist_ok=True)

    def _read_json(self, file_path: str, default: Any) -> Any:
        try:
            return self._persistence_for_path(file_path).read_json(file_path, default)
        except Exception:
            if not self._is_runtime_state_legacy_path(file_path):
                return copy.deepcopy(default)
            return self._read_json_legacy_runtime_state_fallback(file_path, default)

    def _read_json_legacy_runtime_state_fallback(self, file_path: str, default: Any) -> Any:
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return copy.deepcopy(default)

    def _is_runtime_state_legacy_path(self, file_path: str) -> bool:
        return self._classify_persistence_domain(file_path) == "runtime_state"

    def _write_json(self, file_path: str, data: Any) -> None:
        reason = "task_runtime_write_json"
        lineage = {
            "source": "task_runtime",
            "operation": "write_json",
            "target_path": str(file_path),
        }
        provenance = {
            "source": "task_runtime",
            "operation": "write_json",
            "target_path": str(file_path),
        }
        self._assert_runtime_write_allowed(
            file_path,
            reason=reason,
            lineage=lineage,
            provenance=provenance,
        )
        try:
            self._persistence_for_path(file_path).write_json(
                file_path,
                data,
                reason=reason,
                lineage=lineage,
                provenance=provenance,
                metadata={
                    "task_runtime": True,
                    "runtime_state_persistence": True,
                },
            )
            return
        except Exception:
            domain = self._classify_persistence_domain(file_path)
            policy = self._persistence_policy_for_domain(domain)
            if not policy["allow_legacy_json_fallback"]:
                raise
            self._write_json_legacy_runtime_state_fallback(file_path, data)

    def _write_json_legacy_runtime_state_fallback(self, file_path: str, data: Any) -> None:
        """Compatibility fallback for legacy runtime_state.json artifacts only."""
        self._assert_runtime_write_allowed(
            file_path,
            reason="task_runtime_legacy_runtime_state_json_fallback",
            lineage={
                "source": "task_runtime",
                "operation": "legacy_runtime_state_json_fallback",
                "target_path": str(file_path),
            },
            provenance={
                "source": "task_runtime",
                "operation": "legacy_runtime_state_json_fallback",
                "target_path": str(file_path),
            },
        )
        target = os.path.abspath(str(file_path))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{target}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)

    def _write_json_direct(self, file_path: str, data: Any) -> None:
        self._assert_runtime_write_allowed(
            file_path,
            reason="task_runtime_direct_legacy_json_write",
            lineage={
                "source": "task_runtime",
                "operation": "direct_legacy_json_write",
                "target_path": str(file_path),
            },
            provenance={
                "source": "task_runtime",
                "operation": "direct_legacy_json_write",
                "target_path": str(file_path),
            },
        )
        if not self._is_runtime_state_legacy_path(file_path):
            raise RuntimeError("direct JSON fallback is limited to legacy runtime_state.json")
        self._write_json_legacy_runtime_state_fallback(file_path, data)

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

            trace_path = os.path.join(base_dir, self.trace_log_filename)
            trace_persistence = self._persistence_for_path(trace_path)
            trace_persistence.ensure_parent_dir(trace_path)

            record = {
                "ts": self._now(),
                "label": label,
                "payload": payload,
            }

            trace_persistence.append_text(
                trace_path,
                json.dumps(record, ensure_ascii=False) + "\n",
                reason="task_runtime_trace_append",
                lineage={
                    "source": "task_runtime",
                    "operation": "trace_append",
                    "label": str(label or ""),
                },
                provenance={
                    "source": "task_runtime",
                    "operation": "trace_append",
                    "label": str(label or ""),
                },
                metadata={"trace_log": True},
            )
        except Exception:
            pass

# ============================================================
# ZERO v8.0.0 - Autonomous Engineering Runtime metadata
# ============================================================
# This layer keeps the existing step cursor / strategy / rollback / regression
# runtime intact, and adds a durable engineering loop record:
# plan -> execute -> observe -> decide -> replan_candidate.
# It intentionally does not move orchestration back into scheduler.


def _zero_v800_safe_copy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return str(value)


def _zero_v800_normalize_engineering_session(self: TaskRuntime, value: Any = None) -> Dict[str, Any]:
    session = _zero_v800_safe_copy(value) if isinstance(value, dict) else {}

    observations = session.get("observations")
    if not isinstance(observations, list):
        observations = []

    decisions = session.get("decisions")
    if not isinstance(decisions, list):
        decisions = []

    replan_candidates = session.get("replan_candidates")
    if not isinstance(replan_candidates, list):
        replan_candidates = []

    loop_history = session.get("loop_history")
    if not isinstance(loop_history, list):
        loop_history = []

    current_cycle = self._safe_int(session.get("current_cycle"), 0)
    max_replans = self._safe_int(session.get("max_replans"), session.get("max_replan_attempts", 3))
    if max_replans < 0:
        max_replans = 0

    replan_count = self._safe_int(session.get("replan_count"), 0)
    if replan_count < 0:
        replan_count = 0

    normalized = {
        "enabled": bool(session.get("enabled", True)),
        "version": str(session.get("version") or "v8.0.0"),
        "phase": str(session.get("phase") or "planning"),
        "current_cycle": current_cycle,
        "max_replans": max_replans,
        "replan_count": replan_count,
        "last_observation": _zero_v800_safe_copy(session.get("last_observation")) if isinstance(session.get("last_observation"), dict) else {},
        "last_decision": _zero_v800_safe_copy(session.get("last_decision")) if isinstance(session.get("last_decision"), dict) else {},
        "observations": [item for item in observations if isinstance(item, dict)][-MAX_STORED_LIST_ITEMS:],
        "decisions": [item for item in decisions if isinstance(item, dict)][-MAX_STORED_LIST_ITEMS:],
        "replan_candidates": [item for item in replan_candidates if isinstance(item, dict)][-MAX_STORED_LIST_ITEMS:],
        "loop_history": [item for item in loop_history if isinstance(item, dict)][-MAX_STORED_LIST_ITEMS:],
        "exhausted": bool(session.get("exhausted", False)),
        "blocked_reason": str(session.get("blocked_reason") or ""),
    }
    return normalized


def _zero_v800_get_engineering_session(self: TaskRuntime, state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        state = {}
    session = self._normalize_engineering_session(state.get("engineering_session"))
    state["engineering_session"] = session
    return session


def _zero_v800_record_engineering_observation(
    self: TaskRuntime,
    task: Dict[str, Any],
    *,
    observation: Dict[str, Any],
    current_tick: int = 0,
) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    session = self._normalize_engineering_session(state.get("engineering_session"))

    payload = _zero_v800_safe_copy(observation if isinstance(observation, dict) else {})
    payload.setdefault("tick", current_tick)
    payload.setdefault("ts", self._now())
    payload.setdefault("cycle", self._safe_int(session.get("current_cycle"), 0))
    payload.setdefault("current_step_index", self._safe_int(state.get("current_step_index"), 0))
    payload.setdefault("status", str(state.get("status") or ""))

    observations = session.setdefault("observations", [])
    if not isinstance(observations, list):
        observations = []
    observations.append(payload)
    session["observations"] = observations[-MAX_STORED_LIST_ITEMS:]
    session["last_observation"] = payload
    session["phase"] = "observing"

    loop_history = session.setdefault("loop_history", [])
    if not isinstance(loop_history, list):
        loop_history = []
    loop_history.append({"phase": "observe", "tick": current_tick, "summary": payload.get("summary", payload.get("action", ""))})
    session["loop_history"] = loop_history[-MAX_STORED_LIST_ITEMS:]

    state["engineering_session"] = session
    state["last_observation"] = payload
    state["updated_at"] = self._now()
    state = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, state)
    return {"ok": True, "runtime_state": state, "task": copy.deepcopy(task), "observation": payload}


def _zero_v800_record_engineering_decision(
    self: TaskRuntime,
    task: Dict[str, Any],
    *,
    decision: Dict[str, Any],
    current_tick: int = 0,
) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    session = self._normalize_engineering_session(state.get("engineering_session"))

    payload = _zero_v800_safe_copy(decision if isinstance(decision, dict) else {})
    payload.setdefault("tick", current_tick)
    payload.setdefault("ts", self._now())
    payload.setdefault("cycle", self._safe_int(session.get("current_cycle"), 0))
    payload.setdefault("current_step_index", self._safe_int(state.get("current_step_index"), 0))
    payload.setdefault("status", str(state.get("status") or ""))

    decisions = session.setdefault("decisions", [])
    if not isinstance(decisions, list):
        decisions = []
    decisions.append(payload)
    session["decisions"] = decisions[-MAX_STORED_LIST_ITEMS:]
    session["last_decision"] = payload
    session["phase"] = str(payload.get("phase") or "deciding")

    if payload.get("decision") == "replan_candidate":
        session["phase"] = "replanning"
        session["replan_count"] = self._safe_int(session.get("replan_count"), 0) + 1
        if session["replan_count"] > self._safe_int(session.get("max_replans"), 3):
            session["exhausted"] = True
            session["blocked_reason"] = "engineering replan limit exhausted"

    if payload.get("decision") in {"continue", "continue_strategy", "run_next_tick"}:
        session["phase"] = "executing"
    elif payload.get("decision") in {"finish", "terminal"}:
        session["phase"] = "finished" if payload.get("decision") == "finish" else "terminal"

    loop_history = session.setdefault("loop_history", [])
    if not isinstance(loop_history, list):
        loop_history = []
    loop_history.append({"phase": "decide", "tick": current_tick, "decision": payload.get("decision", ""), "reason": payload.get("reason", "")})
    session["loop_history"] = loop_history[-MAX_STORED_LIST_ITEMS:]

    state["engineering_session"] = session
    state["last_decision"] = str(payload.get("decision") or "")
    state["last_decision_reason"] = str(payload.get("reason") or "")
    state["next_action"] = str(payload.get("next_action") or state.get("next_action") or "")
    state["updated_at"] = self._now()
    state = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, state)
    return {"ok": True, "runtime_state": state, "task": copy.deepcopy(task), "decision": payload}


def _zero_v800_create_engineering_replan_candidate(
    self: TaskRuntime,
    task: Dict[str, Any],
    *,
    reason: Any,
    failed_step: Optional[Dict[str, Any]] = None,
    failed_result: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    session = self._normalize_engineering_session(state.get("engineering_session"))

    candidate = {
        "tick": current_tick,
        "ts": self._now(),
        "cycle": self._safe_int(session.get("current_cycle"), 0),
        "reason": self._stringify_failure_message(reason),
        "failed_step": copy.deepcopy(failed_step) if isinstance(failed_step, dict) else None,
        "failed_result": self._sanitize_step_result_for_storage(failed_result if isinstance(failed_result, dict) else {}),
        "repair_context": copy.deepcopy(state.get("repair_context", {})) if isinstance(state.get("repair_context"), dict) else {},
        "repo_impact": copy.deepcopy(state.get("repair_context", {}).get("repo_impact", {})) if isinstance(state.get("repair_context"), dict) else {},
        "strategy": copy.deepcopy(state.get("repair_context", {}).get("strategy", {})) if isinstance(state.get("repair_context"), dict) else {},
        "status": str(state.get("status") or ""),
        "current_step_index": self._safe_int(state.get("current_step_index"), 0),
        "steps_total": self._safe_int(state.get("steps_total"), 0),
    }

    candidates = session.setdefault("replan_candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    candidates.append(candidate)
    session["replan_candidates"] = candidates[-MAX_STORED_LIST_ITEMS:]
    session["phase"] = "replanning"
    session["last_decision"] = {
        "decision": "replan_candidate",
        "reason": candidate["reason"],
        "tick": current_tick,
        "ts": self._now(),
    }
    state["engineering_session"] = session
    state["replan_reason"] = candidate["reason"]
    state["replanned"] = False
    state["updated_at"] = self._now()
    state = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, state)
    return {"ok": True, "runtime_state": state, "task": copy.deepcopy(task), "replan_candidate": candidate}


TaskRuntime._normalize_engineering_session = _zero_v800_normalize_engineering_session
TaskRuntime._get_engineering_session = _zero_v800_get_engineering_session
TaskRuntime.record_engineering_observation = _zero_v800_record_engineering_observation
TaskRuntime.record_engineering_decision = _zero_v800_record_engineering_decision
TaskRuntime.create_engineering_replan_candidate = _zero_v800_create_engineering_replan_candidate


# ============================================================
# AER v9.1 - Engineering Execution Coordinator Runtime
# ============================================================
# This compatibility extension intentionally stays inside TaskRuntime.  It does
# not change scheduler behavior and it does not execute replan proposals.  It
# builds a persistent coordination view under:
#   repair_context.engineering_execution
# from the already-persisted engineering_goal_state / repair_session metadata.

_ZERO_V910_ORIGINAL_NORMALIZE_REPAIR_CONTEXT_FOR_TASK = TaskRuntime._normalize_repair_context_for_task
_ZERO_V910_ORIGINAL_PREPARE_CURRENT_SUBGOAL = TaskRuntime.prepare_current_subgoal
_ZERO_V910_ORIGINAL_UPDATE_GOAL_STATE_AFTER_STEP = TaskRuntime._update_goal_state_after_step
_ZERO_V910_ORIGINAL_MARK_FAILED = TaskRuntime.mark_failed
_ZERO_V910_ORIGINAL_MARK_FINISHED = TaskRuntime.mark_finished


def _zero_v910_status_is_done(status: Any) -> bool:
    return str(status or '').strip().lower() in {'finished', 'skipped'}


def _zero_v910_normalize_engineering_execution(
    self: TaskRuntime,
    value: Any = None,
    *,
    goal_state: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source = copy.deepcopy(value) if isinstance(value, dict) else {}
    goal_state = copy.deepcopy(goal_state) if isinstance(goal_state, dict) else {}
    context = context if isinstance(context, dict) else {}

    subgoals = [copy.deepcopy(item) for item in goal_state.get('subgoals', []) if isinstance(item, dict)]
    completed = [str(item).strip() for item in goal_state.get('completed_subgoals', []) if str(item).strip()] if isinstance(goal_state.get('completed_subgoals'), list) else [
        str(item.get('subgoal_id') or '') for item in subgoals if _zero_v910_status_is_done(item.get('status'))
    ]
    completed_set = set(completed)
    failed = [str(item).strip() for item in goal_state.get('failed_subgoals', []) if str(item).strip()] if isinstance(goal_state.get('failed_subgoals'), list) else [
        str(item.get('subgoal_id') or '') for item in subgoals if str(item.get('status') or '').strip().lower() == 'failed'
    ]
    blocked = [str(item).strip() for item in goal_state.get('blocked_subgoals', []) if str(item).strip()] if isinstance(goal_state.get('blocked_subgoals'), list) else [
        str(item.get('subgoal_id') or '') for item in subgoals if str(item.get('status') or '').strip().lower() == 'blocked'
    ]

    waiting_dependencies: Dict[str, List[str]] = {}
    ready: List[str] = []
    pending: List[str] = []
    execution_order = [str(item).strip() for item in source.get('execution_order', []) if str(item).strip()] if isinstance(source.get('execution_order'), list) else []

    for subgoal in subgoals:
        subgoal_id = str(subgoal.get('subgoal_id') or '').strip()
        if not subgoal_id:
            continue
        status = str(subgoal.get('status') or 'pending').strip().lower()
        if status in {'finished', 'skipped', 'failed'}:
            if status in {'finished', 'skipped'} and subgoal_id not in execution_order:
                execution_order.append(subgoal_id)
            continue
        deps = [str(dep).strip() for dep in subgoal.get('depends_on', []) if str(dep).strip()] if isinstance(subgoal.get('depends_on'), list) else []
        missing = [dep for dep in deps if dep not in completed_set]
        if missing:
            waiting_dependencies[subgoal_id] = missing
            continue
        pending.append(subgoal_id)
        if status not in {'blocked'}:
            ready.append(subgoal_id)

    current_subgoal_id = str(goal_state.get('current_subgoal_id') or source.get('current_subgoal_id') or '').strip()
    if current_subgoal_id and current_subgoal_id not in execution_order and current_subgoal_id in completed_set:
        execution_order.append(current_subgoal_id)

    attempts = copy.deepcopy(source.get('subgoal_attempts')) if isinstance(source.get('subgoal_attempts'), dict) else {}
    retry_budget = copy.deepcopy(source.get('subgoal_retry_budget')) if isinstance(source.get('subgoal_retry_budget'), dict) else {}
    strategy_map = copy.deepcopy(source.get('subgoal_strategy_map')) if isinstance(source.get('subgoal_strategy_map'), dict) else {}
    strategy = context.get('strategy') if isinstance(context.get('strategy'), dict) else {}
    current_strategy = str(strategy.get('current_strategy') or '')

    for subgoal in subgoals:
        subgoal_id = str(subgoal.get('subgoal_id') or '').strip()
        if not subgoal_id:
            continue
        attempts[subgoal_id] = self._safe_int(attempts.get(subgoal_id), 0)
        if subgoal_id not in retry_budget:
            retry_budget[subgoal_id] = self._safe_int(subgoal.get('retry_budget'), 1)
        if current_strategy and subgoal_id not in strategy_map:
            strategy_map[subgoal_id] = current_strategy

    status = str(source.get('status') or goal_state.get('status') or 'running').strip().lower()
    if status not in {'running', 'finished', 'failed', 'blocked', 'waiting'}:
        status = 'running'
    if failed:
        status = 'failed'
    elif ready:
        status = 'running'
    elif waiting_dependencies or blocked:
        status = 'blocked'
    elif subgoals and len(completed_set) >= len(subgoals):
        status = 'finished'

    summary = {
        'total_subgoals': len(subgoals),
        'ready_subgoals': len(ready),
        'completed_subgoals': len(completed),
        'failed_subgoals': len(failed),
        'blocked_subgoals': len(blocked),
        'waiting_dependency_subgoals': len(waiting_dependencies),
        'current_subgoal_id': current_subgoal_id,
        'status': status,
    }

    return {
        'status': status,
        'current_subgoal_id': current_subgoal_id,
        'active_subgoal_queue': ready[-MAX_STORED_LIST_ITEMS:],
        'pending_subgoals': pending[-MAX_STORED_LIST_ITEMS:],
        'completed_subgoals': completed[-MAX_STORED_LIST_ITEMS:],
        'failed_subgoals': failed[-MAX_STORED_LIST_ITEMS:],
        'blocked_subgoals': blocked[-MAX_STORED_LIST_ITEMS:],
        'waiting_dependencies': dict(list(waiting_dependencies.items())[-MAX_STORED_LIST_ITEMS:]),
        'execution_order': execution_order[-MAX_STORED_LIST_ITEMS:],
        'subgoal_attempts': attempts,
        'subgoal_retry_budget': retry_budget,
        'subgoal_strategy_map': strategy_map,
        'last_selected_subgoal_id': str(source.get('last_selected_subgoal_id') or ''),
        'last_selection_reason': self._truncate_text(source.get('last_selection_reason') or '', 300),
        'summary': summary,
    }


def _zero_v910_refresh_engineering_execution(
    self: TaskRuntime,
    context: Dict[str, Any],
    *,
    selected_subgoal_id: str = '',
    selection_reason: str = '',
    increment_attempt: bool = False,
) -> Dict[str, Any]:
    if not isinstance(context, dict):
        context = {}
    goal_state = context.get('engineering_goal_state') if isinstance(context.get('engineering_goal_state'), dict) else {}
    current = context.get('engineering_execution') if isinstance(context.get('engineering_execution'), dict) else {}
    execution = self._normalize_engineering_execution(current, goal_state=goal_state, context=context)
    selected_subgoal_id = str(selected_subgoal_id or '').strip()
    if selected_subgoal_id:
        execution['current_subgoal_id'] = selected_subgoal_id
        execution['last_selected_subgoal_id'] = selected_subgoal_id
        execution['last_selection_reason'] = self._truncate_text(selection_reason or 'selected runnable subgoal', 300)
        if selected_subgoal_id not in execution.get('execution_order', []):
            execution.setdefault('execution_order', []).append(selected_subgoal_id)
        if increment_attempt:
            attempts = execution.setdefault('subgoal_attempts', {})
            attempts[selected_subgoal_id] = self._safe_int(attempts.get(selected_subgoal_id), 0) + 1
        strategy = context.get('strategy') if isinstance(context.get('strategy'), dict) else {}
        current_strategy = str(strategy.get('current_strategy') or '')
        if current_strategy:
            execution.setdefault('subgoal_strategy_map', {})[selected_subgoal_id] = current_strategy
    context['engineering_execution'] = execution
    return context


def _zero_v910_first_step_index_for_subgoal(self: TaskRuntime, subgoal: Dict[str, Any], steps: List[Any]) -> int:
    indices = self._subgoal_step_indices(subgoal, steps)
    return indices[0] if indices else -1


def _zero_v910_find_ready_subgoal(self: TaskRuntime, goal_state: Dict[str, Any], steps: List[Any], *, exclude: str = '') -> Dict[str, Any]:
    completed = set(goal_state.get('completed_subgoals', [])) if isinstance(goal_state.get('completed_subgoals'), list) else set()
    candidates = [item for item in goal_state.get('subgoals', []) if isinstance(item, dict)] if isinstance(goal_state.get('subgoals'), list) else []
    for subgoal in candidates:
        subgoal_id = str(subgoal.get('subgoal_id') or '').strip()
        if not subgoal_id or subgoal_id == exclude:
            continue
        status = str(subgoal.get('status') or 'pending').strip().lower()
        if status in {'finished', 'skipped', 'failed', 'blocked'}:
            continue
        deps = [str(dep).strip() for dep in subgoal.get('depends_on', []) if str(dep).strip()] if isinstance(subgoal.get('depends_on'), list) else []
        if any(dep not in completed for dep in deps):
            continue
        if self._zero_v910_first_step_index_for_subgoal(subgoal, steps) < 0:
            continue
        return subgoal
    return {}


def _zero_v910_normalize_repair_context_for_task(self: TaskRuntime, value: Any, *, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    context = _ZERO_V910_ORIGINAL_NORMALIZE_REPAIR_CONTEXT_FOR_TASK(self, value, task=task, state=state)
    context = self._zero_v910_refresh_engineering_execution(context)
    return context


def _zero_v910_prepare_current_subgoal(self: TaskRuntime, task: Dict[str, Any], *, current_tick: int = 0) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    state = self._sync_steps_from_task(task, state)
    state = self._sync_loop_fields_from_task(task, state)
    context = self._normalize_repair_context_for_task(state.get('repair_context'), task=task, state=state)
    goal_state = context.get('engineering_goal_state') if isinstance(context.get('engineering_goal_state'), dict) else {}
    steps = state.get('steps') if isinstance(state.get('steps'), list) else []
    idx = self._safe_int(state.get('current_step_index'), 0)
    subgoal = self._subgoal_for_step_index(goal_state, steps, idx)
    subgoal_id = str(subgoal.get('subgoal_id') or '') if isinstance(subgoal, dict) else ''
    completed = set(goal_state.get('completed_subgoals', [])) if isinstance(goal_state.get('completed_subgoals'), list) else set()
    missing = [dep for dep in subgoal.get('depends_on', []) if dep not in completed] if isinstance(subgoal, dict) and isinstance(subgoal.get('depends_on'), list) else []

    if subgoal_id and missing:
        reason = f"subgoal dependency unmet: {', '.join(missing)}"
        self._set_subgoal_status(goal_state, subgoal_id, 'blocked', reason=reason)
        ready = self._zero_v910_find_ready_subgoal(goal_state, steps, exclude=subgoal_id)
        if ready:
            ready_id = str(ready.get('subgoal_id') or '')
            ready_index = self._zero_v910_first_step_index_for_subgoal(ready, steps)
            self._set_subgoal_status(goal_state, ready_id, 'running')
            goal_state['current_subgoal_id'] = ready_id
            goal_state['status'] = 'running'
            context['engineering_goal_state'] = self._refresh_goal_state_summary(goal_state)
            context = self._zero_v910_refresh_engineering_execution(
                context,
                selected_subgoal_id=ready_id,
                selection_reason=f'skipped blocked subgoal {subgoal_id}; selected ready subgoal',
                increment_attempt=True,
            )
            state['repair_context'] = context
            state['current_step_index'] = ready_index
            state['status'] = 'running'
            state['last_error'] = ''
            state['updated_at'] = self._now()
            state = self.save_runtime_state(task, state)
            self._sync_task_from_runtime_state(task, state)
            return {'ok': True, 'status': 'running', 'runtime_state': state, 'task': copy.deepcopy(task), 'selected_subgoal_id': ready_id, 'skipped_blocked_subgoal_id': subgoal_id}

    result = _ZERO_V910_ORIGINAL_PREPARE_CURRENT_SUBGOAL(self, task, current_tick=current_tick)
    result_state = result.get('runtime_state') if isinstance(result, dict) and isinstance(result.get('runtime_state'), dict) else self.load_runtime_state(task)
    result_context = result_state.get('repair_context') if isinstance(result_state.get('repair_context'), dict) else {}
    selected = str((result_context.get('engineering_goal_state') if isinstance(result_context.get('engineering_goal_state'), dict) else {}).get('current_subgoal_id') or '')
    if result_context:
        before_status = ''
        for item in (result_context.get('engineering_goal_state') or {}).get('subgoals', []) if isinstance((result_context.get('engineering_goal_state') or {}).get('subgoals'), list) else []:
            if isinstance(item, dict) and item.get('subgoal_id') == selected:
                before_status = str(item.get('status') or '')
                break
        result_context = self._zero_v910_refresh_engineering_execution(
            result_context,
            selected_subgoal_id=selected,
            selection_reason='prepared current subgoal',
            increment_attempt=bool(selected and before_status == 'running'),
        )
        result_state['repair_context'] = result_context
        result_state = self.save_runtime_state(task, result_state)
        self._sync_task_from_runtime_state(task, result_state)
        if isinstance(result, dict):
            result['runtime_state'] = result_state
            result['task'] = copy.deepcopy(task)
    return result


def _zero_v910_update_goal_state_after_step(self: TaskRuntime, *, context: Dict[str, Any], state: Dict[str, Any], step_index: int, step_result: Dict[str, Any], failed: bool, current_tick: int = 0) -> None:
    _ZERO_V910_ORIGINAL_UPDATE_GOAL_STATE_AFTER_STEP(
        self,
        context=context,
        state=state,
        step_index=step_index,
        step_result=step_result,
        failed=failed,
        current_tick=current_tick,
    )
    subgoal_id = ''
    goal_state = context.get('engineering_goal_state') if isinstance(context.get('engineering_goal_state'), dict) else {}
    subgoal = self._subgoal_for_step_index(goal_state, state.get('steps') if isinstance(state.get('steps'), list) else [], step_index)
    if isinstance(subgoal, dict):
        subgoal_id = str(subgoal.get('subgoal_id') or '')
    self._zero_v910_refresh_engineering_execution(
        context,
        selected_subgoal_id=subgoal_id,
        selection_reason='updated after step failure' if failed else 'updated after step success',
        increment_attempt=False,
    )


def _zero_v910_mark_failed(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, failure_type: str = DEFAULT_FAILURE_TYPE, failure_message: str = '') -> Dict[str, Any]:
    result = _ZERO_V910_ORIGINAL_MARK_FAILED(self, task, current_tick=current_tick, failure_type=failure_type, failure_message=failure_message)
    state = result.get('runtime_state') if isinstance(result, dict) and isinstance(result.get('runtime_state'), dict) else self.load_runtime_state(task)
    context = state.get('repair_context') if isinstance(state.get('repair_context'), dict) else {}
    context = self._zero_v910_refresh_engineering_execution(context, selection_reason='task failed')
    state['repair_context'] = context
    state = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, state)
    if isinstance(result, dict):
        result['runtime_state'] = state
        result['task'] = copy.deepcopy(task)
    return result


def _zero_v910_mark_finished(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, final_answer: str = '', final_result: Optional[Dict[str, Any]] = None, completion_authority: Any = None) -> Dict[str, Any]:
    result = _ZERO_V910_ORIGINAL_MARK_FINISHED(self, task, current_tick=current_tick, final_answer=final_answer, final_result=final_result, completion_authority=completion_authority)
    state = result.get('runtime_state') if isinstance(result, dict) and isinstance(result.get('runtime_state'), dict) else self.load_runtime_state(task)
    context = state.get('repair_context') if isinstance(state.get('repair_context'), dict) else {}
    context = self._zero_v910_refresh_engineering_execution(context, selection_reason='task finished')
    state['repair_context'] = context
    state = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, state)
    if isinstance(result, dict):
        result['runtime_state'] = state
        result['task'] = copy.deepcopy(task)
    return result


TaskRuntime._normalize_engineering_execution = _zero_v910_normalize_engineering_execution
TaskRuntime._zero_v910_refresh_engineering_execution = _zero_v910_refresh_engineering_execution
TaskRuntime._zero_v910_first_step_index_for_subgoal = _zero_v910_first_step_index_for_subgoal
TaskRuntime._zero_v910_find_ready_subgoal = _zero_v910_find_ready_subgoal
TaskRuntime._normalize_repair_context_for_task = _zero_v910_normalize_repair_context_for_task
TaskRuntime.prepare_current_subgoal = _zero_v910_prepare_current_subgoal
TaskRuntime._update_goal_state_after_step = _zero_v910_update_goal_state_after_step
TaskRuntime.mark_failed = _zero_v910_mark_failed
TaskRuntime.mark_finished = _zero_v910_mark_finished


# ============================================================
# AER v9.1.2 - Force Engineering Execution Action Landing
# ============================================================
# v9.1 created the engineering_execution coordinator view, but legacy repair
# tasks can still finish without visible pending/current/completed action fields
# if the action state is not forced during normalization/save.  This extension
# keeps the logic runtime-local: no scheduler, UI, app.py, docs, or planner
# coupling.  It derives a compact action view from persisted steps + execution
# log and writes it under:
#   repair_context.engineering_execution

_ZERO_V912_ORIGINAL_NORMALIZE_REPAIR_CONTEXT_FOR_TASK = TaskRuntime._normalize_repair_context_for_task
_ZERO_V912_ORIGINAL_SAVE_RUNTIME_STATE = TaskRuntime.save_runtime_state
_ZERO_V912_ORIGINAL_ADVANCE_STEP = TaskRuntime.advance_step
_ZERO_V912_ORIGINAL_RECORD_STEP_FAILURE = TaskRuntime.record_step_failure
_ZERO_V912_ORIGINAL_MARK_FAILED = TaskRuntime.mark_failed
_ZERO_V912_ORIGINAL_MARK_FINISHED = TaskRuntime.mark_finished


def _zero_v912_slug(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    if not text:
        text = str(fallback or '').strip()
    safe = []
    for ch in text:
        safe.append(ch if ch.isalnum() or ch in {'_', '-'} else '_')
    return ''.join(safe).strip('_') or 'item'


def _zero_v912_step_action_from_step(
    self: TaskRuntime,
    *,
    step: Any,
    step_index: int,
    status: str,
    tick: int = 0,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    step_dict = step if isinstance(step, dict) else {}
    step_type = str(step_dict.get('type') or '').strip()
    step_id = str(step_dict.get('id') or '').strip()
    target_path = str(step_dict.get('target_path') or step_dict.get('path') or '').strip()
    action_id = f"action_{step_index}_{_zero_v912_slug(step_id or step_type, 'step')}"
    message = ''
    error = ''
    ok_value: Any = None
    if isinstance(result, dict):
        ok_value = result.get('ok')
        message = str(result.get('message') or result.get('final_answer') or '')
        raw_error = result.get('error')
        if isinstance(raw_error, dict):
            error = str(raw_error.get('message') or raw_error.get('type') or '')
        else:
            error = str(raw_error or '')
        payload = result.get('result') if isinstance(result.get('result'), dict) else {}
        if not message and isinstance(payload, dict):
            message = str(payload.get('message') or payload.get('final_answer') or '')
    action = {
        'action_id': action_id,
        'step_index': int(step_index),
        'step_id': step_id,
        'step_type': step_type,
        'target_path': target_path,
        'status': str(status or 'pending'),
        'tick': int(tick or 0),
        'requires_confirmation': bool(step_dict.get('requires_confirmation', False)),
        'risk_level': str(step_dict.get('risk_level') or ''),
        'summary': self._truncate_text(message or step_type or action_id, 500),
    }
    if ok_value is not None:
        action['ok'] = bool(ok_value)
    if error:
        action['error'] = self._truncate_text(error, 500)
    return action


def _zero_v912_execution_log_by_step(execution_log: Any) -> Dict[int, Dict[str, Any]]:
    by_step: Dict[int, Dict[str, Any]] = {}
    if not isinstance(execution_log, list):
        return by_step
    for record in execution_log:
        if not isinstance(record, dict):
            continue
        try:
            idx = int(record.get('step_index', -1))
        except Exception:
            continue
        if idx < 0:
            continue
        by_step[idx] = record
    return by_step


def _zero_v912_step_is_continue_observation(step: Any, result_payload: Any) -> bool:
    step_dict = step if isinstance(step, dict) else {}
    if bool(step_dict.get('continue_on_failure', False)):
        return True
    if isinstance(result_payload, dict) and bool(result_payload.get('continued_after_failure', False)):
        return True
    return False


def _zero_v912_force_engineering_action_landing(
    self: TaskRuntime,
    *,
    context: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(context, dict):
        context = {}
    state = state if isinstance(state, dict) else {}
    task = task if isinstance(task, dict) else {}

    existing = context.get('engineering_execution') if isinstance(context.get('engineering_execution'), dict) else {}
    goal_state = context.get('engineering_goal_state') if isinstance(context.get('engineering_goal_state'), dict) else {}
    try:
        execution = self._normalize_engineering_execution(existing, goal_state=goal_state, context=context)
    except Exception:
        execution = copy.deepcopy(existing) if isinstance(existing, dict) else {}

    steps = state.get('steps') if isinstance(state.get('steps'), list) else task.get('steps') if isinstance(task.get('steps'), list) else []
    if not isinstance(steps, list):
        steps = []
    current_idx = self._safe_int(state.get('current_step_index'), self._safe_int(task.get('current_step_index'), 0))
    status = str(state.get('status') or task.get('status') or '').strip().lower()
    execution_log = state.get('execution_log') if isinstance(state.get('execution_log'), list) else []
    log_by_step = _zero_v912_execution_log_by_step(execution_log)

    pending_actions: List[Dict[str, Any]] = []
    completed_actions: List[Dict[str, Any]] = []
    failed_actions: List[Dict[str, Any]] = []
    blocked_actions: List[Dict[str, Any]] = []
    current_action: Dict[str, Any] = {}

    for idx, step in enumerate(steps):
        record = log_by_step.get(idx)
        result_payload = record.get('result') if isinstance(record, dict) and isinstance(record.get('result'), dict) else {}
        tick = self._safe_int(record.get('tick'), 0) if isinstance(record, dict) else 0
        if idx in log_by_step:
            ok = bool(result_payload.get('ok', False))
            if ok or _zero_v912_step_is_continue_observation(step, result_payload):
                action_status = 'completed' if ok else 'observed_failure_continued'
                completed_actions.append(self._zero_v912_step_action_from_step(
                    step=step,
                    step_index=idx,
                    status=action_status,
                    tick=tick,
                    result=result_payload,
                ))
            else:
                failed_actions.append(self._zero_v912_step_action_from_step(
                    step=step,
                    step_index=idx,
                    status='failed',
                    tick=tick,
                    result=result_payload,
                ))
            continue

        if idx < current_idx:
            completed_actions.append(self._zero_v912_step_action_from_step(
                step=step,
                step_index=idx,
                status='completed_unlogged',
                tick=0,
                result=None,
            ))
        elif idx == current_idx and status not in TERMINAL_STATUSES:
            current_action = self._zero_v912_step_action_from_step(
                step=step,
                step_index=idx,
                status='current',
                tick=self._safe_int(state.get('last_run_tick'), 0),
                result=None,
            )
            pending_actions.append(copy.deepcopy(current_action))
        elif idx >= current_idx and status not in TERMINAL_STATUSES:
            pending_actions.append(self._zero_v912_step_action_from_step(
                step=step,
                step_index=idx,
                status='pending',
                tick=0,
                result=None,
            ))

    active_blockers = state.get('blockers') if isinstance(state.get('blockers'), list) else []
    if active_blockers and status in {'blocked', 'waiting_blocker', 'waiting_review', 'waiting'}:
        for item in active_blockers[-MAX_STORED_LIST_ITEMS:]:
            if isinstance(item, dict):
                blocked_actions.append({
                    'action_id': f"blocker_{_zero_v912_slug(item.get('id') or item.get('type') or 'blocked')}",
                    'status': 'blocked',
                    'reason': self._truncate_text(item.get('reason') or item.get('message') or '', 500),
                    'type': str(item.get('type') or ''),
                })

    if status in TERMINAL_STATUSES:
        pending_actions = []
        current_action = {}

    execution['pending_actions'] = pending_actions[-MAX_STORED_LIST_ITEMS:]
    execution['current_action'] = current_action
    execution['completed_actions'] = completed_actions[-MAX_STORED_LIST_ITEMS:]
    execution['failed_actions'] = failed_actions[-MAX_STORED_LIST_ITEMS:]
    execution['blocked_actions'] = blocked_actions[-MAX_STORED_LIST_ITEMS:]
    execution['action_status'] = {
        'pending': len(pending_actions),
        'completed': len(completed_actions),
        'failed': len(failed_actions),
        'blocked': len(blocked_actions),
        'current_action_id': str(current_action.get('action_id') or ''),
    }
    execution['action_landing_version'] = 'aer_v9_1_2'
    execution['last_action_landing_at'] = self._now()
    context['engineering_execution'] = execution
    return context


def _zero_v912_normalize_repair_context_for_task(self: TaskRuntime, value: Any, *, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    context = _ZERO_V912_ORIGINAL_NORMALIZE_REPAIR_CONTEXT_FOR_TASK(self, value, task=task, state=state)
    context = self._zero_v912_force_engineering_action_landing(context=context, state=state, task=task)
    return context


def _zero_v912_save_runtime_state(self: TaskRuntime, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(state, dict):
        context = state.get('repair_context') if isinstance(state.get('repair_context'), dict) else {}
        context = self._zero_v912_force_engineering_action_landing(context=context, state=state, task=task)
        state = copy.deepcopy(state)
        state['repair_context'] = context
    saved = _ZERO_V912_ORIGINAL_SAVE_RUNTIME_STATE(self, task, state)
    return saved


def _zero_v912_resave_with_actions(self: TaskRuntime, task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    state = result.get('runtime_state') if isinstance(result.get('runtime_state'), dict) else None
    if not isinstance(state, dict):
        try:
            state = self.load_runtime_state(task)
        except Exception:
            state = None
    if isinstance(state, dict):
        context = state.get('repair_context') if isinstance(state.get('repair_context'), dict) else {}
        context = self._zero_v912_force_engineering_action_landing(context=context, state=state, task=task)
        state['repair_context'] = context
        state = self.save_runtime_state(task, state)
        self._sync_task_from_runtime_state(task, state)
        result['runtime_state'] = state
        result['task'] = copy.deepcopy(task)
    return result


def _zero_v912_advance_step(self: TaskRuntime, task: Dict[str, Any], step_result: Optional[Dict[str, Any]] = None, current_tick: int = 0) -> Dict[str, Any]:
    result = _ZERO_V912_ORIGINAL_ADVANCE_STEP(self, task, step_result=step_result, current_tick=current_tick)
    return self._zero_v912_resave_with_actions(task, result)


def _zero_v912_record_step_failure(self: TaskRuntime, task: Dict[str, Any], step: Optional[Dict[str, Any]] = None, step_result: Optional[Dict[str, Any]] = None, current_tick: int = 0, status: str = 'running') -> Dict[str, Any]:
    result = _ZERO_V912_ORIGINAL_RECORD_STEP_FAILURE(self, task, step=step, step_result=step_result, current_tick=current_tick, status=status)
    return self._zero_v912_resave_with_actions(task, result)


def _zero_v912_mark_failed(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, failure_type: str = DEFAULT_FAILURE_TYPE, failure_message: str = '') -> Dict[str, Any]:
    result = _ZERO_V912_ORIGINAL_MARK_FAILED(self, task, current_tick=current_tick, failure_type=failure_type, failure_message=failure_message)
    return self._zero_v912_resave_with_actions(task, result)


def _zero_v912_mark_finished(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, final_answer: str = '', final_result: Optional[Dict[str, Any]] = None, completion_authority: Any = None) -> Dict[str, Any]:
    result = _ZERO_V912_ORIGINAL_MARK_FINISHED(self, task, current_tick=current_tick, final_answer=final_answer, final_result=final_result, completion_authority=completion_authority)
    return self._zero_v912_resave_with_actions(task, result)


TaskRuntime._zero_v912_step_action_from_step = _zero_v912_step_action_from_step
TaskRuntime._zero_v912_force_engineering_action_landing = _zero_v912_force_engineering_action_landing
TaskRuntime._zero_v912_resave_with_actions = _zero_v912_resave_with_actions
TaskRuntime._normalize_repair_context_for_task = _zero_v912_normalize_repair_context_for_task
TaskRuntime.save_runtime_state = _zero_v912_save_runtime_state
TaskRuntime.advance_step = _zero_v912_advance_step
TaskRuntime.record_step_failure = _zero_v912_record_step_failure
TaskRuntime.mark_failed = _zero_v912_mark_failed
TaskRuntime.mark_finished = _zero_v912_mark_finished


# ============================================================
# AER v9.1.3 - Engineering Action Runtime API Layer
# ============================================================
# v9.1.2 forced the derived engineering_execution action view to land in
# runtime_state.json, but runners that call the runtime through explicit action
# APIs still need stable public methods.  This layer intentionally stays inside
# TaskRuntime so callers can use:
#   update_current_engineering_action
#   complete_engineering_action
#   fail_engineering_action
#   block_engineering_action
#   record_rollback_restore_action
# without coupling scheduler / runner / app.py to repair_context internals.

_ZERO_V913_ORIGINAL_FORCE_ENGINEERING_ACTION_LANDING = TaskRuntime._zero_v912_force_engineering_action_landing


def _zero_v913_safe_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _zero_v913_normalize_api_action(
    self: TaskRuntime,
    action: Any = None,
    *,
    state: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
    status: str = "current",
    current_tick: int = 0,
    result: Optional[Dict[str, Any]] = None,
    error: Any = None,
    reason: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    state = state if isinstance(state, dict) else {}
    task = task if isinstance(task, dict) else {}
    payload = _zero_v913_safe_dict(action)
    payload.update({key: copy.deepcopy(value) for key, value in kwargs.items() if value is not None})

    step_index = self._safe_int(
        payload.get("step_index"),
        self._safe_int(state.get("current_step_index"), self._safe_int(task.get("current_step_index"), 0)),
    )
    steps = state.get("steps") if isinstance(state.get("steps"), list) else task.get("steps") if isinstance(task.get("steps"), list) else []
    current_step = steps[step_index] if isinstance(steps, list) and 0 <= step_index < len(steps) else {}

    base = self._zero_v912_step_action_from_step(
        step=current_step if isinstance(current_step, dict) else {},
        step_index=step_index,
        status=status,
        tick=current_tick,
        result=result if isinstance(result, dict) else None,
    )
    base.update(payload)
    base["status"] = str(status or base.get("status") or "current")
    base["step_index"] = step_index
    base["tick"] = self._safe_int(base.get("tick"), current_tick)
    base["ts"] = str(base.get("ts") or self._now())
    base["source"] = str(base.get("source") or "task_runtime_api")

    action_id = str(base.get("action_id") or "").strip()
    if not action_id:
        step_id = str(base.get("step_id") or "").strip()
        step_type = str(base.get("step_type") or base.get("type") or "action").strip()
        action_id = f"action_{step_index}_{_zero_v912_slug(step_id or step_type, 'api')}"
    base["action_id"] = action_id

    if reason:
        base["reason"] = self._truncate_text(reason, 500)
    if error is not None:
        base["error"] = self._truncate_text(self._stringify_failure_message(error), 500)
    if isinstance(result, dict):
        base["result"] = self._sanitize_step_result_for_storage(result)
    return self._make_storage_safe(base)


def _zero_v913_upsert_action(items: Any, action: Dict[str, Any], *, limit: int = MAX_STORED_LIST_ITEMS) -> List[Dict[str, Any]]:
    existing = [copy.deepcopy(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    action_id = str(action.get("action_id") or "").strip()
    replaced = False
    merged: List[Dict[str, Any]] = []
    for item in existing:
        if action_id and str(item.get("action_id") or "") == action_id:
            merged.append(copy.deepcopy(action))
            replaced = True
        else:
            merged.append(item)
    if not replaced:
        merged.append(copy.deepcopy(action))
    return merged[-max(1, int(limit)):]


def _zero_v913_remove_action(items: Any, action_id: str) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    target = str(action_id or "").strip()
    if not target:
        return [copy.deepcopy(item) for item in items if isinstance(item, dict)]
    return [copy.deepcopy(item) for item in items if isinstance(item, dict) and str(item.get("action_id") or "") != target]


def _zero_v913_api_bucket(execution: Dict[str, Any]) -> Dict[str, Any]:
    bucket = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}
    for key in ("current", "completed", "failed", "blocked", "rollback"):
        if key == "current":
            if not isinstance(bucket.get(key), dict):
                bucket[key] = {}
        elif not isinstance(bucket.get(key), list):
            bucket[key] = []
    execution["api_actions"] = bucket
    return bucket


def _zero_v913_merge_api_actions_into_execution(self: TaskRuntime, execution: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(execution, dict):
        execution = {}
    bucket = _zero_v913_api_bucket(execution)

    current = bucket.get("current") if isinstance(bucket.get("current"), dict) else {}
    if current:
        execution["current_action"] = copy.deepcopy(current)
        execution["pending_actions"] = _zero_v913_upsert_action(execution.get("pending_actions"), current)

    for bucket_name, target_name in (
        ("completed", "completed_actions"),
        ("failed", "failed_actions"),
        ("blocked", "blocked_actions"),
        ("rollback", "rollback_actions"),
    ):
        target = execution.get(target_name)
        if not isinstance(target, list):
            target = []
        for action in bucket.get(bucket_name, []) if isinstance(bucket.get(bucket_name), list) else []:
            if isinstance(action, dict):
                target = _zero_v913_upsert_action(target, action)
                action_id = str(action.get("action_id") or "")
                if bucket_name in {"completed", "failed", "blocked"}:
                    execution["pending_actions"] = _zero_v913_remove_action(execution.get("pending_actions"), action_id)
        execution[target_name] = target[-MAX_STORED_LIST_ITEMS:]

    pending = execution.get("pending_actions") if isinstance(execution.get("pending_actions"), list) else []
    completed = execution.get("completed_actions") if isinstance(execution.get("completed_actions"), list) else []
    failed = execution.get("failed_actions") if isinstance(execution.get("failed_actions"), list) else []
    blocked = execution.get("blocked_actions") if isinstance(execution.get("blocked_actions"), list) else []
    current_action = execution.get("current_action") if isinstance(execution.get("current_action"), dict) else {}
    execution["action_status"] = {
        "pending": len(pending),
        "completed": len(completed),
        "failed": len(failed),
        "blocked": len(blocked),
        "rollback": len(execution.get("rollback_actions", [])) if isinstance(execution.get("rollback_actions"), list) else 0,
        "current_action_id": str(current_action.get("action_id") or ""),
    }
    execution["runtime_api_layer"] = "aer_v9_1_3"
    execution["last_runtime_api_merge_at"] = self._now()
    return execution


def _zero_v913_force_engineering_action_landing(
    self: TaskRuntime,
    *,
    context: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = _ZERO_V913_ORIGINAL_FORCE_ENGINEERING_ACTION_LANDING(self, context=context, state=state, task=task)
    execution = context.get("engineering_execution") if isinstance(context.get("engineering_execution"), dict) else {}
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    return context


def _zero_v913_load_action_context(self: TaskRuntime, task: Dict[str, Any]) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    context = state.get("repair_context") if isinstance(state.get("repair_context"), dict) else {}
    context = self._zero_v912_force_engineering_action_landing(context=context, state=state, task=task)
    execution = context.get("engineering_execution") if isinstance(context.get("engineering_execution"), dict) else {}
    _zero_v913_api_bucket(execution)
    context["engineering_execution"] = execution
    state["repair_context"] = context
    return {"state": state, "context": context, "execution": execution}


def _zero_v913_save_action_context(
    self: TaskRuntime,
    task: Dict[str, Any],
    state: Dict[str, Any],
    context: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    state = copy.deepcopy(state if isinstance(state, dict) else {})
    context = self._zero_v912_force_engineering_action_landing(context=context, state=state, task=task)
    state["repair_context"] = context
    state["updated_at"] = self._now()
    saved = self.save_runtime_state(task, state)
    self._sync_task_from_runtime_state(task, saved)
    return {
        "ok": True,
        "status": saved.get("status", "running"),
        "task": copy.deepcopy(task),
        "runtime_state": saved,
        "engineering_action": copy.deepcopy(action),
        "engineering_execution": copy.deepcopy(saved.get("repair_context", {}).get("engineering_execution", {})) if isinstance(saved.get("repair_context"), dict) else {},
    }


def _zero_v913_update_current_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v913_load_action_context(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    bucket = _zero_v913_api_bucket(execution)

    current = self._zero_v913_normalize_api_action(
        action,
        state=state,
        task=task,
        status=str(kwargs.pop("status", "current") or "current"),
        current_tick=current_tick,
        **kwargs,
    )
    bucket["current"] = current
    execution["api_actions"] = bucket
    execution["current_action"] = copy.deepcopy(current)
    execution["pending_actions"] = _zero_v913_upsert_action(execution.get("pending_actions"), current)
    execution["last_api_action_event"] = "update_current"
    execution["last_api_action_at"] = self._now()
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    return self._zero_v913_save_action_context(task, state, context, current)


def _zero_v913_complete_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v913_load_action_context(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    bucket = _zero_v913_api_bucket(execution)
    source_action = action if isinstance(action, dict) and action else bucket.get("current")
    completed = self._zero_v913_normalize_api_action(
        source_action,
        state=state,
        task=task,
        status="completed",
        current_tick=current_tick,
        result=result,
        **kwargs,
    )
    action_id = str(completed.get("action_id") or "")
    bucket["completed"] = _zero_v913_upsert_action(bucket.get("completed"), completed)
    if isinstance(bucket.get("current"), dict) and str(bucket["current"].get("action_id") or "") == action_id:
        bucket["current"] = {}
    execution["api_actions"] = bucket
    execution["pending_actions"] = _zero_v913_remove_action(execution.get("pending_actions"), action_id)
    execution["completed_actions"] = _zero_v913_upsert_action(execution.get("completed_actions"), completed)
    if isinstance(execution.get("current_action"), dict) and str(execution["current_action"].get("action_id") or "") == action_id:
        execution["current_action"] = {}
    execution["last_completed_action"] = copy.deepcopy(completed)
    execution["last_api_action_event"] = "complete"
    execution["last_api_action_at"] = self._now()
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    return self._zero_v913_save_action_context(task, state, context, completed)


def _zero_v913_fail_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    error: Any = None,
    reason: str = "",
    result: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v913_load_action_context(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    bucket = _zero_v913_api_bucket(execution)
    source_action = action if isinstance(action, dict) and action else bucket.get("current")
    failed = self._zero_v913_normalize_api_action(
        source_action,
        state=state,
        task=task,
        status="failed",
        current_tick=current_tick,
        result=result,
        error=error,
        reason=reason,
        **kwargs,
    )
    action_id = str(failed.get("action_id") or "")
    bucket["failed"] = _zero_v913_upsert_action(bucket.get("failed"), failed)
    if isinstance(bucket.get("current"), dict) and str(bucket["current"].get("action_id") or "") == action_id:
        bucket["current"] = {}
    execution["api_actions"] = bucket
    execution["pending_actions"] = _zero_v913_remove_action(execution.get("pending_actions"), action_id)
    execution["failed_actions"] = _zero_v913_upsert_action(execution.get("failed_actions"), failed)
    if isinstance(execution.get("current_action"), dict) and str(execution["current_action"].get("action_id") or "") == action_id:
        execution["current_action"] = {}
    execution["last_failed_action"] = copy.deepcopy(failed)
    execution["last_api_action_event"] = "fail"
    execution["last_api_action_at"] = self._now()
    if error is not None or reason:
        state["last_error"] = self._truncate_text(reason or self._stringify_failure_message(error), 500)
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    saved_result = self._zero_v913_save_action_context(task, state, context, failed)
    saved_result["ok"] = False
    return saved_result


def _zero_v913_block_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    blocker: Optional[Dict[str, Any]] = None,
    reason: str = "",
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v913_load_action_context(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    bucket = _zero_v913_api_bucket(execution)
    block_reason = reason or (str(blocker.get("reason") or "") if isinstance(blocker, dict) else "")
    blocked = self._zero_v913_normalize_api_action(
        action if isinstance(action, dict) and action else bucket.get("current"),
        state=state,
        task=task,
        status="blocked",
        current_tick=current_tick,
        reason=block_reason,
        **kwargs,
    )
    if isinstance(blocker, dict):
        blocked["blocker"] = self._make_storage_safe(blocker)
    action_id = str(blocked.get("action_id") or "")
    bucket["blocked"] = _zero_v913_upsert_action(bucket.get("blocked"), blocked)
    execution["api_actions"] = bucket
    execution["pending_actions"] = _zero_v913_remove_action(execution.get("pending_actions"), action_id)
    execution["blocked_actions"] = _zero_v913_upsert_action(execution.get("blocked_actions"), blocked)
    execution["last_blocked_action"] = copy.deepcopy(blocked)
    execution["last_api_action_event"] = "block"
    execution["last_api_action_at"] = self._now()
    state["waiting_reason"] = block_reason
    if str(state.get("status") or "") not in TERMINAL_STATUSES:
        state["status"] = "blocked"
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    return self._zero_v913_save_action_context(task, state, context, blocked)


def _zero_v913_record_rollback_restore_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    rollback: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v913_load_action_context(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    bucket = _zero_v913_api_bucket(execution)
    rollback_action = self._zero_v913_normalize_api_action(
        action,
        state=state,
        task=task,
        status="rollback_restored",
        current_tick=current_tick,
        result=rollback if isinstance(rollback, dict) else None,
        **kwargs,
    )
    if isinstance(rollback, dict):
        rollback_action["rollback"] = self._make_storage_safe(rollback)
        context["rollback_result"] = self._make_storage_safe(rollback)
    bucket["rollback"] = _zero_v913_upsert_action(bucket.get("rollback"), rollback_action)
    execution["api_actions"] = bucket
    execution["rollback_actions"] = _zero_v913_upsert_action(execution.get("rollback_actions"), rollback_action)
    execution["last_rollback_restore_action"] = copy.deepcopy(rollback_action)
    execution["last_api_action_event"] = "rollback_restore"
    execution["last_api_action_at"] = self._now()
    context["engineering_execution"] = self._zero_v913_merge_api_actions_into_execution(execution)
    return self._zero_v913_save_action_context(task, state, context, rollback_action)


TaskRuntime._zero_v913_normalize_api_action = _zero_v913_normalize_api_action
TaskRuntime._zero_v913_merge_api_actions_into_execution = _zero_v913_merge_api_actions_into_execution
TaskRuntime._zero_v912_force_engineering_action_landing = _zero_v913_force_engineering_action_landing
TaskRuntime._zero_v913_load_action_context = _zero_v913_load_action_context
TaskRuntime._zero_v913_save_action_context = _zero_v913_save_action_context
TaskRuntime.update_current_engineering_action = _zero_v913_update_current_engineering_action
TaskRuntime.complete_engineering_action = _zero_v913_complete_engineering_action
TaskRuntime.fail_engineering_action = _zero_v913_fail_engineering_action
TaskRuntime.block_engineering_action = _zero_v913_block_engineering_action
TaskRuntime.record_rollback_restore_action = _zero_v913_record_rollback_restore_action


# ============================================================
# AER v9.1.5 - Direct Engineering Action Runtime API Persistence Fix
# ============================================================
# This patch intentionally overrides the v9.1.3/v9.1.4 action API layer with
# a direct persistence path.  The previous compatibility layer could create the
# engineering_execution skeleton but still fail to persist API action mutations
# when the force-landing compatibility hook rebuilt the derived view.  These
# public methods now mutate repair_context.engineering_execution directly, save
# it, and mirror the same object at top-level state["engineering_execution"] for
# smoke tests / callers that inspect the state without walking repair_context.


def _zero_v915_now(self: TaskRuntime) -> str:
    try:
        return self._now()
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _zero_v915_safe_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _zero_v915_safe_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(item) for item in value if isinstance(item, dict)]


def _zero_v915_action_id(action: Dict[str, Any], fallback: str = "action") -> str:
    for key in ("action_id", "id", "step_id", "name"):
        value = str(action.get(key) or "").strip()
        if value:
            return value
    return fallback


def _zero_v915_upsert(items: Any, action: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _zero_v915_safe_list(items)
    action_id = _zero_v915_action_id(action, "")
    replaced = False
    out: List[Dict[str, Any]] = []
    for row in rows:
        if action_id and _zero_v915_action_id(row, "") == action_id:
            out.append(copy.deepcopy(action))
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(copy.deepcopy(action))
    return out[-MAX_STORED_LIST_ITEMS:]


def _zero_v915_remove(items: Any, action_id: str) -> List[Dict[str, Any]]:
    target = str(action_id or "").strip()
    rows = _zero_v915_safe_list(items)
    if not target:
        return rows[-MAX_STORED_LIST_ITEMS:]
    return [row for row in rows if _zero_v915_action_id(row, "") != target][-MAX_STORED_LIST_ITEMS:]


def _zero_v915_normalize_execution(self: TaskRuntime, execution: Any, *, state: Dict[str, Any]) -> Dict[str, Any]:
    eng = copy.deepcopy(execution) if isinstance(execution, dict) else {}

    for key in ("pending_actions", "completed_actions", "failed_actions", "blocked_actions", "rollback_actions"):
        eng[key] = _zero_v915_safe_list(eng.get(key))

    if not isinstance(eng.get("current_action"), dict):
        eng["current_action"] = {}

    api = eng.get("api_actions") if isinstance(eng.get("api_actions"), dict) else {}
    if not isinstance(api.get("current"), dict):
        api["current"] = {}
    for key in ("completed", "failed", "blocked", "rollback"):
        api[key] = _zero_v915_safe_list(api.get(key))
    eng["api_actions"] = api

    if "status" not in eng or not str(eng.get("status") or "").strip():
        eng["status"] = str(state.get("status") or "running")
    eng["runtime_api_layer"] = "aer_v9_1_5"
    eng.setdefault("action_landing_version", "aer_v9_1_5")
    return eng


def _zero_v915_refresh_action_status(execution: Dict[str, Any]) -> Dict[str, Any]:
    current = execution.get("current_action") if isinstance(execution.get("current_action"), dict) else {}
    execution["action_status"] = {
        "pending": len(_zero_v915_safe_list(execution.get("pending_actions"))),
        "completed": len(_zero_v915_safe_list(execution.get("completed_actions"))),
        "failed": len(_zero_v915_safe_list(execution.get("failed_actions"))),
        "blocked": len(_zero_v915_safe_list(execution.get("blocked_actions"))),
        "rollback": len(_zero_v915_safe_list(execution.get("rollback_actions"))),
        "current_action_id": _zero_v915_action_id(current, "") if current else "",
    }
    return execution


def _zero_v915_normalize_action_payload(
    self: TaskRuntime,
    task: Dict[str, Any],
    state: Dict[str, Any],
    action: Optional[Dict[str, Any]],
    *,
    status: str,
    current_tick: int = 0,
    result: Optional[Dict[str, Any]] = None,
    error: Any = None,
    reason: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    payload = _zero_v915_safe_dict(action)
    for key, value in kwargs.items():
        if value is not None:
            payload[key] = copy.deepcopy(value)

    action_id = _zero_v915_action_id(payload, "")
    if not action_id:
        step_index = self._safe_int(state.get("current_step_index"), 0)
        action_id = f"action_{step_index}"
    payload["action_id"] = action_id
    payload["status"] = str(status or payload.get("status") or "running")
    payload["tick"] = self._safe_int(payload.get("tick"), current_tick)
    payload["ts"] = str(payload.get("ts") or _zero_v915_now(self))
    payload["source"] = str(payload.get("source") or "task_runtime_api")

    if result is not None:
        payload["result"] = self._sanitize_step_result_for_storage(result) if isinstance(result, dict) else self._make_storage_safe(result)
    elif isinstance(payload.get("result"), dict):
        payload["result"] = self._sanitize_step_result_for_storage(payload.get("result"))

    if error is not None:
        payload["error"] = self._truncate_text(self._stringify_failure_message(error), 500)
    if reason:
        payload["reason"] = self._truncate_text(reason, 500)

    # Useful context for UI/debug without forcing callers to provide it.
    payload.setdefault("task_id", str(task.get("task_id") or task.get("id") or task.get("task_name") or ""))
    payload.setdefault("task_name", str(task.get("task_name") or task.get("task_id") or task.get("id") or ""))
    payload.setdefault("step_index", self._safe_int(state.get("current_step_index"), 0))
    return self._make_storage_safe(payload)


def _zero_v915_load_engineering_execution(self: TaskRuntime, task: Dict[str, Any]) -> Dict[str, Any]:
    state = self.load_runtime_state(task)
    context = state.get("repair_context") if isinstance(state.get("repair_context"), dict) else {}
    context = self._normalize_repair_context_for_task(context, task=task, state=state)

    nested_execution = context.get("engineering_execution") if isinstance(context.get("engineering_execution"), dict) else {}
    top_execution = state.get("engineering_execution") if isinstance(state.get("engineering_execution"), dict) else {}
    execution = copy.deepcopy(nested_execution or top_execution)
    execution = self._zero_v915_normalize_execution(execution, state=state)
    context["engineering_execution"] = execution
    state["repair_context"] = context
    state["engineering_execution"] = copy.deepcopy(execution)
    return {"state": state, "context": context, "execution": execution}


def _zero_v915_save_engineering_execution(
    self: TaskRuntime,
    task: Dict[str, Any],
    state: Dict[str, Any],
    context: Dict[str, Any],
    execution: Dict[str, Any],
    action: Dict[str, Any],
    *,
    ok: bool = True,
) -> Dict[str, Any]:
    execution = self._zero_v915_normalize_execution(execution, state=state)
    execution = _zero_v915_refresh_action_status(execution)
    execution["last_runtime_api_merge_at"] = _zero_v915_now(self)

    context["engineering_execution"] = copy.deepcopy(execution)
    state["repair_context"] = context
    state["engineering_execution"] = copy.deepcopy(execution)
    state["updated_at"] = _zero_v915_now(self)

    saved = self.save_runtime_state(task, state)

    # save_runtime_state normalizes known runtime fields; keep the top-level
    # compatibility mirror present even if older normalizers ignored it.
    if not isinstance(saved.get("repair_context"), dict):
        saved["repair_context"] = {}
    saved["repair_context"]["engineering_execution"] = copy.deepcopy(execution)
    saved["engineering_execution"] = copy.deepcopy(execution)
    self._write_json(self._get_runtime_state_file(task), self._compact_runtime_state_for_storage(saved))
    saved = self.load_runtime_state(task)
    if isinstance(saved.get("repair_context"), dict) and isinstance(saved["repair_context"].get("engineering_execution"), dict):
        saved["engineering_execution"] = copy.deepcopy(saved["repair_context"]["engineering_execution"])

    self._sync_task_from_runtime_state(task, saved)
    return {
        "ok": ok,
        "status": saved.get("status", state.get("status", "running")),
        "task": copy.deepcopy(task),
        "runtime_state": saved,
        "engineering_action": copy.deepcopy(action),
        "engineering_execution": copy.deepcopy(saved.get("engineering_execution", execution)),
    }


def _zero_v915_update_current_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v915_load_engineering_execution(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    api = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}

    current = self._zero_v915_normalize_action_payload(
        task,
        state,
        action,
        status=str(kwargs.pop("status", "running") or "running"),
        current_tick=current_tick,
        **kwargs,
    )
    api["current"] = copy.deepcopy(current)
    execution["api_actions"] = api
    execution["current_action"] = copy.deepcopy(current)
    execution["pending_actions"] = _zero_v915_upsert(execution.get("pending_actions"), current)
    execution["last_api_action_event"] = "update_current"
    execution["last_api_action_at"] = _zero_v915_now(self)
    return self._zero_v915_save_engineering_execution(task, state, context, execution, current, ok=True)


def _zero_v915_complete_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v915_load_engineering_execution(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    api = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}
    source = action if isinstance(action, dict) and action else api.get("current") or execution.get("current_action")

    completed = self._zero_v915_normalize_action_payload(
        task,
        state,
        source,
        status="completed",
        current_tick=current_tick,
        result=result,
        **kwargs,
    )
    action_id = _zero_v915_action_id(completed, "")
    api["completed"] = _zero_v915_upsert(api.get("completed"), completed)
    if isinstance(api.get("current"), dict) and _zero_v915_action_id(api.get("current"), "") == action_id:
        api["current"] = {}
    execution["api_actions"] = api
    execution["pending_actions"] = _zero_v915_remove(execution.get("pending_actions"), action_id)
    execution["completed_actions"] = _zero_v915_upsert(execution.get("completed_actions"), completed)
    if isinstance(execution.get("current_action"), dict) and _zero_v915_action_id(execution.get("current_action"), "") == action_id:
        execution["current_action"] = {}
    execution["last_completed_action"] = copy.deepcopy(completed)
    execution["last_api_action_event"] = "complete"
    execution["last_api_action_at"] = _zero_v915_now(self)
    return self._zero_v915_save_engineering_execution(task, state, context, execution, completed, ok=True)


def _zero_v915_fail_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    error: Any = None,
    reason: str = "",
    result: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v915_load_engineering_execution(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    api = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}
    source = action if isinstance(action, dict) and action else api.get("current") or execution.get("current_action")

    failed = self._zero_v915_normalize_action_payload(
        task,
        state,
        source,
        status="failed",
        current_tick=current_tick,
        result=result,
        error=error,
        reason=reason,
        **kwargs,
    )
    action_id = _zero_v915_action_id(failed, "")
    api["failed"] = _zero_v915_upsert(api.get("failed"), failed)
    if isinstance(api.get("current"), dict) and _zero_v915_action_id(api.get("current"), "") == action_id:
        api["current"] = {}
    execution["api_actions"] = api
    execution["pending_actions"] = _zero_v915_remove(execution.get("pending_actions"), action_id)
    execution["failed_actions"] = _zero_v915_upsert(execution.get("failed_actions"), failed)
    if isinstance(execution.get("current_action"), dict) and _zero_v915_action_id(execution.get("current_action"), "") == action_id:
        execution["current_action"] = {}
    execution["last_failed_action"] = copy.deepcopy(failed)
    execution["last_api_action_event"] = "fail"
    execution["last_api_action_at"] = _zero_v915_now(self)
    if reason or error is not None:
        state["last_error"] = self._truncate_text(reason or self._stringify_failure_message(error), 500)
    return self._zero_v915_save_engineering_execution(task, state, context, execution, failed, ok=False)


def _zero_v915_block_engineering_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    blocker: Optional[Dict[str, Any]] = None,
    reason: str = "",
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v915_load_engineering_execution(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    api = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}
    source = action if isinstance(action, dict) and action else api.get("current") or execution.get("current_action")
    block_reason = reason or (str(blocker.get("reason") or "") if isinstance(blocker, dict) else "")

    blocked = self._zero_v915_normalize_action_payload(
        task,
        state,
        source,
        status="blocked",
        current_tick=current_tick,
        reason=block_reason,
        **kwargs,
    )
    if isinstance(blocker, dict):
        blocked["blocker"] = self._make_storage_safe(blocker)
    action_id = _zero_v915_action_id(blocked, "")
    api["blocked"] = _zero_v915_upsert(api.get("blocked"), blocked)
    if isinstance(api.get("current"), dict) and _zero_v915_action_id(api.get("current"), "") == action_id:
        api["current"] = {}
    execution["api_actions"] = api
    execution["pending_actions"] = _zero_v915_remove(execution.get("pending_actions"), action_id)
    execution["blocked_actions"] = _zero_v915_upsert(execution.get("blocked_actions"), blocked)
    if isinstance(execution.get("current_action"), dict) and _zero_v915_action_id(execution.get("current_action"), "") == action_id:
        execution["current_action"] = {}
    execution["last_blocked_action"] = copy.deepcopy(blocked)
    execution["last_api_action_event"] = "block"
    execution["last_api_action_at"] = _zero_v915_now(self)
    state["waiting_reason"] = block_reason
    if str(state.get("status") or "") not in TERMINAL_STATUSES:
        state["status"] = "blocked"
    return self._zero_v915_save_engineering_execution(task, state, context, execution, blocked, ok=True)


def _zero_v915_record_rollback_restore_action(
    self: TaskRuntime,
    task: Dict[str, Any],
    action: Optional[Dict[str, Any]] = None,
    rollback: Optional[Dict[str, Any]] = None,
    current_tick: int = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    loaded = self._zero_v915_load_engineering_execution(task)
    state = loaded["state"]
    context = loaded["context"]
    execution = loaded["execution"]
    api = execution.get("api_actions") if isinstance(execution.get("api_actions"), dict) else {}

    rollback_action = self._zero_v915_normalize_action_payload(
        task,
        state,
        action,
        status="rollback_restored",
        current_tick=current_tick,
        result=rollback if isinstance(rollback, dict) else None,
        **kwargs,
    )
    if isinstance(rollback, dict):
        rollback_action["rollback"] = self._make_storage_safe(rollback)
        context["rollback_result"] = self._make_storage_safe(rollback)
    api["rollback"] = _zero_v915_upsert(api.get("rollback"), rollback_action)
    execution["api_actions"] = api
    execution["rollback_actions"] = _zero_v915_upsert(execution.get("rollback_actions"), rollback_action)
    execution["last_rollback_restore_action"] = copy.deepcopy(rollback_action)
    execution["last_api_action_event"] = "rollback_restore"
    execution["last_api_action_at"] = _zero_v915_now(self)
    return self._zero_v915_save_engineering_execution(task, state, context, execution, rollback_action, ok=True)


TaskRuntime._zero_v915_normalize_execution = _zero_v915_normalize_execution
TaskRuntime._zero_v915_normalize_action_payload = _zero_v915_normalize_action_payload
TaskRuntime._zero_v915_load_engineering_execution = _zero_v915_load_engineering_execution
TaskRuntime._zero_v915_save_engineering_execution = _zero_v915_save_engineering_execution
TaskRuntime.update_current_engineering_action = _zero_v915_update_current_engineering_action
TaskRuntime.complete_engineering_action = _zero_v915_complete_engineering_action
TaskRuntime.fail_engineering_action = _zero_v915_fail_engineering_action
TaskRuntime.block_engineering_action = _zero_v915_block_engineering_action
TaskRuntime.record_rollback_restore_action = _zero_v915_record_rollback_restore_action


# ============================================================
# AER Governance Core Seal v1
# ============================================================

def _zero_v916_build_governed_replay_aer_governance_core_seal(
    self: TaskRuntime,
    policy_resolution: Dict[str, Any],
    *,
    diff_verification: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    journal_preview: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy_resolution = copy.deepcopy(policy_resolution if isinstance(policy_resolution, dict) else {})
    diff_verification = copy.deepcopy(diff_verification if isinstance(diff_verification, dict) else {})
    snapshot = copy.deepcopy(snapshot if isinstance(snapshot, dict) else {})
    journal_preview = copy.deepcopy(journal_preview if isinstance(journal_preview, dict) else {})

    replay_id = str(policy_resolution.get("replay_id") or "")
    transaction_id = str(policy_resolution.get("transaction_id") or "")
    action = str(policy_resolution.get("action") or "")

    stage_order = [
        "replay_request",
        "preflight",
        "decision",
        "gateway_preview",
        "approval_gate",
        "controlled_dispatch_preview",
        "dispatch_authorization",
        "immutable_journal_preview",
        "governance_state_snapshot",
        "governance_diff_verification",
        "governance_policy_resolution",
        "aer_governance_core_seal",
    ]

    governance_flags = {
        "execution_allowed": False,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": False,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
    }

    integrity_checks = {
        "capability_integrity_preserved": not bool(
            diff_verification.get("capability_drift_detection", {}).get(
                "unsafe_flag_escalation_detected",
                False,
            )
        ),
        "deterministic": bool(
            diff_verification.get("deterministic_verification", {}).get(
                "deterministic",
                True,
            )
        ),
        "reconstruction_consistent": bool(
            diff_verification.get("reconstruction_consistency_check", {}).get(
                "reconstruction_consistent",
                True,
            )
        ),
    }

    governance_stable = all(integrity_checks.values())

    seal_summary = {
        "seal_type": "aer_governance_core_seal_preview",
        "preview_only": True,
        "governance_stable": governance_stable,
        "stage_count": len(stage_order),
        "final_stage": "aer_governance_core_seal",
        "blocked_reason": str(policy_resolution.get("blocked_reason") or ""),
        "risk_level": str(policy_resolution.get("risk_level") or "unknown"),
    }

    debug_context = {
        "source": "governed_replay_aer_governance_core_seal_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "governance_stable": governance_stable,
        "stage_count": len(stage_order),
        "blocked_reason": str(policy_resolution.get("blocked_reason") or ""),
        "risk_level": str(policy_resolution.get("risk_level") or "unknown"),
        **governance_flags,
    }

    return {
        "source": "governed_replay_aer_governance_core_seal_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "seal_status": "preview_only",
        "governance_stable": governance_stable,
        "stage_order": stage_order,
        "governance_flags": governance_flags,
        "integrity_checks": integrity_checks,
        "seal_summary": seal_summary,
        "policy_resolution": policy_resolution,
        "diff_verification": diff_verification,
        "snapshot": snapshot,
        "journal_preview": journal_preview,
        "execution_allowed": False,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": False,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
        "blocked_reason": str(policy_resolution.get("blocked_reason") or ""),
        "risk_level": str(policy_resolution.get("risk_level") or "unknown"),
        "debug_context": debug_context,
    }


TaskRuntime.build_governed_replay_aer_governance_core_seal = _zero_v916_build_governed_replay_aer_governance_core_seal


# ============================================================
# AER Governance Core Seal v1.1
# ============================================================

def _zero_v917_nested_unsafe_flag_escalation(diff_verification: Dict[str, Any]) -> bool:
    if not isinstance(diff_verification, dict):
        return False

    snapshot_a = diff_verification.get("snapshot_a")
    snapshot_b = diff_verification.get("snapshot_b")
    if not isinstance(snapshot_a, dict) or not isinstance(snapshot_b, dict):
        return False

    flag_names = [
        "execution_allowed",
        "mutation_allowed",
        "executor_dispatch_allowed",
        "scheduler_dispatch_allowed",
        "command_execution_allowed",
        "authorization_granted",
        "auto_commit",
        "auto_rollback",
    ]

    for flag in flag_names:
        a_value = bool(snapshot_a.get(flag, False))
        b_value = bool(snapshot_b.get(flag, False))
        if a_value is False and b_value is True:
            return True

    flags_a = snapshot_a.get("governance_flags")
    flags_b = snapshot_b.get("governance_flags")
    if isinstance(flags_a, dict) and isinstance(flags_b, dict):
        for flag in flag_names:
            a_value = bool(flags_a.get(flag, False))
            b_value = bool(flags_b.get(flag, False))
            if a_value is False and b_value is True:
                return True

    return False


def _zero_v917_build_governed_replay_aer_governance_core_seal(
    self: TaskRuntime,
    policy_resolution: Dict[str, Any],
    *,
    diff_verification: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    journal_preview: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy_resolution = copy.deepcopy(policy_resolution if isinstance(policy_resolution, dict) else {})
    diff_verification = copy.deepcopy(diff_verification if isinstance(diff_verification, dict) else {})
    snapshot = copy.deepcopy(snapshot if isinstance(snapshot, dict) else {})
    journal_preview = copy.deepcopy(journal_preview if isinstance(journal_preview, dict) else {})

    replay_id = str(policy_resolution.get("replay_id") or diff_verification.get("replay_id") or "")
    transaction_id = str(policy_resolution.get("transaction_id") or diff_verification.get("transaction_id") or "")
    action = str(policy_resolution.get("action") or diff_verification.get("action") or "")

    stage_order = [
        "replay_request",
        "preflight",
        "decision",
        "gateway_preview",
        "approval_gate",
        "controlled_dispatch_preview",
        "dispatch_authorization",
        "immutable_journal_preview",
        "governance_state_snapshot",
        "governance_diff_verification",
        "governance_policy_resolution",
        "aer_governance_core_seal",
    ]

    governance_flags = {
        "execution_allowed": False,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": False,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
    }

    drift = diff_verification.get("capability_drift_detection")
    if not isinstance(drift, dict):
        drift = {}

    deterministic = diff_verification.get("deterministic_verification")
    if not isinstance(deterministic, dict):
        deterministic = {}

    reconstruction = diff_verification.get("reconstruction_consistency_check")
    if not isinstance(reconstruction, dict):
        reconstruction = {}

    nested_unsafe_escalation = _zero_v917_nested_unsafe_flag_escalation(diff_verification)
    unsafe_escalation = bool(
        drift.get("unsafe_flag_escalation_detected", False)
        or drift.get("drift_detected", False)
        or nested_unsafe_escalation
    )

    integrity_checks = {
        "capability_integrity_preserved": not unsafe_escalation,
        "deterministic": bool(deterministic.get("deterministic", True)),
        "reconstruction_consistent": bool(reconstruction.get("reconstruction_consistent", True)),
        "nested_unsafe_flag_escalation_detected": nested_unsafe_escalation,
    }

    governance_stable = (
        integrity_checks["capability_integrity_preserved"]
        and integrity_checks["deterministic"]
        and integrity_checks["reconstruction_consistent"]
    )

    blocked_reason = str(policy_resolution.get("blocked_reason") or diff_verification.get("blocked_reason") or "")
    risk_level = str(policy_resolution.get("risk_level") or diff_verification.get("risk_level") or "unknown")

    seal_summary = {
        "seal_type": "aer_governance_core_seal_preview",
        "preview_only": True,
        "governance_stable": governance_stable,
        "stage_count": len(stage_order),
        "final_stage": "aer_governance_core_seal",
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
    }

    debug_context = {
        "source": "governed_replay_aer_governance_core_seal_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "governance_stable": governance_stable,
        "stage_count": len(stage_order),
        "unsafe_flag_escalation_detected": unsafe_escalation,
        "nested_unsafe_flag_escalation_detected": nested_unsafe_escalation,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
        **governance_flags,
    }

    return {
        "source": "governed_replay_aer_governance_core_seal_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "seal_status": "preview_only",
        "governance_stable": governance_stable,
        "stage_order": stage_order,
        "governance_flags": governance_flags,
        "integrity_checks": integrity_checks,
        "seal_summary": seal_summary,
        "policy_resolution": policy_resolution,
        "diff_verification": diff_verification,
        "snapshot": snapshot,
        "journal_preview": journal_preview,
        "execution_allowed": False,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": False,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
        "debug_context": debug_context,
    }


TaskRuntime.build_governed_replay_aer_governance_core_seal = _zero_v917_build_governed_replay_aer_governance_core_seal


# ============================================================
# Sandboxed Execution Ticket Preview v1
# ============================================================

def _zero_v918_build_governed_sandboxed_execution_ticket_preview(
    self: TaskRuntime,
    aer_governance_core_seal: Dict[str, Any],
    *,
    policy_resolution: Optional[Dict[str, Any]] = None,
    diff_verification: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    aer_governance_core_seal = copy.deepcopy(
        aer_governance_core_seal if isinstance(aer_governance_core_seal, dict) else {}
    )
    policy_resolution = copy.deepcopy(policy_resolution if isinstance(policy_resolution, dict) else {})
    diff_verification = copy.deepcopy(diff_verification if isinstance(diff_verification, dict) else {})

    replay_id = str(
        aer_governance_core_seal.get("replay_id")
        or policy_resolution.get("replay_id")
        or diff_verification.get("replay_id")
        or ""
    )
    transaction_id = str(
        aer_governance_core_seal.get("transaction_id")
        or policy_resolution.get("transaction_id")
        or diff_verification.get("transaction_id")
        or ""
    )
    action = str(
        aer_governance_core_seal.get("action")
        or policy_resolution.get("action")
        or diff_verification.get("action")
        or ""
    )
    blocked_reason = str(
        aer_governance_core_seal.get("blocked_reason")
        or policy_resolution.get("blocked_reason")
        or diff_verification.get("blocked_reason")
        or "sandboxed execution ticket is preview-only"
    )
    risk_level = str(
        aer_governance_core_seal.get("risk_level")
        or policy_resolution.get("risk_level")
        or diff_verification.get("risk_level")
        or "high"
    )
    execution_ticket_status = "preview_only"

    execution_ticket = {
        "ticket_type": "sandboxed_execution_ticket_preview",
        "preview_only": True,
        "immutable": True,
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "governance_sealed": True,
        "execution_allowed": False,
        "mutation_allowed": False,
        "dispatch_allowed": False,
        "shell_execution_allowed": False,
    }

    capability_envelope = {
        "envelope_type": "sandboxed_capability_envelope_preview",
        "preview_only": True,
        "readonly_execution_only": True,
        "mutation_execution_allowed": False,
        "shell_execution_allowed": False,
        "filesystem_write_allowed": False,
        "network_access_allowed": False,
        "subprocess_allowed": False,
        "repo_mutation_allowed": False,
    }

    allowed_readonly_commands = [
        "pwd",
        "dir",
        "ls",
        "git status",
        "python -m compileall",
        "pytest --collect-only",
    ]
    blocked_commands = [
        "rm",
        "del",
        "move",
        "rename",
        "git commit",
        "git push",
        "git reset",
        "pip install",
        "powershell",
        "bash",
        "cmd /c",
        "python script_that_writes.py",
    ]

    sandbox_dispatch_preview = {
        "dispatch_type": "sandboxed_dispatch_preview",
        "preview_only": True,
        "readonly_dispatch_only": True,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "shell_execution_allowed": False,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
    }

    execution_verification_contract = {
        "verification_type": "sandbox_execution_verification_preview",
        "preview_only": True,
        "deterministic_verification_required": True,
        "evidence_capture_required": True,
        "rollback_required_before_mutation": True,
        "governance_seal_required": True,
    }

    evidence_capture_contract = {
        "evidence_type": "sandbox_execution_evidence_preview",
        "preview_only": True,
        "capture_stdout": True,
        "capture_stderr": True,
        "capture_exit_code": True,
        "capture_command": True,
        "capture_runtime_metadata": True,
        "persist_execution_logs": False,
    }

    debug_context = {
        "source": "governed_sandboxed_execution_ticket_preview_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "execution_ticket_status": execution_ticket_status,
        "readonly_execution_only": True,
        "shell_execution_allowed": False,
        "filesystem_write_allowed": False,
        "network_access_allowed": False,
        "subprocess_allowed": False,
        "repo_mutation_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "authorization_granted": False,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
    }

    return {
        "source": "governed_sandboxed_execution_ticket_preview_v1",
        "replay_id": replay_id,
        "transaction_id": transaction_id,
        "action": action,
        "execution_ticket_status": execution_ticket_status,
        "execution_ticket": execution_ticket,
        "capability_envelope": capability_envelope,
        "allowed_readonly_commands": allowed_readonly_commands,
        "blocked_commands": blocked_commands,
        "sandbox_dispatch_preview": sandbox_dispatch_preview,
        "execution_verification_contract": execution_verification_contract,
        "evidence_capture_contract": evidence_capture_contract,
        "aer_governance_core_seal": aer_governance_core_seal,
        "policy_resolution": policy_resolution,
        "diff_verification": diff_verification,
        "execution_allowed": False,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": False,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
        "shell_execution_allowed": False,
        "filesystem_write_allowed": False,
        "network_access_allowed": False,
        "subprocess_allowed": False,
        "repo_mutation_allowed": False,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
        "debug_context": debug_context,
    }


TaskRuntime.build_governed_sandboxed_execution_ticket_preview = _zero_v918_build_governed_sandboxed_execution_ticket_preview


# ============================================================
# Read-only Command Execution Gate v1
# ============================================================

def _zero_v919_normalize_command(command: Any) -> str:
    return " ".join(str(command or "").strip().lower().split())


def _zero_v919_command_matches_pattern(command: str, pattern: str) -> bool:
    pattern = _zero_v919_normalize_command(pattern)
    return command == pattern or command.startswith(f"{pattern} ")


def _zero_v919_command_matches_readonly(command: str, pattern: str) -> bool:
    pattern = _zero_v919_normalize_command(pattern)
    if command == pattern:
        return True
    return pattern in {"python -m compileall", "pytest --collect-only"} and command.startswith(f"{pattern} ")


def _zero_v919_classify_command(
    normalized_command: str,
    *,
    allowed_readonly_commands: List[str],
    blocked_commands: List[str],
) -> Dict[str, Any]:
    readonly_patterns = [_zero_v919_normalize_command(command) for command in allowed_readonly_commands]
    blocked_patterns = [_zero_v919_normalize_command(command) for command in blocked_commands]

    readonly_match = any(
        _zero_v919_command_matches_readonly(normalized_command, pattern)
        for pattern in readonly_patterns
    )
    matched_blocked = ""
    blocked_operator = ""
    for operator in (">>", ">", "|", "&&", ";"):
        if operator in normalized_command:
            blocked_operator = operator
            break

    for pattern in blocked_patterns:
        if _zero_v919_command_matches_pattern(normalized_command, pattern):
            matched_blocked = pattern
            break

    blocked_match = bool(matched_blocked or blocked_operator)
    blocked_pattern_classification = "none"
    if blocked_operator:
        command_category = "blocked_shell"
        blocked_pattern_classification = "shell_operator"
    elif blocked_match and matched_blocked in {"powershell", "bash", "cmd /c", "sh"}:
        command_category = "blocked_shell"
        blocked_pattern_classification = "shell"
    elif blocked_match and matched_blocked in {"pip install", "npm install", "curl", "wget"}:
        command_category = "blocked_network_or_install"
        blocked_pattern_classification = "network_or_install"
    elif blocked_match:
        command_category = "blocked_mutation"
        blocked_pattern_classification = "mutation"
    elif readonly_match:
        command_category = "readonly_allowed"
        blocked_pattern_classification = "none"
    else:
        command_category = "unknown"
        blocked_pattern_classification = "none"

    return {
        "readonly_match": readonly_match,
        "blocked_match": blocked_match,
        "matched_blocked_pattern": matched_blocked or blocked_operator,
        "blocked_pattern_classification": blocked_pattern_classification,
        "command_category": command_category,
    }


def _zero_v919_build_readonly_command_execution_gate(
    self: TaskRuntime,
    sandboxed_execution_ticket_preview: Dict[str, Any],
    command: str,
    *,
    enable_readonly_execution: bool = False,
    readonly_execution_mode: str = "preview",
) -> Dict[str, Any]:
    sandboxed_execution_ticket_preview = copy.deepcopy(
        sandboxed_execution_ticket_preview if isinstance(sandboxed_execution_ticket_preview, dict) else {}
    )
    normalized_command = _zero_v919_normalize_command(command)

    allowed_readonly_commands = sandboxed_execution_ticket_preview.get("allowed_readonly_commands")
    if not isinstance(allowed_readonly_commands, list):
        allowed_readonly_commands = []
    allowed_readonly_commands = [str(item) for item in allowed_readonly_commands]
    if not allowed_readonly_commands:
        allowed_readonly_commands = [
            "pwd",
            "dir",
            "ls",
            "git status",
            "python -m compileall",
            "pytest --collect-only",
        ]

    blocked_commands = sandboxed_execution_ticket_preview.get("blocked_commands")
    if not isinstance(blocked_commands, list):
        blocked_commands = []
    blocked_commands = [str(item) for item in blocked_commands]
    for command_pattern in (
        "rm",
        "del",
        "copy",
        "move",
        "mv",
        "rename",
        "git commit",
        "git push",
        "git reset",
        "git clean",
        "git checkout",
        "pip install",
        "npm install",
        "curl",
        "wget",
        "powershell",
        "bash",
        "sh",
        "cmd /c",
        "python -c",
        "python script_that_writes.py",
        "subprocess",
    ):
        if command_pattern not in blocked_commands:
            blocked_commands.append(command_pattern)

    classification = _zero_v919_classify_command(
        normalized_command,
        allowed_readonly_commands=allowed_readonly_commands,
        blocked_commands=blocked_commands,
    )
    readonly_match = bool(classification["readonly_match"])
    blocked_match = bool(classification["blocked_match"])
    command_category = str(classification["command_category"])
    command_allowed = readonly_match and not blocked_match
    normalized_mode = str(readonly_execution_mode or "preview").strip().lower()
    explicit_readonly_execution = bool(enable_readonly_execution) and normalized_mode == "execute_readonly"
    execution_allowed = command_allowed and explicit_readonly_execution
    command_execution_allowed = command_allowed and execution_allowed
    blocked_pattern_classification = str(classification["blocked_pattern_classification"])

    if blocked_match:
        deny_reason = "blocked command pattern"
    elif not command_allowed:
        deny_reason = "command not in readonly whitelist"
    else:
        deny_reason = ""

    expected_evidence = ["stdout", "stderr", "exit_code", "command", "runtime_metadata"]
    execution_plan_preview = {
        "preview_only": True,
        "command": command,
        "normalized_command": normalized_command,
        "command_allowed": command_allowed,
        "command_category": command_category,
        "dispatch_allowed": False,
        "execution_allowed": execution_allowed,
        "readonly_execution_only": True,
        "mutation_allowed": False,
        "expected_evidence": expected_evidence,
        "enable_readonly_execution": bool(enable_readonly_execution),
        "readonly_execution_mode": normalized_mode,
        "command_execution_allowed": command_execution_allowed,
    }

    evidence_capture_plan = {
        "preview_only": True,
        "capture_stdout": True,
        "capture_stderr": True,
        "capture_exit_code": True,
        "capture_command": True,
        "capture_runtime_metadata": True,
        "persist_logs": False,
        "write_allowed": False,
    }

    verification_plan = {
        "preview_only": True,
        "verify_exit_code": True,
        "verify_no_mutation": True,
        "verify_command_in_whitelist": True,
        "verify_blacklist_not_matched": True,
        "deterministic_verification_required": True,
    }

    debug_context = {
        "source": "readonly_command_execution_gate_v1",
        "command": command,
        "normalized_command": normalized_command,
        "command_category": command_category,
        "command_allowed": command_allowed,
        "deny_reason": deny_reason,
        "readonly_match": readonly_match,
        "blocked_match": blocked_match,
        "blocked_pattern_classification": blocked_pattern_classification,
        "enable_readonly_execution": bool(enable_readonly_execution),
        "readonly_execution_mode": normalized_mode,
        "execution_allowed": execution_allowed,
        "command_execution_allowed": command_execution_allowed,
        "mutation_allowed": False,
        "auto_commit": False,
        "auto_rollback": False,
    }

    return {
        "source": "readonly_command_execution_gate_v1",
        "command": command,
        "normalized_command": normalized_command,
        "command_category": command_category,
        "command_allowed": command_allowed,
        "deny_reason": deny_reason,
        "readonly_match": readonly_match,
        "blocked_match": blocked_match,
        "blocked_pattern_classification": blocked_pattern_classification,
        "enable_readonly_execution": bool(enable_readonly_execution),
        "readonly_execution_mode": normalized_mode,
        "execution_plan_preview": execution_plan_preview,
        "evidence_capture_plan": evidence_capture_plan,
        "verification_plan": verification_plan,
        "sandboxed_execution_ticket_preview": sandboxed_execution_ticket_preview,
        "execution_allowed": execution_allowed,
        "mutation_allowed": False,
        "executor_dispatch_allowed": False,
        "scheduler_dispatch_allowed": False,
        "command_execution_allowed": command_execution_allowed,
        "authorization_granted": False,
        "auto_commit": False,
        "auto_rollback": False,
        "debug_context": debug_context,
    }


TaskRuntime.build_readonly_command_execution_gate = _zero_v919_build_readonly_command_execution_gate


# ============================================================
# Controlled Read-only Execution Bridge v1
# ============================================================

def _zero_readonly_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _zero_readonly_sha256_preview(value: Any, *, preview_limit: int = 2000) -> Dict[str, Any]:
    text = value if isinstance(value, str) else str(value or "")
    return {
        "digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "preview": text[:preview_limit],
    }


def _zero_build_execution_record(
    result: Dict[str, Any],
    *,
    argv: List[str],
    cwd: str,
    started_at: str,
    finished_at: str,
) -> Dict[str, Any]:
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    stdout_record = _zero_readonly_sha256_preview(stdout)
    stderr_record = _zero_readonly_sha256_preview(stderr)
    return {
        "record_type": "readonly_command_execution",
        "command": result.get("command", ""),
        "normalized_command": result.get("normalized_command", ""),
        "argv": list(argv),
        "cwd": cwd,
        "status": result.get("status", ""),
        "executed": bool(result.get("executed", False)),
        "returncode": result.get("returncode"),
        "duration_seconds": result.get("duration_seconds", 0.0),
        "timeout_seconds": result.get("timeout_seconds", 10),
        "stdout_digest": stdout_record["digest"],
        "stderr_digest": stderr_record["digest"],
        "stdout_preview": stdout_record["preview"],
        "stderr_preview": stderr_record["preview"],
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _zero_build_replay_record(
    result: Dict[str, Any],
    *,
    argv: List[str],
    cwd: str,
) -> Dict[str, Any]:
    replayable = bool(result.get("executed", False)) and bool(result.get("command_execution_allowed", False))
    return {
        "replay_type": "readonly_command_replay",
        "replayable": replayable,
        "replay_command": result.get("command", ""),
        "replay_normalized_command": result.get("normalized_command", ""),
        "replay_argv": list(argv) if replayable else [],
        "replay_cwd": cwd if replayable else "",
        "expected_returncode": result.get("returncode") if replayable else None,
        "expected_stdout_digest": result.get("execution_record", {}).get("stdout_digest", ""),
        "expected_stderr_digest": result.get("execution_record", {}).get("stderr_digest", ""),
        "replay_safety": "readonly_only",
        "replay_requires_confirmation": False,
    }


def _zero_build_evidence_record(result: Dict[str, Any]) -> Dict[str, Any]:
    execution_record = result.get("execution_record") if isinstance(result.get("execution_record"), dict) else {}
    evidence_seed = "|".join(
        [
            str(result.get("normalized_command") or ""),
            str(result.get("status") or ""),
            str(execution_record.get("stdout_digest") or ""),
            str(execution_record.get("stderr_digest") or ""),
            str(result.get("returncode")),
        ]
    )
    return {
        "evidence_type": "command_execution_evidence",
        "evidence_id": hashlib.sha256(evidence_seed.encode("utf-8")).hexdigest(),
        "source": "readonly_execution_gate",
        "command": result.get("command", ""),
        "normalized_command": result.get("normalized_command", ""),
        "status": result.get("status", ""),
        "executed": bool(result.get("executed", False)),
        "stdout_digest": execution_record.get("stdout_digest", ""),
        "stderr_digest": execution_record.get("stderr_digest", ""),
        "returncode": result.get("returncode"),
        "duration_seconds": result.get("duration_seconds", 0.0),
        "captured_fields": ["stdout", "stderr", "returncode", "duration_seconds", "status"],
    }


def _zero_build_verification_record(result: Dict[str, Any]) -> Dict[str, Any]:
    status = str(result.get("status") or "")
    returncode = result.get("returncode")
    if status == "preview":
        verification_status = "preview"
    elif status == "blocked":
        verification_status = "blocked"
    elif status == "timeout":
        verification_status = "timeout"
    elif bool(result.get("executed", False)) and returncode == 0:
        verification_status = "passed"
    elif bool(result.get("executed", False)):
        verification_status = "failed"
    else:
        verification_status = "blocked"

    checks = {
        "gate_allowed": bool(result.get("command_allowed", False)),
        "command_execution_allowed": bool(result.get("command_execution_allowed", False)),
        "no_shell_true": True,
        "argv_generated_from_whitelist": bool(result.get("execution_record", {}).get("argv")),
        "blocked_commands_not_executed": (
            str(result.get("blocked_pattern_classification") or "none") == "none"
            or not bool(result.get("executed", False))
        ),
        "unsafe_paths_not_executed": (
            str(result.get("deny_reason") or "") != "unsafe readonly command path"
            or not bool(result.get("executed", False))
        ),
    }
    return {
        "verification_type": "readonly_execution_verification",
        "verification_status": verification_status,
        "checks": checks,
    }


def _zero_v920_readonly_result_from_gate(
    gate: Dict[str, Any],
    *,
    status: str,
    stdout: str = "",
    stderr: str = "",
    returncode: Optional[int] = None,
    duration_seconds: float = 0.0,
    timeout_seconds: int = 10,
    executed: bool = False,
    deny_reason: Optional[str] = None,
    argv: Optional[List[str]] = None,
    cwd: str = "",
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> Dict[str, Any]:
    started_at = started_at or _zero_readonly_now()
    finished_at = finished_at or _zero_readonly_now()
    argv = list(argv or [])
    result = {
        "status": status,
        "command": gate.get("command", ""),
        "normalized_command": gate.get("normalized_command", ""),
        "command_allowed": bool(gate.get("command_allowed", False)),
        "execution_allowed": bool(gate.get("execution_allowed", False)),
        "command_execution_allowed": bool(gate.get("command_execution_allowed", False)),
        "deny_reason": str(deny_reason if deny_reason is not None else gate.get("deny_reason", "")),
        "blocked_pattern_classification": str(gate.get("blocked_pattern_classification", "none")),
        "execution_plan_preview": copy.deepcopy(gate.get("execution_plan_preview", {})),
        "evidence_capture_plan": copy.deepcopy(gate.get("evidence_capture_plan", {})),
        "verification_plan": copy.deepcopy(gate.get("verification_plan", {})),
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "duration_seconds": duration_seconds,
        "timeout_seconds": timeout_seconds,
        "executed": executed,
    }
    result["execution_record"] = _zero_build_execution_record(
        result,
        argv=argv,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
    )
    result["replay_record"] = _zero_build_replay_record(result, argv=argv, cwd=cwd)
    result["evidence_record"] = _zero_build_evidence_record(result)
    result["verification_record"] = _zero_build_verification_record(result)
    return result


def _zero_v920_path_has_unsafe_tokens(path_value: str) -> bool:
    if not str(path_value or "").strip():
        return True
    lowered = str(path_value).lower()
    if any(token in lowered for token in (">>", ">", "|", "&&", ";")):
        return True
    parts = lowered.replace("\\", "/").split("/")
    return ".." in parts


def _zero_v920_resolve_safe_readonly_path(path_value: str, cwd: str) -> Optional[str]:
    if _zero_v920_path_has_unsafe_tokens(path_value):
        return None
    if str(path_value).startswith("-"):
        return None

    root = os.path.abspath(cwd)
    candidate = path_value if os.path.isabs(path_value) else os.path.join(root, path_value)
    candidate = os.path.abspath(candidate)
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate


def _zero_v920_parse_readonly_argv(
    command: str,
    normalized_command: str,
    cwd: str,
) -> Dict[str, Any]:
    if normalized_command == "git status":
        return {"ok": True, "argv": ["git", "status", "--short"], "internal": ""}

    tokens = str(command or "").strip().split()
    lowered_tokens = [token.lower() for token in tokens]

    if normalized_command.startswith("python -m compileall "):
        if len(tokens) != 4 or lowered_tokens[:3] != ["python", "-m", "compileall"]:
            return {"ok": False, "deny_reason": "unsafe readonly command path"}
        safe_path = _zero_v920_resolve_safe_readonly_path(tokens[3], cwd)
        if not safe_path:
            return {"ok": False, "deny_reason": "unsafe readonly command path"}
        return {"ok": True, "argv": [sys.executable, "-m", "compileall", safe_path], "internal": ""}

    if normalized_command.startswith("pytest --collect-only "):
        if len(tokens) != 3 or lowered_tokens[:2] != ["pytest", "--collect-only"]:
            return {"ok": False, "deny_reason": "unsafe readonly command path"}
        safe_path = _zero_v920_resolve_safe_readonly_path(tokens[2], cwd)
        if not safe_path:
            return {"ok": False, "deny_reason": "unsafe readonly command path"}
        return {"ok": True, "argv": [sys.executable, "-m", "pytest", "--collect-only", safe_path], "internal": ""}

    return {"ok": False, "deny_reason": "command not in readonly whitelist"}


def _zero_v920_execute_internal_readonly_command(normalized_command: str, cwd: str) -> Dict[str, Any]:
    if normalized_command == "pwd":
        return {"stdout": f"{os.path.abspath(cwd)}\n", "stderr": "", "returncode": 0}
    if normalized_command in {"dir", "ls"}:
        try:
            names = sorted(os.listdir(cwd))
        except OSError as exc:
            return {"stdout": "", "stderr": str(exc), "returncode": 1}
        return {"stdout": "\n".join(names) + ("\n" if names else ""), "stderr": "", "returncode": 0}
    return {"stdout": "", "stderr": "unsupported internal readonly command", "returncode": 1}


def _zero_v920_run_readonly_command_execution_gate(
    self: TaskRuntime,
    sandboxed_execution_ticket_preview: Dict[str, Any],
    command: str,
    *,
    cwd: Optional[str] = None,
    timeout_seconds: int = 10,
    enable_readonly_execution: bool = False,
    readonly_execution_mode: str = "preview",
) -> Dict[str, Any]:
    start = time.monotonic()
    started_at = _zero_readonly_now()
    gate = self.build_readonly_command_execution_gate(
        sandboxed_execution_ticket_preview,
        command=command,
        enable_readonly_execution=enable_readonly_execution,
        readonly_execution_mode=readonly_execution_mode,
    )
    timeout_seconds = int(timeout_seconds or 10)
    run_cwd = os.path.abspath(cwd or os.getcwd())

    if not bool(gate.get("command_execution_allowed", False)):
        status = "preview" if bool(gate.get("command_allowed", False)) and not bool(gate.get("execution_allowed", False)) else "blocked"
        return _zero_v920_readonly_result_from_gate(
            gate,
            status=status,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            executed=False,
            argv=[],
            cwd=run_cwd,
            started_at=started_at,
            finished_at=_zero_readonly_now(),
        )

    normalized_command = str(gate.get("normalized_command") or "")

    if normalized_command in {"pwd", "dir", "ls"}:
        internal = _zero_v920_execute_internal_readonly_command(normalized_command, run_cwd)
        returncode = internal["returncode"]
        internal_argv = ["__internal_readonly__", normalized_command]
        return _zero_v920_readonly_result_from_gate(
            gate,
            status="executed" if returncode == 0 else "failed",
            stdout=internal["stdout"],
            stderr=internal["stderr"],
            returncode=returncode,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            executed=True,
            argv=internal_argv,
            cwd=run_cwd,
            started_at=started_at,
            finished_at=_zero_readonly_now(),
        )

    argv_plan = _zero_v920_parse_readonly_argv(command, normalized_command, run_cwd)
    if not bool(argv_plan.get("ok", False)):
        return _zero_v920_readonly_result_from_gate(
            gate,
            status="blocked",
            stderr=str(argv_plan.get("deny_reason") or ""),
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            executed=False,
            deny_reason=str(argv_plan.get("deny_reason") or "unsafe readonly command path"),
            argv=[],
            cwd=run_cwd,
            started_at=started_at,
            finished_at=_zero_readonly_now(),
        )

    try:
        argv = list(argv_plan["argv"])
        from core.runtime.execution_gateway import safe_subprocess_run

        completed = safe_subprocess_run(
            argv,
            timeout=timeout_seconds,
            cwd=run_cwd,
        )
        stdout = str(completed.get("stdout") or "")
        stderr = str(completed.get("stderr") or "")
        returncode = completed.get("returncode")
        if returncode is None and completed.get("error"):
            if not stderr:
                stderr = str(completed.get("error") or f"readonly command timeout after {timeout_seconds} seconds")
            return _zero_v920_readonly_result_from_gate(
                gate,
                status="timeout",
                stdout=stdout,
                stderr=stderr,
                returncode=None,
                duration_seconds=time.monotonic() - start,
                timeout_seconds=timeout_seconds,
                executed=True,
                deny_reason="readonly command timeout",
                argv=list(argv_plan.get("argv") or []),
                cwd=run_cwd,
                started_at=started_at,
                finished_at=_zero_readonly_now(),
            )
    except Exception as exc:
        return _zero_v920_readonly_result_from_gate(
            gate,
            status="failed",
            stderr=f"{type(exc).__name__}: {exc}",
            returncode=None,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            executed=False,
            deny_reason="readonly command execution failed",
            argv=list(argv_plan.get("argv") or []),
            cwd=run_cwd,
            started_at=started_at,
            finished_at=_zero_readonly_now(),
        )
    return _zero_v920_readonly_result_from_gate(
        gate,
        status="executed" if returncode == 0 else "failed",
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        duration_seconds=time.monotonic() - start,
        timeout_seconds=timeout_seconds,
        executed=True,
        argv=list(argv_plan.get("argv") or []),
        cwd=run_cwd,
        started_at=started_at,
        finished_at=_zero_readonly_now(),
    )


TaskRuntime.run_readonly_command_execution_gate = _zero_v920_run_readonly_command_execution_gate
TaskRuntime.execute_readonly_command_from_gate = _zero_v920_run_readonly_command_execution_gate


# ============================================================
# Runtime Evidence Registry v1
# ============================================================

def _zero_v921_stable_evidence_id(result: Dict[str, Any]) -> str:
    evidence_record = result.get("evidence_record") if isinstance(result.get("evidence_record"), dict) else {}
    evidence_id = str(evidence_record.get("evidence_id") or "").strip()
    if evidence_id:
        return evidence_id

    execution_record = result.get("execution_record") if isinstance(result.get("execution_record"), dict) else {}
    seed = "|".join(
        [
            str(result.get("command") or ""),
            str(result.get("normalized_command") or ""),
            str(result.get("status") or ""),
            str(result.get("returncode")),
            str(execution_record.get("stdout_digest") or ""),
            str(execution_record.get("stderr_digest") or ""),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _zero_v921_registry_record_id(evidence_id: str) -> str:
    return hashlib.sha256(f"runtime_evidence_registry_record|{evidence_id}".encode("utf-8")).hexdigest()


class RuntimeEvidenceRegistry:
    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []
        self._by_record_id: Dict[str, Dict[str, Any]] = {}
        self._by_evidence_id: Dict[str, Dict[str, Any]] = {}
        self._replay_reports: List[Dict[str, Any]] = []
        self.execution_chain_nodes: List[Dict[str, Any]] = []
        self.execution_chain_edges: List[Dict[str, Any]] = []
        self._chain_nodes_by_id: Dict[str, Dict[str, Any]] = {}
        self._execution_node_by_evidence_id: Dict[str, Dict[str, Any]] = {}

    def register_execution_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(result if isinstance(result, dict) else {})
        evidence_id = _zero_v921_stable_evidence_id(result)
        registry_record_id = _zero_v921_registry_record_id(evidence_id)

        record = {
            "registry_record_id": registry_record_id,
            "evidence_id": evidence_id,
            "record_type": "runtime_evidence_registry_record",
            "source": "readonly_execution_gate",
            "command": str(result.get("command") or ""),
            "normalized_command": str(result.get("normalized_command") or ""),
            "status": str(result.get("status") or ""),
            "executed": bool(result.get("executed", False)),
            "returncode": result.get("returncode"),
            "created_at": _zero_readonly_now(),
            "execution_record": copy.deepcopy(result.get("execution_record") if isinstance(result.get("execution_record"), dict) else {}),
            "replay_record": copy.deepcopy(result.get("replay_record") if isinstance(result.get("replay_record"), dict) else {}),
            "evidence_record": copy.deepcopy(result.get("evidence_record") if isinstance(result.get("evidence_record"), dict) else {}),
            "verification_record": copy.deepcopy(result.get("verification_record") if isinstance(result.get("verification_record"), dict) else {}),
        }

        self._by_record_id[registry_record_id] = record
        self._by_evidence_id[evidence_id] = record
        existing_index = next(
            (idx for idx, item in enumerate(self._records) if item.get("registry_record_id") == registry_record_id),
            None,
        )
        if existing_index is None:
            self._records.append(record)
        else:
            self._records[existing_index] = record
        self._register_execution_chain_node(record)
        return copy.deepcopy(record)

    def _register_execution_chain_node(self, record: Dict[str, Any]) -> Dict[str, Any]:
        evidence_id = str(record.get("evidence_id") or "")
        verification_record = record.get("verification_record") if isinstance(record.get("verification_record"), dict) else {}
        replay_record = record.get("replay_record") if isinstance(record.get("replay_record"), dict) else {}
        node_id = hashlib.sha256(f"readonly_execution|{evidence_id}".encode("utf-8")).hexdigest()
        node = {
            "node_id": node_id,
            "node_type": "readonly_execution",
            "evidence_id": evidence_id,
            "command": record.get("command", ""),
            "normalized_command": record.get("normalized_command", ""),
            "status": record.get("status", ""),
            "executed": bool(record.get("executed", False)),
            "returncode": record.get("returncode"),
            "verification_status": verification_record.get("verification_status", ""),
            "replayable": bool(replay_record.get("replayable", False)),
            "created_at": _zero_readonly_now(),
        }
        self._chain_nodes_by_id[node_id] = node
        self._execution_node_by_evidence_id[evidence_id] = node
        existing_index = next(
            (idx for idx, item in enumerate(self.execution_chain_nodes) if item.get("node_id") == node_id),
            None,
        )
        if existing_index is None:
            self.execution_chain_nodes.append(node)
        else:
            self.execution_chain_nodes[existing_index] = node
        return node

    def _register_replay_chain_node(self, report: Dict[str, Any]) -> Dict[str, Any]:
        evidence_id = str(report.get("evidence_id") or "")
        replay_report_id = str(report.get("replay_report_id") or "")
        node_id = hashlib.sha256(f"readonly_replay_validation|{replay_report_id}".encode("utf-8")).hexdigest()
        node = {
            "node_id": node_id,
            "node_type": "readonly_replay_validation",
            "evidence_id": evidence_id,
            "replay_report_id": replay_report_id,
            "replay_validation_status": report.get("replay_validation_status", ""),
            "replay_executed": bool(report.get("replay_executed", False)),
            "returncode_match": bool(report.get("returncode_match", False)),
            "stdout_digest_match": bool(report.get("stdout_digest_match", False)),
            "stderr_digest_match": bool(report.get("stderr_digest_match", False)),
            "created_at": _zero_readonly_now(),
        }
        self._chain_nodes_by_id[node_id] = node
        self.execution_chain_nodes.append(node)

        execution_node = self._execution_node_by_evidence_id.get(evidence_id)
        if isinstance(execution_node, dict):
            edge_id = hashlib.sha256(
                f"replay_validation_of|{node_id}|{execution_node.get('node_id')}|{evidence_id}".encode("utf-8")
            ).hexdigest()
            edge = {
                "edge_id": edge_id,
                "edge_type": "replay_validation_of",
                "from_node_id": node_id,
                "to_node_id": execution_node.get("node_id", ""),
                "evidence_id": evidence_id,
                "created_at": _zero_readonly_now(),
            }
            self.execution_chain_edges.append(edge)
        return node

    def list_records(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._records)

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        record = self._by_record_id.get(str(record_id or ""))
        return copy.deepcopy(record) if isinstance(record, dict) else None

    def get_by_evidence_id(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        record = self._by_evidence_id.get(str(evidence_id or ""))
        return copy.deepcopy(record) if isinstance(record, dict) else None

    def query(
        self,
        *,
        status: Optional[str] = None,
        executed: Optional[bool] = None,
        command_contains: Optional[str] = None,
        replayable: Optional[bool] = None,
        verification_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        needle = str(command_contains or "").lower()
        for record in self._records:
            try:
                if status is not None and str(record.get("status") or "") != str(status):
                    continue
                if executed is not None and bool(record.get("executed", False)) is not bool(executed):
                    continue
                if needle and needle not in str(record.get("command") or "").lower():
                    continue
                replay_record = record.get("replay_record") if isinstance(record.get("replay_record"), dict) else {}
                if replayable is not None and bool(replay_record.get("replayable", False)) is not bool(replayable):
                    continue
                verification_record = (
                    record.get("verification_record") if isinstance(record.get("verification_record"), dict) else {}
                )
                if verification_status is not None and str(verification_record.get("verification_status") or "") != str(verification_status):
                    continue
                results.append(copy.deepcopy(record))
            except Exception:
                continue
        return results

    def build_replay_request(self, evidence_id: str) -> Dict[str, Any]:
        record = self.get_by_evidence_id(evidence_id)
        if not isinstance(record, dict):
            return {
                "replay_request_type": "readonly_command_replay_request",
                "evidence_id": str(evidence_id or ""),
                "replayable": False,
                "deny_reason": "evidence record not found",
            }

        replay_record = record.get("replay_record") if isinstance(record.get("replay_record"), dict) else {}
        replayable = bool(replay_record.get("replayable", False))
        request = {
            "replay_request_type": "readonly_command_replay_request",
            "evidence_id": record.get("evidence_id", ""),
            "replayable": replayable,
            "replay_command": replay_record.get("replay_command", record.get("command", "")),
            "replay_normalized_command": replay_record.get("replay_normalized_command", record.get("normalized_command", "")),
            "replay_argv": list(replay_record.get("replay_argv") if isinstance(replay_record.get("replay_argv"), list) else []),
            "replay_cwd": replay_record.get("replay_cwd", ""),
            "expected_returncode": replay_record.get("expected_returncode"),
            "expected_stdout_digest": replay_record.get("expected_stdout_digest", ""),
            "expected_stderr_digest": replay_record.get("expected_stderr_digest", ""),
            "replay_safety": replay_record.get("replay_safety", "readonly_only"),
        }
        if not replayable:
            request["deny_reason"] = "evidence record is not replayable"
        return request

    def build_verification_lineage(self, evidence_id: str) -> Dict[str, Any]:
        record = self.get_by_evidence_id(evidence_id)
        if not isinstance(record, dict):
            return {
                "lineage_type": "readonly_execution_verification_lineage",
                "evidence_id": str(evidence_id or ""),
                "command": "",
                "normalized_command": "",
                "status": "missing",
                "executed": False,
                "verification_status": "missing",
                "checks": {},
                "stdout_digest": "",
                "stderr_digest": "",
                "returncode": None,
            }

        execution_record = record.get("execution_record") if isinstance(record.get("execution_record"), dict) else {}
        verification_record = record.get("verification_record") if isinstance(record.get("verification_record"), dict) else {}
        return {
            "lineage_type": "readonly_execution_verification_lineage",
            "evidence_id": record.get("evidence_id", ""),
            "command": record.get("command", ""),
            "normalized_command": record.get("normalized_command", ""),
            "status": record.get("status", ""),
            "executed": bool(record.get("executed", False)),
            "verification_status": verification_record.get("verification_status", ""),
            "checks": copy.deepcopy(verification_record.get("checks") if isinstance(verification_record.get("checks"), dict) else {}),
            "stdout_digest": execution_record.get("stdout_digest", ""),
            "stderr_digest": execution_record.get("stderr_digest", ""),
            "returncode": record.get("returncode"),
        }

    def replay(self, evidence_id: str, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        report = replay_readonly_execution_from_registry(
            self,
            evidence_id,
            timeout_seconds=timeout_seconds,
        )
        self._replay_reports.append(copy.deepcopy(report))
        self._register_replay_chain_node(report)
        return report

    def validate_replay(self, evidence_id: str, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        return self.replay(evidence_id, timeout_seconds=timeout_seconds)

    def list_replay_reports(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._replay_reports)

    def get_replay_reports(self, evidence_id: str) -> List[Dict[str, Any]]:
        return [
            copy.deepcopy(report)
            for report in self._replay_reports
            if str(report.get("evidence_id") or "") == str(evidence_id or "")
        ]

    def list_execution_chain_nodes(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.execution_chain_nodes)

    def list_execution_chain_edges(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.execution_chain_edges)

    def get_execution_chain_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        node = self._chain_nodes_by_id.get(str(node_id or ""))
        return copy.deepcopy(node) if isinstance(node, dict) else None

    def get_execution_chain_for_evidence(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        execution_node = self._execution_node_by_evidence_id.get(evidence_id)
        if not isinstance(execution_node, dict):
            return {
                "chain_type": "readonly_execution_chain",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "execution_node": {},
                "replay_nodes": [],
                "edges": [],
                "replay_report_count": 0,
                "latest_replay_validation_status": "",
            }
        replay_nodes = [
            copy.deepcopy(node)
            for node in self.execution_chain_nodes
            if node.get("node_type") == "readonly_replay_validation" and node.get("evidence_id") == evidence_id
        ]
        edges = [
            copy.deepcopy(edge)
            for edge in self.execution_chain_edges
            if edge.get("evidence_id") == evidence_id
        ]
        latest_status = str(replay_nodes[-1].get("replay_validation_status") or "") if replay_nodes else ""
        return {
            "chain_type": "readonly_execution_chain",
            "evidence_id": evidence_id,
            "found": True,
            "execution_node": copy.deepcopy(execution_node),
            "replay_nodes": replay_nodes,
            "edges": edges,
            "replay_report_count": len(replay_nodes),
            "latest_replay_validation_status": latest_status,
        }

    def build_execution_ancestry(self, evidence_id: str) -> Dict[str, Any]:
        chain = self.get_execution_chain_for_evidence(evidence_id)
        if not bool(chain.get("found", False)):
            return {
                "ancestry_type": "readonly_execution_ancestry",
                "evidence_id": str(evidence_id or ""),
                "found": False,
                "reason": "evidence id not found",
                "root_execution_node": {},
                "validation_nodes": [],
                "edge_count": 0,
                "validation_count": 0,
                "latest_validation_status": "",
                "has_mismatch": False,
                "has_timeout": False,
                "has_blocked_replay": False,
            }
        validation_nodes = list(chain.get("replay_nodes") or [])
        statuses = [str(node.get("replay_validation_status") or "") for node in validation_nodes]
        return {
            "ancestry_type": "readonly_execution_ancestry",
            "evidence_id": chain.get("evidence_id", ""),
            "found": True,
            "root_execution_node": copy.deepcopy(chain.get("execution_node", {})),
            "validation_nodes": validation_nodes,
            "edge_count": len(chain.get("edges") or []),
            "validation_count": len(validation_nodes),
            "latest_validation_status": statuses[-1] if statuses else "",
            "has_mismatch": "mismatch" in statuses,
            "has_timeout": "timeout" in statuses,
            "has_blocked_replay": "blocked" in statuses,
        }

    def build_replay_lineage(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        if evidence_id not in self._by_evidence_id:
            return {
                "lineage_type": "readonly_replay_lineage",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "replay_reports": [],
                "validation_statuses": [],
                "latest_report": {},
                "latest_validation_status": "",
                "mismatch_count": 0,
                "timeout_count": 0,
                "blocked_count": 0,
                "passed_count": 0,
            }
        reports = self.get_replay_reports(evidence_id)
        statuses = [str(report.get("replay_validation_status") or "") for report in reports]
        return {
            "lineage_type": "readonly_replay_lineage",
            "evidence_id": evidence_id,
            "found": True,
            "replay_reports": reports,
            "validation_statuses": statuses,
            "latest_report": copy.deepcopy(reports[-1]) if reports else {},
            "latest_validation_status": statuses[-1] if statuses else "",
            "mismatch_count": statuses.count("mismatch"),
            "timeout_count": statuses.count("timeout"),
            "blocked_count": statuses.count("blocked"),
            "passed_count": statuses.count("passed"),
        }

    def evaluate_execution_health(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        record = self.get_by_evidence_id(evidence_id)
        if not isinstance(record, dict):
            return {
                "evaluation_type": "runtime_execution_health",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "command": "",
                "normalized_command": "",
                "executed": False,
                "verification_status": "unknown",
                "replay_validation_count": 0,
                "passed_replay_count": 0,
                "mismatch_count": 0,
                "timeout_count": 0,
                "blocked_count": 0,
                "replay_success_rate": 0.0,
                "health_status": "unknown",
                "health_score": 0.0,
                "reasons": ["evidence id not found"],
                "warnings": [],
            }
        lineage = self.build_replay_lineage(evidence_id)
        verification_record = record.get("verification_record") if isinstance(record.get("verification_record"), dict) else {}
        passed = int(lineage.get("passed_count", 0) or 0)
        mismatch = int(lineage.get("mismatch_count", 0) or 0)
        timeout = int(lineage.get("timeout_count", 0) or 0)
        blocked = int(lineage.get("blocked_count", 0) or 0)
        replay_count = len(lineage.get("replay_reports") or [])
        success_rate = passed / replay_count if replay_count else 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        if replay_count == 0:
            health_status = "unknown"
            health_score = 0.25
            reasons.append("no replay validation available")
        elif blocked:
            health_status = "blocked"
            health_score = 0.2
            reasons.append("blocked replay detected")
        elif mismatch:
            health_status = "unstable" if mismatch >= passed else "degraded"
            health_score = min(0.5, max(0.2, success_rate * 0.5))
            reasons.append("replay digest mismatch detected")
        elif timeout:
            health_status = "degraded"
            health_score = min(0.4, max(0.2, success_rate * 0.4))
            reasons.append("replay timeout detected")
            warnings.append("runtime replay timed out")
        elif success_rate >= 0.9:
            health_status = "healthy"
            health_score = 0.95
            reasons.append("replay validations passed")
        else:
            health_status = "degraded"
            health_score = max(0.3, success_rate * 0.7)
            reasons.append("insufficient replay success rate")

        return {
            "evaluation_type": "runtime_execution_health",
            "evidence_id": evidence_id,
            "found": True,
            "command": record.get("command", ""),
            "normalized_command": record.get("normalized_command", ""),
            "executed": bool(record.get("executed", False)),
            "verification_status": verification_record.get("verification_status", "unknown"),
            "replay_validation_count": replay_count,
            "passed_replay_count": passed,
            "mismatch_count": mismatch,
            "timeout_count": timeout,
            "blocked_count": blocked,
            "replay_success_rate": success_rate,
            "health_status": health_status,
            "health_score": float(max(0.0, min(1.0, health_score))),
            "reasons": reasons,
            "warnings": warnings,
        }

    def evaluate_replay_stability(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        if evidence_id not in self._by_evidence_id:
            return {
                "evaluation_type": "runtime_replay_stability",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "replay_count": 0,
                "deterministic_replay_count": 0,
                "mismatch_count": 0,
                "timeout_count": 0,
                "blocked_count": 0,
                "replay_stability_score": 0.0,
                "replay_stability_status": "unknown",
                "replay_deterministic": False,
                "reasons": ["evidence id not found"],
            }
        lineage = self.build_replay_lineage(evidence_id)
        replay_count = len(lineage.get("replay_reports") or [])
        passed = int(lineage.get("passed_count", 0) or 0)
        mismatch = int(lineage.get("mismatch_count", 0) or 0)
        timeout = int(lineage.get("timeout_count", 0) or 0)
        blocked = int(lineage.get("blocked_count", 0) or 0)
        reasons: List[str] = []
        if replay_count == 0:
            status = "unknown"
            score = 0.25
            reasons.append("no replay validation available")
        elif blocked:
            status = "blocked"
            score = 0.1
            reasons.append("blocked replay detected")
        elif mismatch:
            status = "unstable"
            score = 0.25
            reasons.append("digest mismatch detected")
        elif timeout:
            status = "partially_stable"
            score = 0.4
            reasons.append("timeout replay detected")
        elif passed == replay_count:
            status = "stable"
            score = 1.0
            reasons.append("all replay validations passed")
        else:
            status = "partially_stable"
            score = passed / replay_count if replay_count else 0.0
            reasons.append("partial replay validation success")
        return {
            "evaluation_type": "runtime_replay_stability",
            "evidence_id": evidence_id,
            "found": True,
            "replay_count": replay_count,
            "deterministic_replay_count": passed,
            "mismatch_count": mismatch,
            "timeout_count": timeout,
            "blocked_count": blocked,
            "replay_stability_score": float(max(0.0, min(1.0, score))),
            "replay_stability_status": status,
            "replay_deterministic": mismatch == 0,
            "reasons": reasons,
        }

    def evaluate_verification_confidence(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        record = self.get_by_evidence_id(evidence_id)
        if not isinstance(record, dict):
            return {
                "evaluation_type": "runtime_verification_confidence",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "verification_status": "unknown",
                "verification_confidence": 0.0,
                "confidence_level": "untrusted",
                "evidence_integrity": False,
                "replay_integrity": False,
                "verification_integrity": False,
                "reasons": ["evidence id not found"],
            }
        health = self.evaluate_execution_health(evidence_id)
        stability = self.evaluate_replay_stability(evidence_id)
        verification_record = record.get("verification_record") if isinstance(record.get("verification_record"), dict) else {}
        evidence_record = record.get("evidence_record") if isinstance(record.get("evidence_record"), dict) else {}
        replay_record = record.get("replay_record") if isinstance(record.get("replay_record"), dict) else {}
        reasons: List[str] = []
        evidence_integrity = bool(evidence_record.get("evidence_id"))
        replay_integrity = bool(replay_record) and bool(stability.get("replay_deterministic", False))
        verification_integrity = bool(verification_record.get("checks") or verification_record.get("verification_status"))
        if stability.get("blocked_count", 0):
            confidence = 0.0
            level = "untrusted"
            reasons.append("blocked replay detected")
        elif stability.get("mismatch_count", 0):
            confidence = 0.25
            level = "low"
            reasons.append("replay mismatch detected")
        elif stability.get("timeout_count", 0):
            confidence = 0.35
            level = "low"
            reasons.append("replay timeout detected")
        elif stability.get("replay_count", 0) == 0:
            confidence = 0.55
            level = "medium"
            reasons.append("no replay validation available")
        elif health.get("health_status") == "healthy" and verification_record.get("verification_status") in {"passed", "failed"}:
            confidence = 0.95
            level = "high"
            reasons.append("deterministic replay validations passed")
        else:
            confidence = 0.65
            level = "medium"
            reasons.append("partial verification confidence")
        return {
            "evaluation_type": "runtime_verification_confidence",
            "evidence_id": evidence_id,
            "found": True,
            "verification_status": verification_record.get("verification_status", "unknown"),
            "verification_confidence": float(max(0.0, min(1.0, confidence))),
            "confidence_level": level,
            "evidence_integrity": evidence_integrity,
            "replay_integrity": replay_integrity,
            "verification_integrity": verification_integrity,
            "reasons": reasons,
        }

    def evaluate_mutation_readiness(self, evidence_id: str) -> Dict[str, Any]:
        evidence_id = str(evidence_id or "")
        if evidence_id not in self._by_evidence_id:
            return {
                "evaluation_type": "runtime_mutation_readiness",
                "evidence_id": evidence_id,
                "found": False,
                "reason": "evidence id not found",
                "mutation_ready": False,
                "mutation_readiness_score": 0.0,
                "mutation_readiness_level": "unsafe",
                "governance_decision": "unsafe_runtime_state",
                "governance_reasons": ["evidence id not found"],
                "blockers": ["missing evidence"],
                "warnings": [],
            }
        health = self.evaluate_execution_health(evidence_id)
        stability = self.evaluate_replay_stability(evidence_id)
        confidence = self.evaluate_verification_confidence(evidence_id)
        replay_count = int(stability.get("replay_count", 0) or 0)
        blockers: List[str] = []
        warnings: List[str] = []
        reasons: List[str] = []
        if confidence.get("confidence_level") == "untrusted" or health.get("health_status") == "blocked":
            decision = "unsafe_runtime_state"
            level = "unsafe"
            ready = False
            score = 0.0
            blockers.append("untrusted or blocked runtime state")
        elif stability.get("mismatch_count", 0) or stability.get("timeout_count", 0) or stability.get("blocked_count", 0):
            decision = "deny_mutation"
            level = "blocked"
            ready = False
            score = 0.2
            blockers.append("replay instability detected")
        elif replay_count < 2:
            decision = "require_more_replay_validation"
            level = "guarded"
            ready = False
            score = 0.55
            warnings.append("at least two replay validations required")
        elif stability.get("replay_stability_status") == "stable" and confidence.get("confidence_level") == "high":
            decision = "allow_future_governed_mutation"
            level = "ready"
            ready = True
            score = 0.95
            reasons.append("stable replay and high verification confidence")
        else:
            decision = "require_more_replay_validation"
            level = "guarded"
            ready = False
            score = 0.5
            warnings.append("runtime requires additional validation")
        reasons.extend(health.get("reasons", []))
        reasons.extend(stability.get("reasons", []))
        reasons.extend(confidence.get("reasons", []))
        return {
            "evaluation_type": "runtime_mutation_readiness",
            "evidence_id": evidence_id,
            "found": True,
            "mutation_ready": ready,
            "mutation_readiness_score": float(max(0.0, min(1.0, score))),
            "mutation_readiness_level": level,
            "governance_decision": decision,
            "governance_reasons": reasons,
            "blockers": blockers,
            "warnings": warnings,
        }

    def evaluate_registry_health(self) -> Dict[str, Any]:
        records = self.list_records()
        if not records:
            return {
                "total_execution_records": 0,
                "total_replay_reports": len(self._replay_reports),
                "healthy_execution_count": 0,
                "degraded_execution_count": 0,
                "unstable_execution_count": 0,
                "blocked_execution_count": 0,
                "mutation_ready_count": 0,
                "mutation_blocked_count": 0,
                "registry_health_score": 0.0,
                "registry_governance_status": "guarded",
                "warnings": ["no execution records registered"],
            }
        health_items = [self.evaluate_execution_health(str(record.get("evidence_id") or "")) for record in records]
        readiness_items = [self.evaluate_mutation_readiness(str(record.get("evidence_id") or "")) for record in records]
        healthy = sum(1 for item in health_items if item.get("health_status") == "healthy")
        degraded = sum(1 for item in health_items if item.get("health_status") == "degraded")
        unstable = sum(1 for item in health_items if item.get("health_status") == "unstable")
        blocked = sum(1 for item in health_items if item.get("health_status") == "blocked")
        ready = sum(1 for item in readiness_items if item.get("mutation_ready") is True)
        mutation_blocked = sum(1 for item in readiness_items if item.get("governance_decision") in {"deny_mutation", "unsafe_runtime_state"})
        score = sum(float(item.get("health_score", 0.0) or 0.0) for item in health_items) / len(health_items)
        if mutation_blocked:
            status = "unsafe" if blocked or unstable else "degraded"
        elif ready == len(records):
            status = "healthy"
        elif degraded or unstable:
            status = "degraded"
        else:
            status = "guarded"
        return {
            "total_execution_records": len(records),
            "total_replay_reports": len(self._replay_reports),
            "healthy_execution_count": healthy,
            "degraded_execution_count": degraded,
            "unstable_execution_count": unstable,
            "blocked_execution_count": blocked,
            "mutation_ready_count": ready,
            "mutation_blocked_count": mutation_blocked,
            "registry_health_score": float(max(0.0, min(1.0, score))),
            "registry_governance_status": status,
            "warnings": [],
        }

    def evaluate_registry_governance_summary(self) -> Dict[str, Any]:
        return self.evaluate_registry_health()


def _zero_v922_replay_report(
    *,
    evidence_id: str,
    replayable: bool,
    replay_executed: bool,
    replay_command: str = "",
    replay_normalized_command: str = "",
    replay_argv: Optional[List[str]] = None,
    replay_cwd: str = "",
    status: str = "blocked",
    returncode: Optional[int] = None,
    stdout: str = "",
    stderr: str = "",
    expected_returncode: Any = None,
    expected_stdout_digest: str = "",
    expected_stderr_digest: str = "",
    deny_reason: str = "",
    duration_seconds: float = 0.0,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    stdout_record = _zero_readonly_sha256_preview(stdout)
    stderr_record = _zero_readonly_sha256_preview(stderr)
    replay_report_id = hashlib.sha256(
        "|".join(
            [
                str(evidence_id or ""),
                _zero_readonly_now(),
                str(status or ""),
                str(returncode),
                stdout_record["digest"],
                stderr_record["digest"],
            ]
        ).encode("utf-8")
    ).hexdigest()
    returncode_match = replay_executed and returncode == expected_returncode
    stdout_digest_match = replay_executed and stdout_record["digest"] == str(expected_stdout_digest or "")
    stderr_digest_match = replay_executed and stderr_record["digest"] == str(expected_stderr_digest or "")

    if status == "timeout":
        replay_validation_status = "timeout"
    elif status == "failed" and not replay_executed:
        replay_validation_status = "failed"
    elif not replayable or not replay_executed:
        replay_validation_status = "blocked"
    elif status == "failed" and returncode is None:
        replay_validation_status = "failed"
    elif returncode_match and stdout_digest_match and stderr_digest_match:
        replay_validation_status = "passed"
    else:
        replay_validation_status = "mismatch"

    return {
        "replay_report_type": "readonly_command_replay_validation",
        "replay_report_id": replay_report_id,
        "evidence_id": evidence_id,
        "replayable": replayable,
        "replay_executed": replay_executed,
        "replay_command": replay_command,
        "replay_normalized_command": replay_normalized_command,
        "replay_argv": list(replay_argv or []),
        "replay_cwd": replay_cwd,
        "status": status,
        "returncode": returncode,
        "stdout_digest": stdout_record["digest"],
        "stderr_digest": stderr_record["digest"],
        "stdout_preview": stdout_record["preview"],
        "stderr_preview": stderr_record["preview"],
        "expected_returncode": expected_returncode,
        "expected_stdout_digest": expected_stdout_digest,
        "expected_stderr_digest": expected_stderr_digest,
        "returncode_match": returncode_match,
        "stdout_digest_match": stdout_digest_match,
        "stderr_digest_match": stderr_digest_match,
        "replay_validation_status": replay_validation_status,
        "deny_reason": deny_reason,
        "duration_seconds": duration_seconds,
        "timeout_seconds": timeout_seconds,
    }


def _zero_v922_replay_argv_is_safe(argv: Any) -> bool:
    if not isinstance(argv, list) or not argv:
        return False
    if not all(isinstance(item, str) and item for item in argv):
        return False
    joined = " ".join(argv).lower()
    if any(token in joined for token in (">", ">>", "|", "&&", ";")):
        return False
    blocked_prefixes = (
        ["git", "commit"],
        ["git", "push"],
        ["git", "reset"],
        ["git", "checkout"],
        ["pip", "install"],
        ["npm", "install"],
        ["curl"],
        ["wget"],
        ["powershell"],
        ["cmd"],
        ["bash"],
        ["sh"],
    )
    lowered = [item.lower() for item in argv]
    for prefix in blocked_prefixes:
        if lowered[: len(prefix)] == prefix:
            return False
    return (
        lowered == ["git", "status", "--short"]
        or lowered[:3] == [sys.executable.lower(), "-m", "compileall"]
        or lowered[:3] == [sys.executable.lower(), "-m", "pytest"] and "--collect-only" in lowered
        or lowered[:1] == ["__internal_readonly__"] and len(lowered) == 2 and lowered[1] in {"pwd", "dir", "ls"}
    )


def replay_readonly_execution_from_registry(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
    *,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    timeout_seconds = int(timeout_seconds or 10)
    start = time.monotonic()
    request = registry.build_replay_request(evidence_id) if isinstance(registry, RuntimeEvidenceRegistry) else {
        "replayable": False,
        "deny_reason": "invalid registry",
    }

    replayable = bool(request.get("replayable", False))
    replay_argv = request.get("replay_argv")
    replay_command = str(request.get("replay_command") or "")
    replay_normalized_command = str(request.get("replay_normalized_command") or "")
    replay_cwd = str(request.get("replay_cwd") or "")
    expected_returncode = request.get("expected_returncode")
    expected_stdout_digest = str(request.get("expected_stdout_digest") or "")
    expected_stderr_digest = str(request.get("expected_stderr_digest") or "")

    if not replayable:
        return _zero_v922_replay_report(
            evidence_id=str(evidence_id or ""),
            replayable=False,
            replay_executed=False,
            replay_command=replay_command,
            replay_normalized_command=replay_normalized_command,
            replay_argv=replay_argv if isinstance(replay_argv, list) else [],
            replay_cwd=replay_cwd,
            expected_returncode=expected_returncode,
            expected_stdout_digest=expected_stdout_digest,
            expected_stderr_digest=expected_stderr_digest,
            deny_reason=str(request.get("deny_reason") or "evidence record is not replayable"),
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
        )

    if not _zero_v922_replay_argv_is_safe(replay_argv):
        return _zero_v922_replay_report(
            evidence_id=str(evidence_id or ""),
            replayable=True,
            replay_executed=False,
            replay_command=replay_command,
            replay_normalized_command=replay_normalized_command,
            replay_argv=[],
            replay_cwd=replay_cwd,
            expected_returncode=expected_returncode,
            expected_stdout_digest=expected_stdout_digest,
            expected_stderr_digest=expected_stderr_digest,
            deny_reason="invalid replay argv",
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
        )

    argv = list(replay_argv)
    if argv[:1] == ["__internal_readonly__"]:
        internal = _zero_v920_execute_internal_readonly_command(argv[1], replay_cwd or os.getcwd())
        return _zero_v922_replay_report(
            evidence_id=str(evidence_id or ""),
            replayable=True,
            replay_executed=True,
            replay_command=replay_command,
            replay_normalized_command=replay_normalized_command,
            replay_argv=argv,
            replay_cwd=replay_cwd,
            status="executed" if internal["returncode"] == 0 else "failed",
            returncode=internal["returncode"],
            stdout=internal["stdout"],
            stderr=internal["stderr"],
            expected_returncode=expected_returncode,
            expected_stdout_digest=expected_stdout_digest,
            expected_stderr_digest=expected_stderr_digest,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
        )

    try:
        from core.runtime.execution_gateway import safe_subprocess_run

        completed = safe_subprocess_run(
            argv,
            timeout=timeout_seconds,
            cwd=replay_cwd or None,
        )
        stdout = str(completed.get("stdout") or "")
        stderr = str(completed.get("stderr") or "")
        returncode = completed.get("returncode")
        if returncode is None and completed.get("error"):
            if not stderr:
                stderr = str(completed.get("error") or f"readonly replay timeout after {timeout_seconds} seconds")
            return _zero_v922_replay_report(
                evidence_id=str(evidence_id or ""),
                replayable=True,
                replay_executed=True,
                replay_command=replay_command,
                replay_normalized_command=replay_normalized_command,
                replay_argv=argv,
                replay_cwd=replay_cwd,
                status="timeout",
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                expected_returncode=expected_returncode,
                expected_stdout_digest=expected_stdout_digest,
                expected_stderr_digest=expected_stderr_digest,
                deny_reason="readonly replay timeout",
                duration_seconds=time.monotonic() - start,
                timeout_seconds=timeout_seconds,
            )
    except Exception as exc:
        return _zero_v922_replay_report(
            evidence_id=str(evidence_id or ""),
            replayable=True,
            replay_executed=False,
            replay_command=replay_command,
            replay_normalized_command=replay_normalized_command,
            replay_argv=argv,
            replay_cwd=replay_cwd,
            status="failed",
            returncode=None,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
            expected_returncode=expected_returncode,
            expected_stdout_digest=expected_stdout_digest,
            expected_stderr_digest=expected_stderr_digest,
            deny_reason="readonly replay execution failed",
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
        )
    return _zero_v922_replay_report(
        evidence_id=str(evidence_id or ""),
        replayable=True,
        replay_executed=True,
        replay_command=replay_command,
        replay_normalized_command=replay_normalized_command,
        replay_argv=argv,
        replay_cwd=replay_cwd,
        status="executed" if returncode == 0 else "failed",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        expected_returncode=expected_returncode,
        expected_stdout_digest=expected_stdout_digest,
        expected_stderr_digest=expected_stderr_digest,
        duration_seconds=time.monotonic() - start,
        timeout_seconds=timeout_seconds,
    )


def build_runtime_evidence_registry() -> RuntimeEvidenceRegistry:
    return RuntimeEvidenceRegistry()


def register_runtime_execution_result(
    registry: RuntimeEvidenceRegistry,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.register_execution_result(result)


def query_runtime_evidence_records(
    registry: RuntimeEvidenceRegistry,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        return []
    return registry.query(**kwargs)


def reconstruct_replay_from_evidence_record(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.build_replay_request(evidence_id)


def build_verification_lineage(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.build_verification_lineage(evidence_id)


def build_execution_ancestry(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.build_execution_ancestry(evidence_id)


def build_replay_lineage(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.build_replay_lineage(evidence_id)


def evaluate_runtime_execution_health(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.evaluate_execution_health(evidence_id)


def evaluate_runtime_replay_stability(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.evaluate_replay_stability(evidence_id)


def evaluate_runtime_verification_confidence(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.evaluate_verification_confidence(evidence_id)


def evaluate_runtime_mutation_readiness(
    registry: RuntimeEvidenceRegistry,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(registry, RuntimeEvidenceRegistry):
        registry = RuntimeEvidenceRegistry()
    return registry.evaluate_mutation_readiness(evidence_id)


TaskRuntime.build_runtime_evidence_registry = staticmethod(build_runtime_evidence_registry)
TaskRuntime.register_runtime_execution_result = staticmethod(register_runtime_execution_result)
TaskRuntime.query_runtime_evidence_records = staticmethod(query_runtime_evidence_records)
TaskRuntime.reconstruct_replay_from_evidence_record = staticmethod(reconstruct_replay_from_evidence_record)
TaskRuntime.build_verification_lineage = staticmethod(build_verification_lineage)
TaskRuntime.replay_readonly_execution_from_registry = staticmethod(replay_readonly_execution_from_registry)
TaskRuntime.build_execution_ancestry = staticmethod(build_execution_ancestry)
TaskRuntime.build_replay_lineage = staticmethod(build_replay_lineage)
TaskRuntime.evaluate_runtime_execution_health = staticmethod(evaluate_runtime_execution_health)
TaskRuntime.evaluate_runtime_replay_stability = staticmethod(evaluate_runtime_replay_stability)
TaskRuntime.evaluate_runtime_verification_confidence = staticmethod(evaluate_runtime_verification_confidence)
TaskRuntime.evaluate_runtime_mutation_readiness = staticmethod(evaluate_runtime_mutation_readiness)
