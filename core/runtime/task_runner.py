from __future__ import annotations

import copy
import json
import os
import re
import shlex
import subprocess
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.agent.capability_invoker import execute_resolved_capability
from core.memory.step_reflection_engine import StepReflectionEngine
from core.runtime.failure_policy import FailurePolicy
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime
from core.runtime.audit_log import AuditLogger
from core.runtime.repair_planner import RepairPlanner
from core.runtime.repair_step_injector import RepairStepInjector

MAX_PUBLIC_LIST_ITEMS = 20
MAX_PUBLIC_TRACE_ITEMS = 100
MAX_PUBLIC_TEXT_CHARS = 12000


class TaskRunner:
    DEFAULT_POLICY: Dict[str, Dict[str, Any]] = {
        "transient_error": {"retry": True, "replan": False, "wait": False, "fail": False},
        "tool_error": {"retry": True, "replan": True, "wait": False, "fail": False},
        "validation_error": {"retry": False, "replan": True, "wait": False, "fail": False},
        "dependency_unmet": {"retry": False, "replan": False, "wait": True, "fail": False},
        "timeout": {"retry": True, "replan": False, "wait": False, "fail": False},
        "unsafe_action": {"retry": False, "replan": False, "wait": False, "fail": True},
        "unsafe_action_blocked": {"retry": False, "replan": False, "wait": False, "fail": True},
        "cancelled": {"retry": False, "replan": False, "wait": False, "fail": True},
        "internal_error": {"retry": False, "replan": False, "wait": False, "fail": True},
    }

    READ_ONLY_STEP_TYPES = {"read_file", "list_files", "inspect", "analyze", "search", "verify"}
    SIDE_EFFECT_STEP_TYPES = {"command", "write_file", "delete_file", "call_api", "shell", "run_python", "code_chain_repair", "autonomous_code_repair"}

    def __init__(
        self,
        step_executor: Optional[StepExecutor] = None,
        replanner: Any = None,
        verifier: Any = None,
        debug: bool = False,
        task_runtime: Optional[TaskRuntime] = None,
        reflection_engine: Optional[StepReflectionEngine] = None,
    ) -> None:
        self.runtime = task_runtime if task_runtime else TaskRuntime(debug=debug)
        self.step_executor = step_executor if step_executor else StepExecutor()
        self.replanner = replanner
        self.verifier = verifier
        self.debug = debug
        self.reflection_engine = reflection_engine if reflection_engine else StepReflectionEngine()
        self.audit = AuditLogger(workspace_root=getattr(self.runtime, "workspace_root", "workspace"))
        self.repair_planner = RepairPlanner()
        self.repair_step_injector = RepairStepInjector()

    # ============================================================
    # main loop
    # ============================================================

    def run_task_tick(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        try:
            # Q package: persistence/resume gate.
            # Load the saved runtime state before mutating it so a restarted
            # process can preserve terminal/waiting states and resume only when
            # the previous loop explicitly requested run_next_tick.
            state = self.runtime.load_runtime_state(task)
            self._ensure_execution_trace_defaults(task, state)

            status = str(state.get("status") or "").strip().lower()
            next_action = str(state.get("next_action") or "").strip().lower()
            active_blocker_count = self._safe_int(state.get("active_blocker_count"), 0)
            blockers = state.get("blockers") if isinstance(state.get("blockers"), list) else []

            if status in {"waiting", "waiting_blocker", "waiting_review", "blocked", "paused"}:
                if next_action != "run_next_tick" or active_blocker_count > 0 or blockers:
                    return self._finalize_public_result({
                        "ok": True,
                        "action": "blocked_waiting",
                        "task": copy.deepcopy(task),
                        "runtime_state": state,
                        "status": status,
                        "next_action": next_action or "wait_for_external_event",
                        "blockers": copy.deepcopy(blockers),
                    })

            if status in {"finished", "done", "success", "completed"}:
                return self._finalize_public_result({
                    "ok": True,
                    "action": "already_finished",
                    "task": copy.deepcopy(task),
                    "runtime_state": state,
                    "status": "finished",
                    "final_answer": str(state.get("final_answer") or ""),
                    "execution_trace": copy.deepcopy(state.get("execution_trace", []))
                    if isinstance(state.get("execution_trace"), list)
                    else [],
                })

            if status in {"failed", "error", "cancelled", "canceled", "timeout"}:
                return self._finalize_public_result({
                    "ok": False,
                    "action": "already_terminal",
                    "task": copy.deepcopy(task),
                    "runtime_state": state,
                    "status": status,
                    "error": str(state.get("last_error") or state.get("failure_message") or status),
                    "execution_trace": copy.deepcopy(state.get("execution_trace", []))
                    if isinstance(state.get("execution_trace"), list)
                    else [],
                })

            run_result = self.runtime.mark_running(task, current_tick=current_tick)
            state = copy.deepcopy(run_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, state)

            capability_result = self._maybe_run_enabled_capability(
                task=task,
                state=state,
                current_tick=current_tick,
            )
            if capability_result is not None:
                return self._finalize_public_result(capability_result)

            result: Dict[str, Any] = {
                "ok": True,
                "action": "no_step_executed",
                "task": copy.deepcopy(task),
                "runtime_state": state,
                "status": str(state.get("status") or "running"),
            }

            max_auto_ticks = self._resolve_max_auto_ticks(task=task, state=state)
            auto_tick_count = 0

            while auto_tick_count < max_auto_ticks:
                result = self._run_one_step(task, current_tick=current_tick + auto_tick_count)

                if not isinstance(result, dict):
                    result = {
                        "ok": False,
                        "action": "invalid_result",
                        "task": copy.deepcopy(task),
                        "runtime_state": self.runtime.load_runtime_state(task),
                        "status": "failed",
                        "error": "TaskRunner._run_one_step returned invalid result",
                    }
                    break

                runtime_state = result.get("runtime_state")
                if not isinstance(runtime_state, dict):
                    runtime_state = self.runtime.load_runtime_state(task)

                self._ensure_execution_trace_defaults(task, runtime_state)

                status = str(
                    runtime_state.get("status")
                    or result.get("status")
                    or ""
                ).strip().lower()

                action = str(result.get("action") or "").strip().lower()
                next_action = str(runtime_state.get("next_action") or "").strip().lower()

                if status in {
                    "finished",
                    "done",
                    "success",
                    "completed",
                    "failed",
                    "error",
                    "cancelled",
                    "canceled",
                    "timeout",
                    "blocked",
                    "waiting",
                    "waiting_blocker",
                    "waiting_review",
                    "paused",
                }:
                    break

                if action in {
                    "blocked_for_review",
                    "subgoal_blocked",
                    "step_failed",
                    "exception_failed",
                    "already_terminal",
                    "already_finished",
                    "task_finished",
                    "capability_executed",
                    "capability_failed",
                    "regression_verify_failed",
                    "strategy_retry",
                    "retry",
                    "replan",
                }:
                    break

                if next_action != "run_next_tick":
                    break

                auto_tick_count += 1

            if auto_tick_count >= max_auto_ticks:
                runtime_state = result.get("runtime_state")
                if isinstance(runtime_state, dict):
                    runtime_state["auto_tick_limit_reached"] = True
                    runtime_state["auto_tick_limit"] = max_auto_ticks
                    try:
                        runtime_state = self.runtime.save_runtime_state(task, runtime_state)
                    except Exception:
                        pass
                    result["runtime_state"] = runtime_state
                result["auto_tick_limit_reached"] = True
                result["auto_tick_limit"] = max_auto_ticks

            return self._finalize_public_result(result)

        except Exception as e:
            traceback.print_exc()

            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="internal_error",
                failure_message=str(e),
            )
            runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)

            return {
                "ok": False,
                "action": "exception_failed",
                "error": str(e),
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "failed",
            }

    # compatibility entrypoints
    def run_one_tick(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.run_task_tick(task=task, current_tick=current_tick)

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.run_task_tick(task=task, current_tick=current_tick)

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.run_task_tick(task=task, current_tick=current_tick)

    def run(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.run_task_tick(task=task, current_tick=current_tick)

    # ============================================================
    # capability execution
    # ============================================================

    def _resolve_max_auto_ticks(self, *, task: Dict[str, Any], state: Dict[str, Any]) -> int:
        """
        Resolve the maximum number of automatic runtime ticks for one public run() call.

        This turns TaskRunner from a single-step executor into a bounded autonomous
        continuation dispatcher:

            step_completed + next_action=run_next_tick
            -> continue executing the next step
            -> stop only at terminal / waiting / blocked / review states

        The limit prevents accidental infinite loops if runtime state gets stuck.
        """
        raw_value = None

        if isinstance(task, dict):
            raw_value = (
                task.get("max_auto_ticks")
                or task.get("max_runtime_ticks")
                or task.get("auto_tick_limit")
            )

        if raw_value is None and isinstance(state, dict):
            raw_value = (
                state.get("max_auto_ticks")
                or state.get("max_runtime_ticks")
                or state.get("auto_tick_limit")
            )

        if raw_value is None:
            raw_value = 32

        try:
            value = int(raw_value)
        except Exception:
            value = 32

        if value < 1:
            return 1

        if value > 128:
            return 128

        return value

    def _maybe_run_enabled_capability(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        capability_execution = self._get_capability_execution(task, state)
        if not capability_execution.get("enabled"):
            return None

        route = self._get_capability_route(task, state)
        input_path = capability_execution.get("input_path")
        summary_output_path = capability_execution.get("summary_output_path")
        action_items_output_path = capability_execution.get("action_items_output_path")

        execution_result = execute_resolved_capability(
            route=route,
            input_path=input_path,
            summary_output_path=summary_output_path,
            action_items_output_path=action_items_output_path,
        )

        result_payload = self._make_json_safe(execution_result.to_dict())
        capability_execution = copy.deepcopy(capability_execution)
        capability_execution["enabled"] = False
        capability_execution["status"] = "finished" if execution_result.ok else "failed"
        capability_execution["last_result"] = copy.deepcopy(result_payload)
        capability_execution["error"] = execution_result.error

        task["capability_execution"] = copy.deepcopy(capability_execution)
        state["capability_execution"] = copy.deepcopy(capability_execution)

        final_answer = self._format_capability_final_answer(result_payload)

        if execution_result.ok:
            finish_result = self.runtime.mark_finished(
                task=task,
                current_tick=current_tick,
                final_answer=final_answer,
                final_result={
                    "ok": True,
                    "step_type": "capability",
                    "capability": execution_result.capability,
                    "operation": execution_result.operation,
                    "registry_operation": execution_result.registry_operation,
                    "result": copy.deepcopy(result_payload),
                    "final_answer": final_answer,
                    "execution_trace": [
                        {
                            "step_index": self._safe_int(state.get("current_step_index", 0), 0),
                            "step_type": "capability",
                            "ok": True,
                            "message": "controlled capability execution completed",
                            "final_answer": final_answer,
                            "error_type": "",
                            "classification": None,
                            "attempts": 1,
                            "max_attempts": 1,
                            "retry_used": False,
                        }
                    ],
                },
            )
            runtime_state = copy.deepcopy(finish_result.get("runtime_state", {}))
            runtime_state["capability_execution"] = copy.deepcopy(capability_execution)
            task["capability_execution"] = copy.deepcopy(capability_execution)

            try:
                runtime_state = self.runtime.save_runtime_state(task, runtime_state)
            except Exception:
                pass

            self._ensure_execution_trace_defaults(task, runtime_state)
            return {
                "ok": True,
                "action": "capability_executed",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "finished",
                "last_result": copy.deepcopy(result_payload),
                "final_answer": finish_result.get("final_answer", final_answer),
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        fail_result = self.runtime.mark_failed(
            task=task,
            current_tick=current_tick,
            failure_type="tool_error",
            failure_message=execution_result.error or "capability execution failed",
        )
        runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
        self._ensure_execution_trace_defaults(task, runtime_state)
        return {
            "ok": False,
            "action": "capability_failed",
            "task": copy.deepcopy(task),
            "runtime_state": runtime_state,
            "status": "failed",
            "error": execution_result.error,
            "last_result": copy.deepcopy(result_payload),
            "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
        }

    def _get_capability_execution(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        value = state.get("capability_execution") if isinstance(state, dict) else None
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)

        value = task.get("capability_execution") if isinstance(task, dict) else None
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)

        return {"enabled": False, "status": "metadata_only", "reason": ""}

    def _get_capability_route(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        route = task.get("route") if isinstance(task, dict) else None
        if isinstance(route, dict):
            return copy.deepcopy(route)

        route = state.get("route") if isinstance(state, dict) else None
        if isinstance(route, dict):
            return copy.deepcopy(route)

        capability = str(
            state.get("capability")
            or task.get("capability")
            or ""
        ).strip()
        operation = str(
            state.get("operation")
            or task.get("operation")
            or ""
        ).strip()

        capability_hint = state.get("capability_hint") if isinstance(state.get("capability_hint"), dict) else task.get("capability_hint")
        capability_registry_hint = (
            state.get("capability_registry_hint")
            if isinstance(state.get("capability_registry_hint"), dict)
            else task.get("capability_registry_hint")
        )

        built_route: Dict[str, Any] = {}
        if capability:
            built_route["capability"] = capability
        if operation:
            built_route["operation"] = operation
        if isinstance(capability_hint, dict):
            built_route["capability_hint"] = copy.deepcopy(capability_hint)
        if isinstance(capability_registry_hint, dict):
            built_route["capability_registry_hint"] = copy.deepcopy(capability_registry_hint)

        return built_route


    # ============================================================
    # target repo routing
    # ============================================================

    def _normalize_target_repo_root(self, value: Any) -> str:
        text = str(value or "").strip().strip('"').strip("'")
        if not text:
            return ""
        text = os.path.expandvars(os.path.expanduser(text))
        try:
            text = os.path.abspath(text)
        except Exception:
            pass
        if os.path.isdir(text):
            return os.path.normpath(text)
        return ""

    def _extract_target_repo_root_from_mapping(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ""

        for key in (
            "target_repo_root",
            "target_root",
            "repo_root",
            "project_root",
            "working_root",
            "workspace_target_root",
        ):
            resolved = self._normalize_target_repo_root(value.get(key))
            if resolved:
                return resolved

        for nested_key in ("config", "runtime_config", "engineering_config", "capability_execution"):
            nested = value.get(nested_key)
            if isinstance(nested, dict):
                resolved = self._extract_target_repo_root_from_mapping(nested)
                if resolved:
                    return resolved

        repair_context = value.get("repair_context")
        if isinstance(repair_context, dict):
            resolved = self._normalize_target_repo_root(repair_context.get("target_repo_root"))
            if resolved:
                return resolved
            engineering_execution = repair_context.get("engineering_execution")
            if isinstance(engineering_execution, dict):
                resolved = self._normalize_target_repo_root(engineering_execution.get("target_repo_root"))
                if resolved:
                    return resolved

        return ""

    def _resolve_target_repo_root(self, task: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> str:
        resolved = self._extract_target_repo_root_from_mapping(task)
        if resolved:
            return resolved

        resolved = self._extract_target_repo_root_from_mapping(state)
        if resolved:
            return resolved

        resolved = self._normalize_target_repo_root(os.environ.get("ZERO_TARGET_REPO_ROOT"))
        if resolved:
            return resolved

        return ""

    def _sync_target_repo_context(self, task: Dict[str, Any], state: Dict[str, Any]) -> str:
        target_repo_root = self._resolve_target_repo_root(task=task, state=state)
        if not target_repo_root:
            return ""

        if isinstance(task, dict):
            task["target_repo_root"] = target_repo_root

        if isinstance(state, dict):
            state["target_repo_root"] = target_repo_root
            repair_context = state.setdefault("repair_context", {})
            if isinstance(repair_context, dict):
                repair_context["target_repo_root"] = target_repo_root
                engineering_execution = repair_context.setdefault("engineering_execution", {})
                if isinstance(engineering_execution, dict):
                    engineering_execution["target_repo_root"] = target_repo_root
                    engineering_execution["target_routing_version"] = "aer_v9_2_0"
                    engineering_execution["last_target_routing_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return target_repo_root

    def _resolve_step_cwd(self, *, task: Dict[str, Any], state: Dict[str, Any], step: Any) -> str:
        target_repo_root = self._resolve_target_repo_root(task=task, state=state)

        if isinstance(step, dict):
            for key in ("cwd", "working_dir", "workdir"):
                value = str(step.get(key) or "").strip()
                if not value:
                    continue
                expanded = os.path.expandvars(os.path.expanduser(value))
                if os.path.isabs(expanded):
                    return os.path.normpath(expanded)
                if target_repo_root:
                    return os.path.normpath(os.path.join(target_repo_root, expanded))
                return os.path.normpath(expanded)

        if target_repo_root:
            return target_repo_root

        return str(state.get("task_dir") or "")

    def _target_routed_context(self, *, task: Dict[str, Any], state: Dict[str, Any], step: Any) -> Dict[str, Any]:
        target_repo_root = self._sync_target_repo_context(task=task, state=state)
        cwd = self._resolve_step_cwd(task=task, state=state, step=step)
        return {
            "cwd": cwd,
            "task_dir": state.get("task_dir"),
            "workspace_root": state.get("workspace_root") or getattr(self.runtime, "workspace_root", "workspace"),
            "target_repo_root": target_repo_root,
            "target_routing_enabled": bool(target_repo_root),
        }

    def _make_json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._make_json_safe(item) for key, item in value.items()}

        if isinstance(value, list):
            return [self._make_json_safe(item) for item in value]

        if isinstance(value, tuple):
            return [self._make_json_safe(item) for item in value]

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return self._make_json_safe(to_dict())
            except Exception:
                pass

        if hasattr(value, "__dict__"):
            try:
                raw = {
                    key: item
                    for key, item in vars(value).items()
                    if not str(key).startswith("_")
                }
                return self._make_json_safe(raw)
            except Exception:
                pass

        return str(value)

    def _format_capability_final_answer(self, result_payload: Dict[str, Any]) -> str:
        capability = str(result_payload.get("capability") or "").strip()
        operation = str(result_payload.get("operation") or "").strip()
        summary_output_path = str(result_payload.get("summary_output_path") or "").strip()
        action_items_output_path = str(result_payload.get("action_items_output_path") or "").strip()

        lines = [
            "Capability execution completed.",
            f"capability: {capability}",
            f"operation: {operation}",
        ]

        if summary_output_path:
            lines.append(f"summary_output_path: {summary_output_path}")
        if action_items_output_path:
            lines.append(f"action_items_output_path: {action_items_output_path}")

        return "\n".join(lines)


    # ============================================================
    # engineering execution action linkage
    # ============================================================

    def _runtime_step_action_type(self, step: Any) -> str:
        if not isinstance(step, dict):
            return "unknown"
        return str(step.get("type") or step.get("action") or step.get("operation") or "unknown").strip().lower() or "unknown"

    def _runtime_step_target(self, step: Any) -> str:
        if not isinstance(step, dict):
            return ""
        for key in ("target", "target_path", "path", "file_path", "output_path", "summary_output_path", "action_items_output_path", "command", "cmd"):
            value = step.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _runtime_step_id(self, step: Any, step_index: int) -> str:
        if isinstance(step, dict):
            for key in ("id", "step_id", "name"):
                value = step.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return "step_" + str(int(step_index))

    def _runtime_action_id(self, task: Dict[str, Any], step: Any, step_index: int) -> str:
        task_id = str(task.get("task_id") or task.get("id") or task.get("task_name") or "task").strip()
        return "action_" + task_id + "_" + self._runtime_step_id(step, step_index) + "_" + self._runtime_step_action_type(step)

    def _runtime_linked_session_node(self, task: Dict[str, Any], step: Any, step_index: int) -> str:
        if isinstance(step, dict):
            for key in ("linked_session_node", "session_node", "node_id", "repair_session_node"):
                value = step.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        repair_context = task.get("repair_context") if isinstance(task, dict) else {}
        if isinstance(repair_context, dict):
            repair_session = repair_context.get("repair_session")
            if isinstance(repair_session, dict):
                session_id = str(repair_session.get("session_id") or repair_session.get("id") or "").strip()
                if session_id:
                    return session_id + ":step_" + str(int(step_index))
        return ""

    def _runtime_action_metadata(self, step: Any, step_index: int, current_tick: int, trace_tick: int) -> Dict[str, Any]:
        return {
            "step_index": int(step_index),
            "current_tick": current_tick,
            "trace_tick": trace_tick,
            "step": copy.deepcopy(step) if isinstance(step, dict) else {},
        }

    def _safe_update_current_engineering_action(self, *, task: Dict[str, Any], step: Any, step_index: int, current_tick: int, trace_tick: int) -> None:
        fn = getattr(self.runtime, "update_current_engineering_action", None)
        if not callable(fn):
            return
        try:
            fn(
                task=task,
                action_type=self._runtime_step_action_type(step),
                target=self._runtime_step_target(step),
                step_id=self._runtime_step_id(step, step_index),
                action_id=self._runtime_action_id(task, step, step_index),
                linked_session_node=self._runtime_linked_session_node(task, step, step_index),
                metadata=self._runtime_action_metadata(step, step_index, current_tick, trace_tick),
            )
        except Exception:
            if self.debug:
                traceback.print_exc()

    def _safe_complete_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        fn = getattr(self.runtime, "complete_engineering_action", None)
        if not callable(fn):
            return
        try:
            fn(
                task=task,
                action_type=self._runtime_step_action_type(step),
                target=self._runtime_step_target(step),
                step_id=self._runtime_step_id(step, step_index),
                action_id=self._runtime_action_id(task, step, step_index),
                linked_session_node=self._runtime_linked_session_node(task, step, step_index),
                result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
                changed_files=self._extract_changed_files_from_step_result(step_result),
                tick=trace_tick if trace_tick is not None else current_tick,
                metadata=self._runtime_action_metadata(step, step_index, current_tick, trace_tick),
            )
        except Exception:
            if self.debug:
                traceback.print_exc()

    def _safe_fail_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        fn = getattr(self.runtime, "fail_engineering_action", None)
        if not callable(fn):
            return
        try:
            error = ""
            if isinstance(step_result, dict):
                error = self._stringify_failure_message(step_result.get("error") or step_result.get("message") or "")
            fn(
                task=task,
                action_type=self._runtime_step_action_type(step),
                target=self._runtime_step_target(step),
                step_id=self._runtime_step_id(step, step_index),
                action_id=self._runtime_action_id(task, step, step_index),
                linked_session_node=self._runtime_linked_session_node(task, step, step_index),
                error=error,
                result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
                tick=trace_tick if trace_tick is not None else current_tick,
                metadata=self._runtime_action_metadata(step, step_index, current_tick, trace_tick),
            )
        except Exception:
            if self.debug:
                traceback.print_exc()

    def _safe_block_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int, reason: str = "") -> None:
        fn = getattr(self.runtime, "block_engineering_action", None)
        if not callable(fn):
            return
        try:
            resolved_reason = str(reason or "").strip()
            if not resolved_reason and isinstance(step_result, dict):
                resolved_reason = str(step_result.get("policy_reason") or step_result.get("error") or step_result.get("message") or "blocked")
            fn(
                task=task,
                action_type=self._runtime_step_action_type(step),
                target=self._runtime_step_target(step),
                step_id=self._runtime_step_id(step, step_index),
                action_id=self._runtime_action_id(task, step, step_index),
                linked_session_node=self._runtime_linked_session_node(task, step_index=step_index, step=step),
                reason=resolved_reason,
                result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
                tick=trace_tick if trace_tick is not None else current_tick,
                metadata=self._runtime_action_metadata(step, step_index, current_tick, trace_tick),
            )
        except Exception:
            if self.debug:
                traceback.print_exc()

    def _safe_record_rollback_restore_action(self, *, task: Dict[str, Any], step: Any, rollback_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        fn = getattr(self.runtime, "record_rollback_restore_action", None)
        if not callable(fn):
            return
        try:
            fn(
                task=task,
                target=self._runtime_step_target(step),
                step_id=self._runtime_step_id(step, step_index) + ":rollback_restore",
                action_id=self._runtime_action_id(task, step, step_index) + "_rollback_restore",
                linked_session_node=self._runtime_linked_session_node(task, step, step_index),
                result=copy.deepcopy(rollback_result) if isinstance(rollback_result, dict) else {},
                changed_files=self._extract_changed_files_from_step_result(rollback_result),
                tick=trace_tick if trace_tick is not None else current_tick,
            )
        except Exception:
            if self.debug:
                traceback.print_exc()

    def _extract_changed_files_from_step_result(self, step_result: Any) -> List[str]:
        files: List[str] = []

        def _collect(value: Any) -> None:
            if isinstance(value, str) and value.strip():
                item = value.strip()
                if item not in files:
                    files.append(item)
                return
            if isinstance(value, list):
                for child in value:
                    _collect(child)
                return
            if isinstance(value, dict):
                for key in ("changed_files", "modified_files", "created_files", "written_files", "files"):
                    if key in value:
                        _collect(value.get(key))

        _collect(step_result)
        if isinstance(step_result, dict):
            for key in ("result", "rollback_result"):
                payload = step_result.get(key)
                if isinstance(payload, dict):
                    _collect(payload)
        return files

    # ============================================================
    # step execution
    # ============================================================

    def _run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.runtime.load_runtime_state(task)
        self._ensure_execution_trace_defaults(task, state)

        steps = state.get("steps", [])
        idx = int(state.get("current_step_index", 0) or 0)

        if not isinstance(steps, list):
            steps = []

        if idx >= len(steps):
            finish_result = self.runtime.mark_finished(
                task=task,
                current_tick=current_tick,
                final_answer=str(task.get("final_answer") or state.get("final_answer") or ""),
                final_result=copy.deepcopy(task.get("last_step_result") or state.get("last_step_result")),
            )
            runtime_state = copy.deepcopy(finish_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)
            return {
                "ok": True,
                "action": "already_finished",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "finished",
                "final_answer": finish_result.get("final_answer", ""),
            }

        prepare_result = self.runtime.prepare_current_subgoal(task=task, current_tick=current_tick)
        prepared_state = copy.deepcopy(prepare_result.get("runtime_state", state))
        self._ensure_execution_trace_defaults(task, prepared_state)
        if not bool(prepare_result.get("ok", False)):
            self._safe_block_engineering_action(
                task=task,
                step=steps[idx] if isinstance(steps, list) and 0 <= idx < len(steps) else {},
                step_result=copy.deepcopy(prepare_result),
                step_index=idx,
                current_tick=current_tick,
                trace_tick=current_tick,
                reason=str(prepare_result.get("reason") or prepared_state.get("last_error") or "subgoal blocked"),
            )
            return {
                "ok": False,
                "action": "subgoal_blocked",
                "task": copy.deepcopy(task),
                "runtime_state": prepared_state,
                "status": prepared_state.get("status", "blocked"),
                "error": prepare_result.get("reason") or prepared_state.get("last_error"),
                "execution_trace": copy.deepcopy(prepared_state.get("execution_trace", [])),
            }
        if str(prepared_state.get("status") or "").strip().lower() == "finished":
            return {
                "ok": True,
                "action": "already_finished",
                "task": copy.deepcopy(task),
                "runtime_state": prepared_state,
                "status": "finished",
                "final_answer": str(prepared_state.get("final_answer") or ""),
                "execution_trace": copy.deepcopy(prepared_state.get("execution_trace", [])),
            }
        state = prepared_state
        steps = state.get("steps", []) if isinstance(state.get("steps"), list) else []
        idx = int(state.get("current_step_index", idx) or idx)

        step = steps[idx]
        trace_tick = self._trace_tick_for_step(
            state=state,
            step_index=idx,
            current_tick=current_tick,
        )

        self._safe_update_current_engineering_action(
            task=task,
            step=step,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

        self._append_trace_json_event(
            task,
            "step_start",
            {
                "task_id": task.get("task_id") or task.get("id"),
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "steps_total": len(steps),
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
            },
        )
        self.audit.log_event(
            task,
            "step_start",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "steps_total": len(steps),
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
            },
            source="task_runner",
        )

        self.audit.log_event(
            task,
            "policy_check",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "step": copy.deepcopy(step) if isinstance(step, dict) else {},
            },
            source="policy_layer",
        )

        result = self.step_executor.execute_step(
            task=task,
            step=step,
            context=self._target_routed_context(task=task, state=state, step=step),
            previous_result=self._get_previous_result(state),
            step_index=idx,
            step_count=len(steps),
        )

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "error": "step_executor returned invalid result",
                "raw_result": result,
                "step": copy.deepcopy(step),
                "execution_trace": [],
            }

        result = self._ensure_step_execution_trace(step=step, step_result=result, step_index=idx)

        self._append_step_result_trace_json(
            task=task,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=trace_tick,
        )
        self.audit.log_event(
            task,
            "step_result",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                "error": copy.deepcopy(result.get("error")) if isinstance(result, dict) else "invalid_result",
            },
            source="task_runner",
        )

        self.audit.log_event(
            task,
            "policy_result",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                "error": copy.deepcopy(result.get("error")) if isinstance(result, dict) else "invalid_result",
                "guard_mode": str(result.get("guard_mode") or "") if isinstance(result, dict) else "",
                "policy_action": str(result.get("policy_action") or "") if isinstance(result, dict) else "",
                "policy_reason": str(result.get("policy_reason") or "") if isinstance(result, dict) else "",
            },
            source="policy_layer",
        )

        if self._should_convert_policy_block_to_review(result):
            review_id = self._build_policy_review_id(task=task, step_index=idx, current_tick=current_tick)
            review_payload = {
                "kind": "policy_blocked_action",
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "step": copy.deepcopy(step) if isinstance(step, dict) else {},
                "guard_mode": str(result.get("guard_mode") or ""),
                "policy_action": str(result.get("policy_action") or "deny"),
                "policy_reason": str(result.get("policy_reason") or result.get("error") or "policy blocked action"),
                "error": copy.deepcopy(result.get("error")),
            }

            self._safe_block_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
                reason=str(review_payload.get("policy_reason") or "policy blocked action"),
            )

            wait_result = self.runtime.mark_waiting_review(
                task=task,
                current_tick=current_tick,
                review_id=review_id,
                review_payload=review_payload,
                reason=str(review_payload.get("policy_reason") or "policy blocked action"),
            )
            runtime_state = copy.deepcopy(wait_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)

            self.audit.log_event(
                task,
                "policy_blocked_to_review",
                {
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "review_id": review_id,
                    "guard_mode": review_payload.get("guard_mode", ""),
                    "policy_action": review_payload.get("policy_action", "deny"),
                    "policy_reason": review_payload.get("policy_reason", ""),
                    "next_action": runtime_state.get("next_action", ""),
                    "status": runtime_state.get("status", ""),
                },
                source="policy_layer",
            )

            return {
                "ok": True,
                "action": "blocked_for_review",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": runtime_state.get("status", "waiting_review"),
                "next_action": runtime_state.get("next_action", "wait_for_external_event"),
                "requires_review": True,
                "review_id": runtime_state.get("review_id", review_id),
                "review_payload": copy.deepcopy(runtime_state.get("review_payload", review_payload)),
                "blockers": copy.deepcopy(runtime_state.get("blockers", [])),
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        if not result.get("ok") and self._should_advance_failed_step_observation(
            step=step,
            step_result=result,
            step_index=idx,
            step_count=len(steps),
        ):
            result["continued_after_failure"] = True
            result["observed_failure"] = True
            self._safe_fail_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
            )
            advance_result = self.runtime.advance_step(
                task=task,
                step_result=result,
                current_tick=current_tick,
            )
            runtime_state = copy.deepcopy(advance_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)
            return {
                "ok": True,
                "action": "step_failed_observed",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": runtime_state.get("status", "running"),
                "last_result": copy.deepcopy(result),
                "current_step_index": runtime_state.get("current_step_index", idx + 1),
                "steps_total": runtime_state.get("steps_total", len(steps)),
                "error": result.get("error"),
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        if not result.get("ok"):
            failure_type = self._determine_failure_type(step, result)
            decision = FailurePolicy.decide(failure_type)

            failure_decision = {
                "retry": decision.retry,
                "replan": decision.replan,
                "fail": decision.fail,
                "wait": decision.wait,
            }

            failure_status = "running"
            if decision.retry:
                failure_status = "retrying"
            elif decision.replan and self.replanner:
                failure_status = "replanning"

            failure_record_result = self.runtime.record_step_failure(
                task=task,
                step=step,
                step_result=result,
                current_tick=current_tick,
                status=failure_status,
            )
            state = copy.deepcopy(failure_record_result.get("runtime_state", {}))
            self._safe_fail_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
            )
            self._ensure_execution_trace_defaults(task, state)

            repair_injection_result = self._maybe_inject_repair_steps_after_failure(
                task=task,
                state=state,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
            )
            if isinstance(repair_injection_result, dict) and repair_injection_result.get("ok"):
                runtime_state = copy.deepcopy(repair_injection_result.get("runtime_state", state))
                self._ensure_execution_trace_defaults(task, runtime_state)
                return {
                    "ok": True,
                    "action": "repair_steps_injected",
                    "failure_type": failure_type,
                    "failure_decision": failure_decision,
                    "task": copy.deepcopy(task),
                    "runtime_state": runtime_state,
                    "status": runtime_state.get("status", "running"),
                    "last_result": copy.deepcopy(result),
                    "repair_plan": copy.deepcopy(repair_injection_result.get("repair_plan")),
                    "repair_injection": copy.deepcopy(repair_injection_result.get("repair_injection")),
                    "current_step_index": runtime_state.get("current_step_index", idx + 1),
                    "steps_total": runtime_state.get("steps_total"),
                    "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
                }

            rollback_result = None
            if self._should_rollback_after_failed_verify(step=step, step_result=result, state=state):
                rollback_result = self.runtime.rollback_last_apply(
                    task=task,
                    current_tick=current_tick,
                    verify_error=result.get("error") or result.get("message"),
                )
                state = copy.deepcopy(rollback_result.get("runtime_state", state))
                self._ensure_execution_trace_defaults(task, state)
                if bool(rollback_result.get("ok", False)):
                    self._safe_record_rollback_restore_action(
                        task=task,
                        step=step,
                        rollback_result=rollback_result,
                        step_index=idx,
                        current_tick=current_tick,
                        trace_tick=trace_tick,
                    )
                    strategy_result = self.runtime.advance_repair_strategy_after_failure(
                        task=task,
                        current_tick=current_tick,
                        failure_reason=result.get("error") or result.get("message"),
                    )
                    strategy_state = copy.deepcopy(strategy_result.get("runtime_state", state))
                    self._ensure_execution_trace_defaults(task, strategy_state)
                    if strategy_result.get("ok"):
                        return {
                            "ok": True,
                            "action": "strategy_retry",
                            "task": copy.deepcopy(task),
                            "runtime_state": strategy_state,
                            "status": "running",
                            "last_result": copy.deepcopy(result),
                            "rollback_result": copy.deepcopy(rollback_result.get("rollback_result")),
                            "next_strategy": strategy_result.get("next_strategy"),
                            "current_step_index": strategy_state.get("current_step_index"),
                            "execution_trace": copy.deepcopy(strategy_state.get("execution_trace", [])),
                        }
                    state = strategy_state
            elif self._is_apply_step(step):
                repair_context = state.get("repair_context") if isinstance(state, dict) else {}
                rollback = repair_context.get("rollback") if isinstance(repair_context, dict) else None
                if isinstance(rollback, dict) and bool(rollback.get("restore_available")):
                    rollback_result = self.runtime.rollback_last_apply(
                        task=task,
                        current_tick=current_tick,
                        verify_error=result.get("error") or result.get("message"),
                    )
                    state = copy.deepcopy(rollback_result.get("runtime_state", state))
                    self._ensure_execution_trace_defaults(task, state)

            self._trace(
                task,
                "failure_decision",
                {
                    "failure_type": failure_type,
                    "decision": failure_decision,
                    "error": result.get("error"),
                    "step_index": idx,
                },
            )
            self.audit.log_event(
                task,
                "failure_decision",
                {
                    "failure_type": failure_type,
                    "decision": copy.deepcopy(failure_decision),
                    "error": copy.deepcopy(result.get("error")),
                    "step_index": idx,
                },
                source="task_runner",
            )

            if decision.retry:
                runtime_state = self.runtime.load_runtime_state(task)
                self._ensure_execution_trace_defaults(task, runtime_state)
                return {
                    "ok": False,
                    "action": "retry",
                    "failure_type": failure_type,
                    "failure_decision": failure_decision,
                    "error": result.get("error"),
                    "task": copy.deepcopy(task),
                    "runtime_state": runtime_state,
                    "status": "retrying",
                    "last_result": copy.deepcopy(result),
                    "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
                }

            if decision.replan and self.replanner:
                try:
                    self.replanner.replan(
                        goal=state.get("goal"),
                        failed_step=step,
                        reason=result.get("error"),
                    )
                except Exception as e:
                    self._trace(
                        task,
                        "replan_failed",
                        {
                            "error": str(e),
                            "step_index": idx,
                        },
                    )

                runtime_state = self.runtime.load_runtime_state(task)
                self._ensure_execution_trace_defaults(task, runtime_state)
                return {
                    "ok": False,
                    "action": "replan",
                    "failure_type": failure_type,
                    "failure_decision": failure_decision,
                    "task": copy.deepcopy(task),
                    "runtime_state": runtime_state,
                    "status": "replanning",
                    "last_result": copy.deepcopy(result),
                    "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
                }

            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type=failure_type,
                failure_message=str(state.get("last_error") or self._stringify_failure_message(result.get("error"))),
            )

            fail_result["failure_decision"] = failure_decision
            if isinstance(rollback_result, dict):
                fail_result["rollback_result"] = copy.deepcopy(rollback_result.get("rollback_result"))
            runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)
            self._append_trace_json_event(
                task,
                "task_failed",
                {
                    "task_id": task.get("task_id") or task.get("id"),
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "failure_type": failure_type,
                    "error": result.get("error"),
                    "status": "failed",
                },
            )

            return {
                "ok": False,
                "action": "step_failed",
                "failure_type": failure_type,
                "failure_decision": failure_decision,
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "failed",
                "error": result.get("error"),
                "last_result": copy.deepcopy(result),
                "rollback_result": copy.deepcopy(rollback_result.get("rollback_result")) if isinstance(rollback_result, dict) else None,
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        advance_result = self.runtime.advance_step(
            task=task,
            step_result=result,
            current_tick=current_tick,
        )
        self._safe_complete_engineering_action(
            task=task,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        new_state = copy.deepcopy(advance_result.get("runtime_state", {}))
        self._ensure_execution_trace_defaults(task, new_state)
        if self._is_apply_step(step):
            regression_result = self._run_regression_verify_phase(
                task=task,
                state=new_state,
                current_tick=current_tick,
            )
            if regression_result is not None and not bool(regression_result.get("passed", False)):
                recorded = self.runtime.record_regression_verify(
                    task=task,
                    regression_result=regression_result,
                    current_tick=current_tick,
                )
                new_state = copy.deepcopy(recorded.get("runtime_state", new_state))
                rollback_result = self.runtime.rollback_last_apply(
                    task=task,
                    current_tick=current_tick,
                    verify_error=str(regression_result.get("error") or "regression verification failed"),
                )
                runtime_state = copy.deepcopy(rollback_result.get("runtime_state", new_state))
                self._ensure_execution_trace_defaults(task, runtime_state)
                if bool(rollback_result.get("ok", False)):
                    self._safe_record_rollback_restore_action(
                        task=task,
                        step=step,
                        rollback_result=rollback_result,
                        step_index=idx,
                        current_tick=current_tick,
                        trace_tick=trace_tick,
                    )
                    strategy_result = self.runtime.advance_repair_strategy_after_failure(
                        task=task,
                        current_tick=current_tick,
                        failure_reason=str(regression_result.get("error") or "regression verification failed"),
                    )
                    strategy_state = copy.deepcopy(strategy_result.get("runtime_state", runtime_state))
                    self._ensure_execution_trace_defaults(task, strategy_state)
                    if strategy_result.get("ok"):
                        return {
                            "ok": True,
                            "action": "strategy_retry",
                            "task": copy.deepcopy(task),
                            "runtime_state": strategy_state,
                            "status": "running",
                            "regression_verify": copy.deepcopy(regression_result),
                            "rollback_result": copy.deepcopy(rollback_result.get("rollback_result")),
                            "next_strategy": strategy_result.get("next_strategy"),
                            "execution_trace": copy.deepcopy(strategy_state.get("execution_trace", [])),
                        }
                    runtime_state = strategy_state
                return {
                    "ok": False,
                    "action": "regression_verify_failed",
                    "task": copy.deepcopy(task),
                    "runtime_state": runtime_state,
                    "status": "failed",
                    "error": runtime_state.get("last_error") or regression_result.get("error"),
                    "regression_verify": copy.deepcopy(regression_result),
                    "rollback_result": copy.deepcopy(rollback_result.get("rollback_result")),
                    "last_result": copy.deepcopy(result),
                    "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
                }
            if regression_result is not None:
                recorded = self.runtime.record_regression_verify(
                    task=task,
                    regression_result=regression_result,
                    current_tick=current_tick,
                )
                new_state = copy.deepcopy(recorded.get("runtime_state", new_state))

        new_status = str(new_state.get("status") or advance_result.get("status") or "running").strip().lower()

        if new_status == "finished":
            finish_result = self.runtime.mark_finished(
                task=task,
                current_tick=current_tick,
                final_answer=self._extract_final_answer_from_step_result(result),
                final_result=result,
            )
            runtime_state = copy.deepcopy(finish_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)
            self._append_trace_json_event(
                task,
                "task_finished",
                {
                    "task_id": task.get("task_id") or task.get("id"),
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "steps_total": len(steps),
                    "status": "finished",
                    "final_answer": finish_result.get("final_answer", ""),
                },
            )
            self.audit.log_event(
                task,
                "task_finished",
                {
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "steps_total": len(steps),
                    "final_answer": finish_result.get("final_answer", ""),
                },
                source="task_runner",
            )
            return {
                "ok": True,
                "action": "task_finished",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "finished",
                "last_result": copy.deepcopy(result),
                "final_answer": finish_result.get("final_answer", ""),
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        return {
            "ok": True,
            "action": "step_completed",
            "task": copy.deepcopy(task),
            "runtime_state": new_state,
            "status": new_status or "running",
            "last_result": copy.deepcopy(result),
            "current_step_index": new_state.get("current_step_index", idx + 1),
            "steps_total": new_state.get("steps_total", len(steps)),
            "final_answer": str(new_state.get("final_answer") or ""),
            "execution_trace": copy.deepcopy(new_state.get("execution_trace", [])),
        }

    # ============================================================
    # execution trace helpers
    # ============================================================

    def _ensure_execution_trace_defaults(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if isinstance(task, dict):
            task.setdefault("execution_trace", [])
        if isinstance(state, dict):
            state.setdefault("execution_trace", [])

    def _ensure_step_execution_trace(
        self,
        *,
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        step_index: int,
    ) -> Dict[str, Any]:
        normalized = copy.deepcopy(step_result)

        existing_trace = normalized.get("execution_trace")
        if isinstance(existing_trace, list):
            normalized["execution_trace"] = [copy.deepcopy(item) for item in existing_trace if isinstance(item, dict)]
            return normalized

        safe_step = copy.deepcopy(step) if isinstance(step, dict) else {}
        error_payload = normalized.get("error") if isinstance(normalized.get("error"), dict) else {}
        error_details = error_payload.get("details") if isinstance(error_payload.get("details"), dict) else {}
        retry_payload = normalized.get("retry") if isinstance(normalized.get("retry"), dict) else {}

        event: Dict[str, Any] = {
            "step_index": self._safe_int(normalized.get("step_index", step_index), step_index),
            "step_type": str(
                normalized.get("step_type")
                or safe_step.get("type")
                or ""
            ).strip().lower(),
            "ok": bool(normalized.get("ok", False)),
            "message": str(normalized.get("message") or ""),
            "final_answer": str(normalized.get("final_answer") or ""),
            "error_type": str(error_payload.get("type") or ""),
            "classification": error_details.get("classification"),
            "attempts": self._safe_int(retry_payload.get("attempts", 1), 1),
            "max_attempts": self._safe_int(retry_payload.get("max_attempts", 1), 1),
            "retry_used": bool(retry_payload.get("used", False)),
        }

        step_payload = normalized.get("step") if isinstance(normalized.get("step"), dict) else safe_step
        if isinstance(step_payload, dict):
            step_id = str(step_payload.get("id") or "").strip()
            if step_id:
                event["step_id"] = step_id

        normalized["execution_trace"] = [event]

        if isinstance(normalized.get("result"), dict):
            normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

        return normalized

    def _extract_trace_from_step_result(self, step_result: Any) -> List[Dict[str, Any]]:
        if not isinstance(step_result, dict):
            return []

        trace = step_result.get("execution_trace")
        if isinstance(trace, list):
            return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]

        result_payload = step_result.get("result")
        if isinstance(result_payload, dict):
            nested_trace = result_payload.get("execution_trace")
            if isinstance(nested_trace, list):
                return [copy.deepcopy(item) for item in nested_trace if isinstance(item, dict)]

        return []

    def _persist_step_result_to_runtime_state(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        current_tick: int,
    ) -> Dict[str, Any]:
        self._ensure_execution_trace_defaults(task, state)

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

        record = {
            "step_index": self._safe_int(
                step_result.get("step_index", state.get("current_step_index", 0)),
                self._safe_int(state.get("current_step_index", 0), 0),
            ),
            "step": copy.deepcopy(step) if isinstance(step, dict) else None,
            "result": copy.deepcopy(step_result),
            "tick": current_tick,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        results.append(copy.deepcopy(record))
        step_results.append(copy.deepcopy(record))
        execution_log.append(copy.deepcopy(record))

        incoming_trace = self._extract_trace_from_step_result(step_result)
        if incoming_trace:
            execution_trace.extend(copy.deepcopy(incoming_trace))

        state["last_step_result"] = copy.deepcopy(step_result)
        state["last_error"] = self._stringify_failure_message(step_result.get("error"))

        result_payload = step_result.get("result")
        if isinstance(result_payload, dict):
            for key in ("message", "content", "text", "final_answer", "stdout"):
                value = result_payload.get(key)
                if isinstance(value, str) and value.strip():
                    state["last_output"] = value.strip()
                    break

        if not state.get("last_output"):
            for key in ("message", "content", "text", "final_answer", "stdout"):
                value = step_result.get(key)
                if isinstance(value, str) and value.strip():
                    state["last_output"] = value.strip()
                    break

        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state = self.runtime.save_runtime_state(task, state)
        self._sync_runtime_state_back_to_task(task, state)
        return state

    def _sync_runtime_state_back_to_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if not isinstance(task, dict) or not isinstance(state, dict):
            return

        safe_state = self._compact_runtime_state_for_public_payload(state)

        # Do not embed the whole runtime_state into task.
        # It can recursively inflate task snapshots and returned scheduler payloads.
        task.pop("runtime_state", None)
        task["execution_trace"] = copy.deepcopy(safe_state.get("execution_trace", task.get("execution_trace", [])))
        task["execution_log"] = copy.deepcopy(safe_state.get("execution_log", task.get("execution_log", [])))
        task["results"] = copy.deepcopy(safe_state.get("results", task.get("results", [])))
        task["step_results"] = copy.deepcopy(safe_state.get("step_results", task.get("step_results", [])))
        task["last_step_result"] = copy.deepcopy(safe_state.get("last_step_result", task.get("last_step_result")))
        task["status"] = safe_state.get("status", task.get("status"))
        task["current_step_index"] = safe_state.get("current_step_index", task.get("current_step_index", 0))
        task["steps_total"] = safe_state.get("steps_total", task.get("steps_total", 0))
        task["last_error"] = safe_state.get("last_error", task.get("last_error"))
        task["final_answer"] = safe_state.get("final_answer", task.get("final_answer", ""))
        task["capability"] = safe_state.get("capability", task.get("capability", ""))
        task["operation"] = safe_state.get("operation", task.get("operation", ""))
        task["capability_hint"] = copy.deepcopy(safe_state.get("capability_hint", task.get("capability_hint", {})))
        task["capability_registry_hint"] = copy.deepcopy(
            safe_state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
        )
        task["capability_execution"] = copy.deepcopy(
            safe_state.get("capability_execution", task.get("capability_execution", {}))
        )

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _trace_tick_for_step(
        self,
        *,
        state: Optional[Dict[str, Any]],
        step_index: int,
        current_tick: int,
    ) -> int:
        """Return a stable task-local tick for trace.json events.

        Scheduler/current_tick can be reused or reset across queue runs, especially
        when `task run 2` advances multiple tasks.  For trace.json, the useful
        display value is the task-local step order, so each task shows a clean
        monotonic sequence: step 0 -> tick 1, step 1 -> tick 2, etc.
        The original scheduler tick is still stored separately as scheduler_tick
        on trace.json events that TaskRunner writes.
        """
        try:
            idx = int(step_index)
            if idx >= 0:
                return idx + 1
        except Exception:
            pass

        if isinstance(state, dict):
            try:
                idx = int(state.get("current_step_index", 0) or 0)
                if idx >= 0:
                    return idx + 1
            except Exception:
                pass

        try:
            tick = int(current_tick)
            return tick if tick > 0 else 1
        except Exception:
            return 1

    # ============================================================
    # helpers
    # ============================================================

    def _get_previous_result(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        last = state.get("last_step_result")
        if isinstance(last, dict):
            return copy.deepcopy(last)

        results = state.get("results")
        if isinstance(results, list) and results:
            last_item = results[-1]
            if isinstance(last_item, dict):
                result = last_item.get("result")
                if isinstance(result, dict):
                    return copy.deepcopy(result)

        return None

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

    def _should_convert_policy_block_to_review(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if bool(result.get("ok", False)):
            return False

        policy_action = str(result.get("policy_action") or "").strip().lower()
        guard_mode = str(result.get("guard_mode") or "").strip().lower()
        policy_reason = str(result.get("policy_reason") or "").strip().lower()
        error_text = self._stringify_failure_message(result.get("error")).strip().lower()

        if policy_action in {"ask", "review", "require_review"}:
            return True
        if policy_action == "deny":
            return True
        if guard_mode.startswith("policy_blocked"):
            return True
        if "policy blocked" in error_text or "policy_blocked" in error_text:
            return True
        if "blocked by guard" in error_text or "command execution blocked by guard" in error_text:
            return True
        if policy_reason and ("not allowed" in policy_reason or "blocked" in policy_reason):
            return True

        return False

    def _should_advance_failed_step_observation(
        self,
        *,
        step: Any,
        step_result: Any,
        step_index: int,
        step_count: int,
    ) -> bool:
        if not isinstance(step, dict) or not isinstance(step_result, dict):
            return False
        if bool(step_result.get("ok", False)):
            return False
        if not bool(step.get("continue_on_failure") or step.get("advance_on_failure")):
            return False
        step_type = str(step.get("type") or "").strip().lower()

        # continue_on_failure is an explicit task-level instruction.
        # It must work for diagnostic/observation steps, not only verify steps.
        # This is what allows:
        #   run_python fails -> record failure -> continue -> write failure report.
        allowed_continue_types = {
            "verify",
            "verify_file",
            "code_chain_verify",
            "run_python",
            "command",
            "shell",
            "tool",
            "read_file",
        }

        if step_type not in allowed_continue_types:
            return False

        return int(step_index) < max(0, int(step_count) - 1)

    def _maybe_inject_repair_steps_after_failure(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Optional[Dict[str, Any]]:
        """
        AER Repair Hook v1.

        Convert an observed runtime failure into injected repair steps.

        This is deliberately gated.  The runtime will only inject repair steps
        when the task or failed step explicitly opts in with auto_repair=True.

        Boundary:
        - The hook does not call an LLM.
        - The hook does not mutate target repo files directly.
        - The hook only writes generated repair candidates into the normal task
          sandbox flow via regular write_file/run_python/verify_file steps.
        """
        if not isinstance(task, dict) or not isinstance(state, dict):
            return None
        if not isinstance(step, dict) or not isinstance(step_result, dict):
            return None
        if bool(step_result.get("ok", False)):
            return None

        if bool(step.get("repair_injected")):
            return None

        if not bool(
            task.get("auto_repair")
            or task.get("enable_auto_repair")
            or step.get("auto_repair")
            or step.get("enable_auto_repair")
        ):
            return None

        repair_context = state.setdefault("repair_context", {})
        if not isinstance(repair_context, dict):
            repair_context = {}
            state["repair_context"] = repair_context

        source_path = self._infer_repair_source_path(step=step, step_result=step_result)

        repair_policy_decision = FailurePolicy.decide_repair(
            task=task,
            state=state,
            step=step,
            step_result=step_result,
            source_path=source_path,
        ).to_dict()
        repair_context["repair_policy_decision"] = copy.deepcopy(repair_policy_decision)
        state["repair_policy_decision"] = copy.deepcopy(repair_policy_decision)

        if not bool(repair_policy_decision.get("allow", False)):
            state["repair_policy_blocked"] = True
            state["repair_policy_reason"] = str(repair_policy_decision.get("reason") or "repair blocked")
            if bool(repair_policy_decision.get("quarantine", False)):
                state["repair_quarantine"] = True
            if str(repair_policy_decision.get("action") or "") == "review_required":
                state["status"] = "waiting_review"
                state["next_action"] = "wait_for_external_event"
                state["requires_review"] = True
                state["last_error"] = str(repair_policy_decision.get("reason") or "repair requires review")
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            self._trace(
                task,
                "repair_policy_blocked",
                {
                    "step_index": step_index,
                    "current_tick": current_tick,
                    "trace_tick": trace_tick,
                    "source_path": source_path,
                    "decision": copy.deepcopy(repair_policy_decision),
                },
            )
            self.audit.log_event(
                task,
                "repair_policy_blocked",
                {
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": step_index,
                    "source_path": source_path,
                    "decision": copy.deepcopy(repair_policy_decision),
                },
                source="repair_policy",
            )
            return None

        max_injections = self._safe_int(task.get("max_repair_injections") or state.get("max_repair_injections"), 1)
        if max_injections < 1:
            max_injections = 1
        prior_injections = repair_context.get("injections")
        prior_count = len(prior_injections) if isinstance(prior_injections, list) else 0
        if prior_count >= max_injections:
            return None

        source_text = self._read_repair_source_text(task=task, state=state, source_path=source_path)

        try:
            repair_plan = self.repair_planner.plan(
                step_result=copy.deepcopy(step_result),
                previous_result=copy.deepcopy(state.get("last_step_result")),
                source_path=source_path,
                source_text=source_text,
                target_path="",
            ).to_dict()
        except Exception as exc:
            repair_context["last_repair_plan_error"] = str(exc)
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            return None

        if not isinstance(repair_plan, dict) or not bool(repair_plan.get("ok", False)):
            repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            return None

        verify_command = ""
        action_path = self._first_repair_action_path(repair_plan)
        if action_path and action_path.lower().endswith(".py"):
            verify_command = "python -m py_compile " + action_path

        try:
            injection = self.repair_step_injector.build_injection(
                repair_plan=copy.deepcopy(repair_plan),
                task=task,
                failed_step=step,
                failed_result=step_result,
                verify_command=verify_command,
                report_path=str(task.get("auto_repair_report_path") or "AER_AUTO_REPAIR_REPORT.md"),
            ).to_dict()
        except Exception as exc:
            repair_context["last_repair_injection_error"] = str(exc)
            repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            return None

        if not isinstance(injection, dict) or not bool(injection.get("ok", False)):
            repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
            repair_context["last_repair_injection"] = copy.deepcopy(injection)
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            return None

        injected_steps = injection.get("steps")
        if not isinstance(injected_steps, list) or not injected_steps:
            return None

        try:
            injected_state = self.repair_step_injector.inject_steps_into_state(
                runtime_state=state,
                injected_steps=injected_steps,
                insert_after_index=step_index,
            )
        except Exception as exc:
            repair_context["last_repair_injection_error"] = str(exc)
            repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
            repair_context["last_repair_injection"] = copy.deepcopy(injection)
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
            return None

        injected_state["status"] = "running"
        injected_state["next_action"] = "run_next_tick"
        injected_state["last_repair_plan"] = copy.deepcopy(repair_plan)
        injected_state["last_repair_injection"] = copy.deepcopy(injection)
        injected_state["last_error"] = self._stringify_failure_message(step_result.get("error"))

        repair_context = injected_state.setdefault("repair_context", {})
        if isinstance(repair_context, dict):
            repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
            repair_context["last_repair_injection"] = copy.deepcopy(injection)
            repair_context["last_repair_source_path"] = source_path
            repair_context["last_repair_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        injected_state = self.runtime.save_runtime_state(task, injected_state)
        self._sync_runtime_state_back_to_task(task, injected_state)

        self._trace(
            task,
            "repair_steps_injected",
            {
                "step_index": step_index,
                "current_tick": current_tick,
                "trace_tick": trace_tick,
                "source_path": source_path,
                "repair_plan": copy.deepcopy(repair_plan),
                "repair_injection": copy.deepcopy(injection),
                "injected_step_count": len(injected_steps),
            },
        )
        self.audit.log_event(
            task,
            "repair_steps_injected",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": step_index,
                "source_path": source_path,
                "classification": repair_plan.get("classification"),
                "injected_step_count": len(injected_steps),
            },
            source="task_runner",
        )

        return {
            "ok": True,
            "runtime_state": injected_state,
            "repair_plan": repair_plan,
            "repair_injection": injection,
        }

    def _infer_repair_source_path(self, *, step: Any, step_result: Any) -> str:
        if isinstance(step, dict):
            for key in ("repair_source_path", "source_path", "path", "target_path", "file_path"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            command = str(step.get("command") or step.get("cmd") or "").strip()
            inferred = self._infer_python_compile_path_from_command(command)
            if inferred:
                return inferred

        if isinstance(step_result, dict):
            for key in ("path", "resolved_path"):
                value = step_result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            result = step_result.get("result")
            if isinstance(result, dict):
                for key in ("path", "resolved_path"):
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                nested = result.get("result")
                if isinstance(nested, dict):
                    for key in ("path", "resolved_path"):
                        value = nested.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()

        return ""

    def _infer_python_compile_path_from_command(self, command: str) -> str:
        text = str(command or "").strip()
        if not text:
            return ""
        try:
            parts = shlex.split(text, posix=False)
        except Exception:
            parts = text.split()
        if len(parts) >= 4:
            lowered = [str(part).strip().strip('"\'').lower() for part in parts]
            for index in range(0, len(lowered) - 2):
                if lowered[index] in {"python", "python3", "py"} or lowered[index].endswith("python.exe"):
                    if lowered[index + 1] == "-m" and lowered[index + 2] == "py_compile":
                        for candidate in parts[index + 3:]:
                            cleaned = str(candidate).strip().strip('"\'')
                            if cleaned.endswith(".py"):
                                return cleaned
        for token in parts:
            cleaned = str(token).strip().strip('"\'')
            if cleaned.endswith(".py"):
                return cleaned
        return ""

    def _read_repair_source_text(self, *, task: Dict[str, Any], state: Dict[str, Any], source_path: str) -> str:
        if not source_path:
            return ""

        candidates: List[str] = []

        def add_candidate(value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return
            try:
                normalized = os.path.abspath(text)
            except Exception:
                normalized = text
            if normalized not in candidates:
                candidates.append(normalized)

        if os.path.isabs(source_path):
            add_candidate(source_path)
        else:
            for base in (
                state.get("sandbox_dir"),
                state.get("task_dir"),
                task.get("sandbox_dir"),
                task.get("task_dir"),
                task.get("target_repo_root"),
                state.get("target_repo_root"),
            ):
                if isinstance(base, str) and base.strip():
                    add_candidate(os.path.join(base, source_path))

        try:
            resolved = self.step_executor.resolve_read_path(
                relative_path=source_path,
                task=task,
                prefer_scopes=("sandbox", "shared"),
                return_fallback_candidate_if_missing=True,
            )
            add_candidate(resolved)
        except Exception:
            pass

        for candidate in candidates:
            if os.path.exists(candidate) and os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    continue
        return ""

    def _first_repair_action_path(self, repair_plan: Any) -> str:
        if not isinstance(repair_plan, dict):
            return ""
        actions = repair_plan.get("actions")
        if not isinstance(actions, list):
            return ""
        for action in actions:
            if isinstance(action, dict):
                path = str(action.get("path") or "").strip()
                if path:
                    return path
        return ""

    def _should_rollback_after_failed_verify(self, *, step: Any, step_result: Any, state: Any) -> bool:
        if not isinstance(step, dict) or not isinstance(step_result, dict) or not isinstance(state, dict):
            return False
        if bool(step_result.get("ok", False)):
            return False
        step_type = str(step.get("type") or "").strip().lower()
        if step_type not in {"verify", "verify_file", "code_chain_verify"}:
            return False
        repair_context = state.get("repair_context")
        if not isinstance(repair_context, dict):
            return False
        rollback_result = repair_context.get("rollback_result")
        if isinstance(rollback_result, dict) and rollback_result.get("ok") is True:
            return False
        rollback = repair_context.get("rollback")
        return isinstance(rollback, dict) and bool(rollback.get("restore_available"))

    def _is_apply_step(self, step: Any) -> bool:
        if not isinstance(step, dict):
            return False
        return str(step.get("type") or "").strip().lower() in {"apply_patch", "apply_unified_diff"}

    def _run_regression_verify_phase(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        repair_context = state.get("repair_context") if isinstance(state, dict) else {}
        if not isinstance(repair_context, dict):
            return None
        repo_impact = repair_context.get("repo_impact")
        if not isinstance(repo_impact, dict):
            return None
        verify_plan = repo_impact.get("verify_plan")
        if not isinstance(verify_plan, dict):
            return None

        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commands = self._build_regression_verify_commands(verify_plan=verify_plan, repo_impact=repo_impact)
        results: List[Dict[str, Any]] = []
        blocked_commands: List[Dict[str, Any]] = []
        failed_commands: List[Dict[str, Any]] = []

        for command in commands:
            guard = self._validate_regression_command(command)
            if not guard.get("ok"):
                item = {"command": command, "reason": guard.get("error", "blocked regression command")}
                blocked_commands.append(item)
                failed_commands.append(item)
                continue
            completed = subprocess.run(
                guard["argv"],
                cwd=self._resolve_target_repo_root(task=task, state=state) or os.getcwd(),
                text=True,
                capture_output=True,
                timeout=30,
            )
            item = {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "ok": completed.returncode == 0,
            }
            results.append(item)
            if completed.returncode != 0:
                failed_commands.append(item)

        passed = not failed_commands and not blocked_commands
        error = ""
        if blocked_commands:
            error = "blocked regression command"
        elif failed_commands:
            error = "regression verification failed"

        return {
            "commands": commands,
            "results": results,
            "passed": passed,
            "failed_commands": failed_commands,
            "blocked_commands": blocked_commands,
            "started_at": started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": error,
            "current_tick": current_tick,
        }

    def _build_regression_verify_commands(self, *, verify_plan: Dict[str, Any], repo_impact: Dict[str, Any]) -> List[str]:
        commands: List[str] = []
        raw = verify_plan.get("commands")
        if isinstance(raw, list):
            commands.extend(str(item).strip() for item in raw if str(item).strip())

        for key in ("changed_files", "impacted_files"):
            value = repo_impact.get(key)
            if not isinstance(value, list):
                continue
            compile_files = list(dict.fromkeys(str(item).replace("\\", "/") for item in value if str(item).endswith(".py")))
            if compile_files:
                command = "python -m py_compile " + " ".join(compile_files)
                if command not in commands:
                    commands.append(command)

        return list(dict.fromkeys(commands))

    def _validate_regression_command(self, command: str) -> Dict[str, Any]:
        text = str(command or "").strip()
        try:
            parts = shlex.split(text, posix=False)
        except Exception as exc:
            return {"ok": False, "error": f"blocked regression command: parse failed: {exc}"}
        if len(parts) < 4:
            return {"ok": False, "error": "blocked regression command: too short"}

        exe = parts[0].lower()
        if exe not in {"python", "python3", "py"} and not exe.endswith("python.exe"):
            return {"ok": False, "error": "blocked regression command: only python is allowed"}
        if parts[1:3] == ["-m", "py_compile"]:
            paths = parts[3:]
            if not paths:
                return {"ok": False, "error": "blocked regression command: no py_compile paths"}
            for path in paths:
                normalized = path.replace("\\", "/").strip("'\"")
                if not normalized.endswith(".py"):
                    return {"ok": False, "error": "blocked regression command: py_compile only accepts .py files"}
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    return {"ok": False, "error": "blocked regression command: unsafe path"}
            return {"ok": True, "argv": [sys.executable] + parts[1:]}
        if parts[1:3] == ["-m", "pytest"]:
            paths = parts[3:]
            if not paths:
                return {"ok": False, "error": "blocked regression command: no pytest paths"}
            for path in paths:
                normalized = path.replace("\\", "/").strip("'\"")
                if not normalized.startswith("tests/"):
                    return {"ok": False, "error": "blocked regression command: pytest path must be under tests/"}
            return {"ok": True, "argv": parts}
        return {"ok": False, "error": "blocked regression command: not on whitelist"}

    def _build_policy_review_id(self, *, task: Dict[str, Any], step_index: int, current_tick: int) -> str:
        raw_task_id = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or "task"
        ).strip()
        safe_task_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw_task_id)
        if not safe_task_id:
            safe_task_id = "task"
        return f"review-policy-{safe_task_id}-{int(current_tick or 0)}-{int(step_index or 0)}"

    def _determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        error_payload = result.get("error")
        error_message = ""
        error_type = ""

        if isinstance(error_payload, dict):
            error_message = str(error_payload.get("message") or "").lower()
            error_type = str(error_payload.get("type") or "").lower()
        else:
            error_message = str(result.get("error") or "").lower()

        if (
            "repo source apply" in error_message
            or "requires confirmation" in error_message
            or error_type == "repo_scope_confirmation_required"
        ):
            return "unsafe_action"
        if "unsafe" in error_message or "blocked" in error_message:
            return "unsafe_action_blocked"
        if "timeout" in error_message or error_type in {"timeout", "command_timeout", "tool_timeout"}:
            return "timeout"
        if (
            "old_text/new_text" in error_message
            or "invalid_edit_payload" in error_message
            or error_type == "invalid_edit_payload_schema"
        ):
            return "validation_error"
        if "verify" in error_message or "validation" in error_message:
            return "validation_error"
        if (
            "not exist" in error_message
            or "not found" in error_message
            or error_type in {"tool_error", "command_failed", "step_handler_exception"}
        ):
            return "tool_error"

        return "internal_error"

    def _stringify_failure_message(self, error: Any) -> str:
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            return json.dumps(error, ensure_ascii=False)
        if isinstance(error, str):
            return error
        if error is None:
            return ""
        return str(error)

    def _compact_runtime_state_for_public_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {}
        safe = self._make_public_payload_safe(state)
        if not isinstance(safe, dict):
            return {}
        for key in ("results", "step_results", "execution_log"):
            value = safe.get(key)
            safe[key] = value[-MAX_PUBLIC_LIST_ITEMS:] if isinstance(value, list) else []
        trace = safe.get("execution_trace")
        safe["execution_trace"] = trace[-MAX_PUBLIC_TRACE_ITEMS:] if isinstance(trace, list) else []
        safe.pop("runtime_state", None)
        return safe

    def _make_public_payload_safe(self, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "<truncated: max depth reached>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if len(value) <= MAX_PUBLIC_TEXT_CHARS:
                return value
            return value[:MAX_PUBLIC_TEXT_CHARS] + f"\n<truncated: {len(value) - MAX_PUBLIC_TEXT_CHARS} characters omitted>"
        if isinstance(value, tuple):
            value = list(value)
        if isinstance(value, list):
            return [self._make_public_payload_safe(item, depth + 1) for item in value[-MAX_PUBLIC_LIST_ITEMS:]]
        if isinstance(value, dict):
            safe: Dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text in {"runtime_state", "task", "raw_task", "raw_result", "runner_result"}:
                    safe[key_text] = "<omitted: recursive/heavy payload>"
                    continue
                safe[key_text] = self._make_public_payload_safe(item, depth + 1)
            return safe
        return str(value)

    def _finalize_public_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "ok": False,
                "action": "invalid_result",
                "status": "failed",
                "error": "task_runner returned invalid result",
            }

        task = result.get("task")
        runtime_state = result.get("runtime_state")

        safe_runtime_state = None
        if isinstance(runtime_state, dict):
            safe_runtime_state = self._compact_runtime_state_for_public_payload(runtime_state)
            result["runtime_state"] = safe_runtime_state

        if isinstance(safe_runtime_state, dict) and isinstance(task, dict):
            task.pop("runtime_state", None)
            task["status"] = safe_runtime_state.get("status", task.get("status"))
            task["current_step_index"] = safe_runtime_state.get("current_step_index", task.get("current_step_index", 0))
            task["steps_total"] = safe_runtime_state.get("steps_total", task.get("steps_total", 0))
            task["results"] = copy.deepcopy(safe_runtime_state.get("results", task.get("results", [])))
            task["step_results"] = copy.deepcopy(safe_runtime_state.get("step_results", task.get("step_results", [])))
            task["execution_log"] = copy.deepcopy(safe_runtime_state.get("execution_log", task.get("execution_log", [])))
            task["execution_trace"] = copy.deepcopy(safe_runtime_state.get("execution_trace", task.get("execution_trace", [])))
            task["last_step_result"] = copy.deepcopy(safe_runtime_state.get("last_step_result"))
            task["last_error"] = safe_runtime_state.get("last_error")
            task["final_answer"] = safe_runtime_state.get("final_answer", task.get("final_answer", ""))
            task["capability"] = safe_runtime_state.get("capability", task.get("capability", ""))
            task["operation"] = safe_runtime_state.get("operation", task.get("operation", ""))
            task["capability_hint"] = copy.deepcopy(safe_runtime_state.get("capability_hint", task.get("capability_hint", {})))
            task["capability_registry_hint"] = copy.deepcopy(
                safe_runtime_state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
            )
            task["capability_execution"] = copy.deepcopy(
                safe_runtime_state.get("capability_execution", task.get("capability_execution", {}))
            )

        if isinstance(safe_runtime_state, dict):
            result["execution_trace"] = copy.deepcopy(safe_runtime_state.get("execution_trace", result.get("execution_trace", [])))
        elif isinstance(task, dict):
            result["execution_trace"] = copy.deepcopy(task.get("execution_trace", result.get("execution_trace", [])))
        else:
            result.setdefault("execution_trace", [])

        result.setdefault("final_answer", "")
        if isinstance(task, dict):
            candidate_final = str(task.get("final_answer") or "").strip()
            if candidate_final:
                result["final_answer"] = candidate_final

        if not result.get("final_answer"):
            last_result = result.get("last_result")
            result["final_answer"] = self._extract_final_answer_from_step_result(last_result)

        return result

    def _append_step_result_trace_json(
        self,
        *,
        task: Dict[str, Any],
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
    ) -> None:
        safe_step = copy.deepcopy(step) if isinstance(step, dict) else {}
        safe_result = copy.deepcopy(step_result) if isinstance(step_result, dict) else {}
        trace_items = self._extract_trace_from_step_result(safe_result)

        if not trace_items:
            trace_items = [
                {
                    "step_index": step_index,
                    "step_type": str(safe_step.get("type") or safe_result.get("step_type") or "").strip().lower(),
                    "ok": bool(safe_result.get("ok", False)),
                    "message": str(safe_result.get("message") or ""),
                    "final_answer": str(safe_result.get("final_answer") or ""),
                    "error_type": self._extract_error_type(safe_result),
                    "attempts": 1,
                    "max_attempts": 1,
                    "retry_used": False,
                }
            ]

        for item in trace_items:
            if not isinstance(item, dict):
                continue

            data = copy.deepcopy(item)
            data.setdefault("task_id", task.get("task_id") or task.get("id"))
            data.setdefault("tick", current_tick)
            data.setdefault("step_index", step_index)
            data.setdefault("step_type", str(safe_step.get("type") or "").strip().lower())
            data.setdefault("step_id", str(safe_step.get("id") or "").strip())

            if "ok" not in data:
                data["ok"] = bool(safe_result.get("ok", False))

            if "error" not in data and safe_result.get("error"):
                data["error"] = copy.deepcopy(safe_result.get("error"))

            self._append_trace_json_event(task, "step_result", data)

    def _append_trace_json_event(self, task: Dict[str, Any], event_type: str, data: Any) -> None:
        try:
            task_dir = self._resolve_task_dir_for_trace(task)
            if not task_dir:
                return

            os.makedirs(task_dir, exist_ok=True)
            trace_path = os.path.join(task_dir, "trace.json")

            trace_payload = self._read_trace_json(trace_path)
            events = trace_payload.setdefault("events", [])
            if not isinstance(events, list):
                events = []
                trace_payload["events"] = events

            events.append(
                {
                    "ts": datetime.now().timestamp(),
                    "event_type": str(event_type or "event"),
                    "data": self._make_json_safe(data),
                }
            )
            trace_payload["trace_version"] = int(trace_payload.get("trace_version") or 1)
            trace_payload["event_count"] = len(events)

            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _read_trace_json(self, trace_path: str) -> Dict[str, Any]:
        try:
            if os.path.exists(trace_path):
                with open(trace_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict):
                    if not isinstance(payload.get("events"), list):
                        payload["events"] = []
                    return payload
        except Exception:
            pass

        return {
            "trace_version": 1,
            "event_count": 0,
            "events": [],
        }

    def _resolve_task_dir_for_trace(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return ""

        value = task.get("task_dir")
        if isinstance(value, str) and value.strip():
            return os.path.abspath(value.strip())

        runtime_state = task.get("runtime_state")
        if isinstance(runtime_state, dict):
            value = runtime_state.get("task_dir")
            if isinstance(value, str) and value.strip():
                return os.path.abspath(value.strip())

        for key in ("trace_path", "runtime_state_path", "result_path", "plan_path"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return os.path.abspath(os.path.dirname(value.strip()))

        task_id = str(task.get("task_id") or task.get("id") or "").strip()
        if task_id:
            return os.path.abspath(os.path.join("workspace", "tasks", task_id))

        return ""

    def _extract_error_type(self, result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""

        error_payload = result.get("error")
        if isinstance(error_payload, dict):
            return str(error_payload.get("type") or "").strip()

        if error_payload:
            return "error"

        return ""

    def _trace(self, task: Dict[str, Any], label: str, payload: Any) -> None:
        try:
            task_dir = task.get("task_dir")
            if not task_dir:
                return

            os.makedirs(task_dir, exist_ok=True)
            trace_path = os.path.join(task_dir, "task_runner_trace.log")

            record = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "label": label,
                "payload": payload,
            }

            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

# ============================================================
# ZERO v7.0.2 - TaskRunner repair step preservation shim
# ============================================================
# Purpose:
# - If an older queued task accidentally preserved autonomous repair as a generic
#   command step, convert it back to code_chain_repair at execution time.
# - New tasks should already be fixed by Scheduler v7.0.2; this is a compatibility guard.

_ZERO_V702_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP = TaskRunner._run_one_step


def _zero_v702_runner_normalize_rel_path(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v702_runner_extract_workspace_py_path(text: str) -> str:
    match = re.search(r"(workspace[/\\][A-Za-z0-9_./\\ -]+?\.py)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return _zero_v702_runner_normalize_rel_path(match.group(1))


def _zero_v702_runner_looks_like_autonomous_repair(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    if "workspace/" not in lowered.replace("\\", "/") or ".py" not in lowered:
        return False
    has_analyze = any(token in lowered for token in ("analyze", "inspect", "check", "diagnose", "分析", "檢查"))
    has_repair = any(token in lowered for token in ("repair", "fix", "correct", "修復", "修正"))
    has_code_target = any(token in lowered for token in ("function", "functions", "math", "code", "函數", "函式"))
    return has_analyze and has_repair and has_code_target


def _zero_v702_runner_repair_task_steps_if_needed(self, task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return task
    goal = str(task.get("goal") or task.get("task") or task.get("name") or "").strip()
    if not _zero_v702_runner_looks_like_autonomous_repair(goal):
        return task
    target_path = _zero_v702_runner_extract_workspace_py_path(goal)
    if not target_path:
        return task

    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        task["steps"] = [
            {
                "type": "code_chain_repair",
                "task_text": goal,
                "target_path": target_path,
                "planner_autonomous_repair": True,
                "repair_scope": "single_file_math_functions_minimal",
                "preserve_step_type": True,
            }
        ]
        task["steps_total"] = 1
        task["step_count"] = 1
        task["current_step_index"] = 0
        return task

    current_index = 0
    try:
        current_index = int(task.get("current_step_index", 0) or 0)
    except Exception:
        current_index = 0
    if 0 <= current_index < len(steps) and isinstance(steps[current_index], dict):
        current = steps[current_index]
        current_type = str(current.get("type") or "").strip().lower()
        current_command = str(current.get("command") or "").strip().lower()
        if current_type == "command" or (current_type not in {"code_chain_repair", "autonomous_code_repair"} and current_command):
            steps[current_index] = {
                "type": "code_chain_repair",
                "task_text": goal,
                "target_path": target_path,
                "planner_autonomous_repair": True,
                "repair_scope": "single_file_math_functions_minimal",
                "preserve_step_type": True,
                "converted_from": copy.deepcopy(current),
            }
            task["steps"] = steps
    return task


def _zero_v702_task_runner_run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    task = _zero_v702_runner_repair_task_steps_if_needed(self, task)
    try:
        state = self.runtime.load_runtime_state(task)
        state = _zero_v702_runner_repair_task_steps_if_needed(self, state)
        if isinstance(state, dict) and isinstance(state.get("steps"), list):
            task["steps"] = copy.deepcopy(state.get("steps"))
            task["steps_total"] = len(task["steps"])
            task["step_count"] = len(task["steps"])
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
    except Exception:
        pass
    return _ZERO_V702_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP(self, task=task, current_tick=current_tick)


TaskRunner._run_one_step = _zero_v702_task_runner_run_one_step


# ============================================================
# ZERO v7.0.3 - TaskRunner Code Chain repair registration
# ============================================================
# Purpose:
# - Classify code_chain_repair failures as validation/tool failures rather than
#   opaque internal errors.
# - Mark code_chain_repair as a known side-effect step so runtime/replan layers
#   do not treat it as an unsupported generic step.

TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
    "code_chain_repair",
    "autonomous_code_repair",
}
TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair"}

_ZERO_V703_ORIGINAL_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v703_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES:
        error_text = str((result or {}).get("error") or (result or {}).get("message") or "").lower()
        if "unsafe" in error_text or "blocked" in error_text:
            return "unsafe_action_blocked"
        if "verification" in error_text or "verify" in error_text or "validation" in error_text:
            return "validation_error"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        return "validation_error"
    return _ZERO_V703_ORIGINAL_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v703_task_runner_determine_failure_type


# ============================================================
# ZERO v7.1.0 - Repair Scope Guard result classification
# ============================================================
# Keep preflight-blocked repair steps as failed/unsafe or validation failures;
# do not let them become finished simple tasks.

try:
    TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
    TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
except Exception:
    pass

_ZERO_V710_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v710_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set()):
        error_text = str(
            (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("final_answer")
            or ""
        ).lower()
        if "scope" in error_text or "blocked" in error_text or "unsafe" in error_text:
            return "unsafe_action_blocked"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        if "verification" in error_text or "validation" in error_text:
            return "validation_error"
        return "validation_error"
    return _ZERO_V710_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v710_task_runner_determine_failure_type


# ============================================================
# ZERO v7.3.1 - Multi-Step Code Chain TaskRunner registration
# ============================================================
# Register analyze / repair / verify phases as known Code Chain workflow steps.

_ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES = {
    "code_chain_analyze",
    "code_chain_repair",
    "autonomous_code_repair",
    "code_chain_verify",
    "code_chain_repair_preflight_failed",
}

try:
    TaskRunner.READ_ONLY_STEP_TYPES = set(getattr(TaskRunner, "READ_ONLY_STEP_TYPES", set())) | {
        "code_chain_analyze",
        "code_chain_verify",
    }
    TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
    TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
    TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
except Exception:
    pass

_ZERO_V731_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v731_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in getattr(TaskRunner, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set()):
        error_text = str(
            (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("final_answer")
            or ""
        ).lower()
        if "scope" in error_text or "blocked" in error_text or "unsafe" in error_text:
            return "unsafe_action_blocked"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        if "verification" in error_text or "validation" in error_text or "failed_functions" in error_text:
            return "validation_error"
        return "validation_error"
    return _ZERO_V731_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v731_task_runner_determine_failure_type


# ============================================================
# ZERO v8.0.0 - Autonomous Engineering Runtime wrapper
# ============================================================
# Adds durable Plan -> Execute -> Observe -> Decide -> Replan-candidate
# bookkeeping around the existing runtime step executor.  This wrapper does
# not bypass rollback, regression verification, scope gate, or strategy retry.

_ZERO_V800_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP = TaskRunner._run_one_step


def _zero_v800_extract_action(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("action") or "").strip()
    return ""


def _zero_v800_extract_status(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("status") or "").strip().lower()
    return ""


def _zero_v800_extract_error(result: Any) -> str:
    if not isinstance(result, dict):
        return "invalid runner result"
    for key in ("error", "last_error", "message", "final_answer"):
        value = result.get(key)
        if value:
            return str(value)
    runtime_state = result.get("runtime_state")
    if isinstance(runtime_state, dict):
        for key in ("last_error", "failure_message"):
            value = runtime_state.get(key)
            if value:
                return str(value)
    return ""


def _zero_v800_build_observation(self: TaskRunner, *, task: Dict[str, Any], result: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    runtime_state = result.get("runtime_state") if isinstance(result.get("runtime_state"), dict) else {}
    repair_context = runtime_state.get("repair_context") if isinstance(runtime_state, dict) else {}
    if not isinstance(repair_context, dict):
        repair_context = {}
    strategy = repair_context.get("strategy") if isinstance(repair_context.get("strategy"), dict) else {}
    regression_verify = repair_context.get("regression_verify") if isinstance(repair_context.get("regression_verify"), dict) else result.get("regression_verify")
    rollback_result = repair_context.get("rollback_result") if isinstance(repair_context.get("rollback_result"), dict) else result.get("rollback_result")
    repo_impact = repair_context.get("repo_impact") if isinstance(repair_context.get("repo_impact"), dict) else {}

    action = _zero_v800_extract_action(result)
    status = _zero_v800_extract_status(result)
    ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
    error = _zero_v800_extract_error(result)

    summary_parts = []
    if action:
        summary_parts.append(action)
    if status:
        summary_parts.append(status)
    if error:
        summary_parts.append(error[:240])

    return {
        "tick": current_tick,
        "action": action,
        "status": status,
        "ok": ok,
        "error": error,
        "summary": " | ".join(summary_parts),
        "current_step_index": runtime_state.get("current_step_index") if isinstance(runtime_state, dict) else None,
        "steps_total": runtime_state.get("steps_total") if isinstance(runtime_state, dict) else None,
        "last_step_type": self._zero_v800_last_step_type(runtime_state),
        "strategy": copy.deepcopy(strategy),
        "regression_verify": copy.deepcopy(regression_verify) if isinstance(regression_verify, dict) else {},
        "rollback_result": copy.deepcopy(rollback_result) if isinstance(rollback_result, dict) else {},
        "repo_impact": copy.deepcopy(repo_impact) if isinstance(repo_impact, dict) else {},
    }


def _zero_v800_decide_from_observation(self: TaskRunner, *, observation: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    action = str(observation.get("action") or "")
    status = str(observation.get("status") or "").lower()
    ok = bool(observation.get("ok", False))
    error = str(observation.get("error") or "")
    strategy = observation.get("strategy") if isinstance(observation.get("strategy"), dict) else {}
    exhausted = bool(strategy.get("exhausted", False))

    if action == "strategy_retry":
        return {
            "decision": "continue_strategy",
            "phase": "executing",
            "reason": f"strategy retry selected: {result.get('next_strategy', strategy.get('current_strategy', ''))}",
            "next_action": "run_next_tick",
            "next_strategy": result.get("next_strategy") or strategy.get("current_strategy", ""),
        }

    if action in {"blocked_for_review", "blocked_waiting"} or status in {"waiting", "waiting_review", "blocked", "paused"}:
        return {
            "decision": "wait_for_review",
            "phase": "waiting",
            "reason": error or "action blocked pending review",
            "next_action": "wait_for_external_event",
        }

    if status == "finished" or action in {"already_finished"}:
        return {
            "decision": "finish",
            "phase": "finished",
            "reason": "runtime reached terminal finished state",
            "next_action": "none",
        }

    if status in {"failed", "error", "cancelled", "canceled", "timeout"} or action in {"step_failed", "regression_verify_failed"}:
        if exhausted or action in {"step_failed", "regression_verify_failed"}:
            return {
                "decision": "replan_candidate",
                "phase": "replanning",
                "reason": error or "terminal failure observed by engineering runtime",
                "next_action": "manual_or_planner_replan",
                "strategy_exhausted": exhausted,
            }
        return {
            "decision": "terminal",
            "phase": "terminal",
            "reason": error or "terminal failure",
            "next_action": "none",
        }

    if action in {"step_failed_observed", "retry", "replan"}:
        return {
            "decision": "continue",
            "phase": "executing",
            "reason": action,
            "next_action": "run_next_tick",
        }

    if ok:
        return {
            "decision": "continue",
            "phase": "executing",
            "reason": action or "step completed",
            "next_action": "run_next_tick",
        }

    return {
        "decision": "replan_candidate",
        "phase": "replanning",
        "reason": error or "unclassified failure observed",
        "next_action": "manual_or_planner_replan",
        "strategy_exhausted": exhausted,
    }


def _zero_v800_last_step_type(self: TaskRunner, runtime_state: Any) -> str:
    if not isinstance(runtime_state, dict):
        return ""
    last = runtime_state.get("last_step_result")
    if not isinstance(last, dict):
        return ""
    step = last.get("step")
    if isinstance(step, dict):
        return str(step.get("type") or "")
    result = last.get("result")
    if isinstance(result, dict):
        return str(result.get("step_type") or "")
    return ""


def _zero_v800_task_runner_run_one_step(self: TaskRunner, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    result = _ZERO_V800_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP(self, task, current_tick)
    if not isinstance(result, dict):
        return result

    try:
        observation = self._zero_v800_build_observation(task=task, result=result, current_tick=current_tick)
        observed = self.runtime.record_engineering_observation(
            task=task,
            observation=observation,
            current_tick=current_tick,
        )
        if isinstance(observed, dict) and isinstance(observed.get("runtime_state"), dict):
            result["runtime_state"] = copy.deepcopy(observed["runtime_state"])

        decision = self._zero_v800_decide_from_observation(observation=observation, result=result)
        decided = self.runtime.record_engineering_decision(
            task=task,
            decision=decision,
            current_tick=current_tick,
        )
        if isinstance(decided, dict) and isinstance(decided.get("runtime_state"), dict):
            result["runtime_state"] = copy.deepcopy(decided["runtime_state"])

        if decision.get("decision") == "replan_candidate":
            runtime_state = result.get("runtime_state") if isinstance(result.get("runtime_state"), dict) else {}
            last_step = None
            last_result = None
            if isinstance(runtime_state, dict) and isinstance(runtime_state.get("last_step_result"), dict):
                last_record = runtime_state["last_step_result"]
                last_step = last_record.get("step") if isinstance(last_record.get("step"), dict) else None
                last_result = last_record.get("result") if isinstance(last_record.get("result"), dict) else None
            replan = self.runtime.create_engineering_replan_candidate(
                task=task,
                reason=decision.get("reason") or observation.get("error") or "engineering replan candidate",
                failed_step=last_step,
                failed_result=last_result,
                current_tick=current_tick,
            )
            if isinstance(replan, dict) and isinstance(replan.get("runtime_state"), dict):
                result["runtime_state"] = copy.deepcopy(replan["runtime_state"])
                result["engineering_replan_candidate"] = copy.deepcopy(replan.get("replan_candidate"))

        if isinstance(result.get("runtime_state"), dict):
            result["engineering_session"] = copy.deepcopy(result["runtime_state"].get("engineering_session", {}))
            result["execution_trace"] = copy.deepcopy(result["runtime_state"].get("execution_trace", result.get("execution_trace", [])))
    except Exception as exc:
        # Never let engineering-loop observability break the already-safe
        # transactional repair runtime.
        try:
            runtime_state = self.runtime.load_runtime_state(task)
            runtime_state["engineering_session_error"] = str(exc)
            runtime_state = self.runtime.save_runtime_state(task, runtime_state)
            result["runtime_state"] = runtime_state
        except Exception:
            result["engineering_session_error"] = str(exc)

    return result


TaskRunner._zero_v800_build_observation = _zero_v800_build_observation
TaskRunner._zero_v800_decide_from_observation = _zero_v800_decide_from_observation
TaskRunner._zero_v800_last_step_type = _zero_v800_last_step_type
TaskRunner._run_one_step = _zero_v800_task_runner_run_one_step
