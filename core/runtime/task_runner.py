from __future__ import annotations

import copy
import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.memory.step_reflection_engine import StepReflectionEngine
from core.runtime.failure_policy import FailurePolicy
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime


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
    SIDE_EFFECT_STEP_TYPES = {"command", "write_file", "delete_file", "call_api", "shell", "run_python"}

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

    # ============================================================
    # main loop
    # ============================================================

    def run_task_tick(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        try:
            self.runtime.ensure_runtime_state(task)
            run_result = self.runtime.mark_running(task, current_tick=current_tick)
            state = copy.deepcopy(run_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, state)

            result = self._run_one_step(task, current_tick=current_tick)
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

        step = steps[idx]

        result = self.step_executor.execute_step(
            task=task,
            step=step,
            context={"cwd": state.get("task_dir")},
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

        if not result.get("ok"):
            state = self._persist_step_result_to_runtime_state(
                task=task,
                state=state,
                step=step,
                step_result=result,
                current_tick=current_tick,
            )

            failure_type = self._determine_failure_type(step, result)
            decision = FailurePolicy.decide(failure_type)

            failure_decision = {
                "retry": decision.retry,
                "replan": decision.replan,
                "fail": decision.fail,
                "wait": decision.wait,
            }

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
                failure_message=self._stringify_failure_message(result.get("error")),
            )

            fail_result["failure_decision"] = failure_decision
            runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)

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
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        advance_result = self.runtime.advance_step(
            task=task,
            step_result=result,
            current_tick=current_tick,
        )
        new_state = copy.deepcopy(advance_result.get("runtime_state", {}))
        self._ensure_execution_trace_defaults(task, new_state)
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

        task["runtime_state"] = copy.deepcopy(state)
        task["execution_trace"] = copy.deepcopy(state.get("execution_trace", task.get("execution_trace", [])))
        task["execution_log"] = copy.deepcopy(state.get("execution_log", task.get("execution_log", [])))
        task["results"] = copy.deepcopy(state.get("results", task.get("results", [])))
        task["step_results"] = copy.deepcopy(state.get("step_results", task.get("step_results", [])))
        task["last_step_result"] = copy.deepcopy(state.get("last_step_result", task.get("last_step_result")))
        task["status"] = state.get("status", task.get("status"))
        task["current_step_index"] = state.get("current_step_index", task.get("current_step_index", 0))
        task["steps_total"] = state.get("steps_total", task.get("steps_total", 0))
        task["last_error"] = state.get("last_error", task.get("last_error"))
        task["final_answer"] = state.get("final_answer", task.get("final_answer", ""))

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

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

    def _determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        error_payload = result.get("error")
        error_message = ""
        error_type = ""

        if isinstance(error_payload, dict):
            error_message = str(error_payload.get("message") or "").lower()
            error_type = str(error_payload.get("type") or "").lower()
        else:
            error_message = str(result.get("error") or "").lower()

        if "unsafe" in error_message or "blocked" in error_message:
            return "unsafe_action_blocked"
        if "timeout" in error_message or error_type in {"timeout", "command_timeout", "tool_timeout"}:
            return "timeout"
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

        if isinstance(runtime_state, dict) and isinstance(task, dict):
            task["runtime_state"] = copy.deepcopy(runtime_state)
            task["status"] = runtime_state.get("status", task.get("status"))
            task["current_step_index"] = runtime_state.get("current_step_index", task.get("current_step_index", 0))
            task["steps_total"] = runtime_state.get("steps_total", task.get("steps_total", 0))
            task["results"] = copy.deepcopy(runtime_state.get("results", task.get("results", [])))
            task["step_results"] = copy.deepcopy(runtime_state.get("step_results", task.get("step_results", [])))
            task["execution_log"] = copy.deepcopy(runtime_state.get("execution_log", task.get("execution_log", [])))
            task["execution_trace"] = copy.deepcopy(runtime_state.get("execution_trace", task.get("execution_trace", [])))
            task["last_step_result"] = copy.deepcopy(runtime_state.get("last_step_result"))
            task["last_error"] = runtime_state.get("last_error")
            task["final_answer"] = runtime_state.get("final_answer", task.get("final_answer", ""))

        if isinstance(runtime_state, dict):
            result["execution_trace"] = copy.deepcopy(runtime_state.get("execution_trace", result.get("execution_trace", [])))
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