from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.failure_policy import FailurePolicy
from core.runtime.audit_log import AuditLogger
from core.runtime.runtime_state_guard import RuntimeStateGuard, validate_runtime_state
from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy, RuntimeTransitionPolicyError
from core.runtime.runtime_persistence_service import RuntimePersistenceService


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


class TaskRuntime:
    def __init__(
        self,
        workspace_root: str = "workspace",
        debug: bool = False,
        trace_log_filename: str = "task_runtime_trace.log",
        evidence_adapter: Any = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.debug = debug
        self.trace_log_filename = trace_log_filename
        self.evidence_adapter = evidence_adapter
        self.state_machine = RuntimeStateMachine(debug=debug)
        self.audit = AuditLogger(workspace_root=self.workspace_root)
        self.state_guard = RuntimeStateGuard()
        self.transition_policy = RuntimeTransitionPolicy()
        self.persistence = RuntimePersistenceService(
            workspace_root=self.workspace_root,
            source="task_runtime",
        )

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

        next_index = idx + 1
        state["current_step_index"] = next_index
        state["updated_at"] = self._now()

        if next_index >= len(steps):
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
    ) -> Dict[str, Any]:
        state = self.load_runtime_state(task)
        state = self._sync_steps_from_task(task, state)
        state = self._sync_loop_fields_from_task(task, state)
        state = self._stamp_runtime_ownership(state, owner="task_runtime", action="mark_finished")

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
            **self._runtime_transition_metadata(state, "mark_finished"),
        }
        self._emit_task_runtime_evidence("completed", task=task, state=state)
        return result


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
        }
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
            if status not in {"pending", "running", "finished", "failed", "blocked", "skipped"}:
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
        if status not in {"running", "finished", "failed", "blocked"}:
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
            context["engineering_goal_state"] = self._refresh_goal_state_summary(goal_state, final_status="finished")
            state["repair_context"] = context
            state = self.apply_runtime_transition(
                task,
                state,
                owner="task_runtime",
                action="subgoal_flow_finished",
                updates={
                    "current_step_index": len(steps),
                    "status": "finished",
                },
                save=True,
            )
            return {"ok": True, "status": "finished", "runtime_state": state, "task": copy.deepcopy(task)}

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
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                return copy.deepcopy(default)

    def _write_json(self, file_path: str, data: Any) -> None:
        try:
            self._persistence_for_path(file_path).write_json(
                file_path,
                data,
                reason="task_runtime_write_json",
                lineage={
                    "source": "task_runtime",
                    "operation": "write_json",
                    "target_path": str(file_path),
                },
                provenance={
                    "source": "task_runtime",
                    "operation": "write_json",
                    "target_path": str(file_path),
                },
                metadata={
                    "task_runtime": True,
                    "runtime_state_persistence": True,
                },
            )
            return
        except Exception:
            if self._is_path_under_root(file_path, self.workspace_root):
                raise
            self._write_json_direct(file_path, data)

    def _write_json_direct(self, file_path: str, data: Any) -> None:
        """Compatibility fallback for explicit external task artifact paths.

        Some tests and legacy callers construct TaskRuntime with a workspace root
        such as ``<tmp>/workspace`` while passing task_dir under sibling
        ``<tmp>/tasks/...``.  The governed persistence path can reject those
        artifacts when rollback/capability scopes are intentionally narrow.
        This fallback is limited to paths outside the configured workspace root
        and keeps the write atomic for runtime_state.json compatibility.
        """
        target = os.path.abspath(str(file_path))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{target}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)

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


def _zero_v910_mark_finished(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, final_answer: str = '', final_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = _ZERO_V910_ORIGINAL_MARK_FINISHED(self, task, current_tick=current_tick, final_answer=final_answer, final_result=final_result)
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


def _zero_v912_mark_finished(self: TaskRuntime, task: Dict[str, Any], current_tick: int = 0, final_answer: str = '', final_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = _ZERO_V912_ORIGINAL_MARK_FINISHED(self, task, current_tick=current_tick, final_answer=final_answer, final_result=final_result)
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
