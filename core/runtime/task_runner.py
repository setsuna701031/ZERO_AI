from __future__ import annotations

import copy
import hashlib
import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from core.memory.step_reflection_engine import StepReflectionEngine
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime


class TaskRunner:
    """
    ZERO Task Runner

    本版整合：
    1. RuntimeStateMachine 已透過 TaskRuntime 接入
    2. Retry / Replan / Wait / Fail policy
    3. Step metadata normalization
    4. 非 idempotent / 非 retry_safe / 非 replan_safe step 保護
    5. reflection -> failure_type -> policy -> runtime transition
    6. 修正最後一個 step 成功後沒進 finished 的 bug
    7. 修正 multi-step 任務只跑一步就停住的問題
       - step_completed 不再直接 break
       - 會在同一個 tick 內繼續跑下一步
    """

    DEFAULT_POLICY: Dict[str, Dict[str, Any]] = {
        "transient_error": {
            "retry": True,
            "replan": False,
            "wait": False,
            "fail": False,
        },
        "tool_error": {
            "retry": True,
            "replan": True,
            "wait": False,
            "fail": False,
        },
        "validation_error": {
            "retry": False,
            "replan": True,
            "wait": False,
            "fail": False,
        },
        "dependency_unmet": {
            "retry": False,
            "replan": False,
            "wait": True,
            "fail": False,
        },
        "timeout": {
            "retry": True,
            "replan": False,
            "wait": False,
            "fail": False,
        },
        "unsafe_action": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "unsafe_action_blocked": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "cancelled": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "internal_error": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "retry_exhausted": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "replan_exhausted": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "non_retryable_side_effect_step": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
        "non_replannable_side_effect_step": {
            "retry": False,
            "replan": False,
            "wait": False,
            "fail": True,
        },
    }

    READ_ONLY_STEP_TYPES = {
        "read_file",
        "list_files",
        "inspect",
        "analyze",
        "search",
        "web_search",
        "check",
        "verify",
        "noop",
    }

    SIDE_EFFECT_STEP_TYPES = {
        "command",
        "write_file",
        "delete_file",
        "call_api",
        "http_request",
        "shell",
        "execute",
    }

    def __init__(
        self,
        step_executor: Optional[StepExecutor] = None,
        replanner: Any = None,
        verifier: Any = None,
        debug: bool = False,
        task_runtime: Optional[TaskRuntime] = None,
        reflection_engine: Optional[StepReflectionEngine] = None,
    ) -> None:
        self.runtime = task_runtime if task_runtime is not None else TaskRuntime(debug=debug)
        self.step_executor = step_executor if step_executor is not None else StepExecutor()
        self.replanner = replanner
        self.verifier = verifier
        self.debug = debug
        self.reflection_engine = (
            reflection_engine if reflection_engine is not None else StepReflectionEngine()
        )

    # ============================================================
    # public
    # ============================================================

    def run_task_tick(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        self._trace(
            task,
            "run_task_tick_enter",
            {
                "current_tick": current_tick,
            },
        )

        try:
            self.runtime.ensure_runtime_state(task)

            cancel_result = self.runtime.check_cancel_before_run(
                task,
                current_tick=current_tick,
            )
            if cancel_result.get("cancel_applied"):
                return cancel_result

            timeout_result = self.runtime.check_timeout_before_run(
                task,
                current_tick=current_tick,
            )
            if timeout_result.get("timed_out"):
                return timeout_result

            blocked_result = self.runtime.check_blocked_by_dependencies(
                task,
                dependency_status_map={},
                current_tick=current_tick,
            )
            if blocked_result.get("blocked"):
                return blocked_result

            state = self.runtime.load_runtime_state(task)
            status = str(state.get("status", "") or "").strip().lower()

            if status == "retrying":
                next_retry_tick = int(state.get("next_retry_tick", 0) or 0)
                if current_tick < next_retry_tick:
                    return {
                        "ok": True,
                        "action": "waiting_retry",
                        "message": "waiting for next retry tick",
                        "task": copy.deepcopy(state),
                    }

                state = copy.deepcopy(state)
                state["status"] = "ready"
                self.runtime.save_runtime_state(task, state)
                state = self.runtime.load_runtime_state(task)
                status = str(state.get("status", "") or "").strip().lower()

            if status not in {"queued", "ready", "running", "retrying"}:
                return {
                    "ok": True,
                    "action": "skip",
                    "message": f"task status = {status}, skip",
                    "task": copy.deepcopy(state),
                }

            run_result = self.runtime.mark_running(task, current_tick=current_tick)
            state = copy.deepcopy(run_result.get("runtime_state", self.runtime.load_runtime_state(task)))

            max_steps_per_tick = self._get_max_steps_per_tick(state)
            loop_result: Optional[Dict[str, Any]] = None
            executed_steps = 0

            while executed_steps < max_steps_per_tick:
                loop_result = self._run_one_step(task, current_tick=current_tick)
                executed_steps += 1

                if not isinstance(loop_result, dict):
                    break

                action = str(loop_result.get("action", "") or "").strip().lower()

                if action in {
                    "task_finished",
                    "finished",
                    "step_failed",
                    "exception_failed",
                    "task_blocked",
                    "task_timeout",
                    "task_cancelled",
                    "replanned",
                    "retry_scheduled",
                    "waiting",
                }:
                    break

                # 關鍵修正：
                # step_completed 代表這一步成功，應該繼續跑下一步，
                # 而不是直接 break。
                if action == "step_completed":
                    latest_state = self.runtime.load_runtime_state(task)
                    current_index = int(latest_state.get("current_step_index", 0) or 0)
                    steps_total = int(
                        latest_state.get("steps_total", len(latest_state.get("steps", [])))
                        or len(latest_state.get("steps", []))
                    )

                    self._trace(
                        task,
                        "step_completed_continue",
                        {
                            "executed_steps": executed_steps,
                            "max_steps_per_tick": max_steps_per_tick,
                            "current_step_index": current_index,
                            "steps_total": steps_total,
                        },
                    )

                    if current_index >= steps_total:
                        loop_result = {
                            "ok": True,
                            "action": "task_finished",
                            "status": "finished",
                            "task": copy.deepcopy(latest_state),
                        }
                        break

                    continue

                if action in {"noop", ""}:
                    break

            if loop_result is None:
                loop_result = {
                    "ok": True,
                    "action": "noop",
                    "message": "no step executed",
                    "task": copy.deepcopy(state),
                }

            return loop_result

        except Exception as e:
            traceback.print_exc()
            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="internal_error",
                failure_message=str(e),
            )
            return {
                "ok": False,
                "action": "exception_failed",
                "error": str(e),
                "task": copy.deepcopy(fail_result.get("runtime_state", {})),
            }

    def run_one_tick(self, task: Dict[str, Any], current_tick: int = 0, **kwargs: Any) -> Dict[str, Any]:
        return self.run_task_tick(task, current_tick=current_tick)

    # ============================================================
    # step execution
    # ============================================================

    def _run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.runtime.load_runtime_state(task)
        steps = state.get("steps", [])
        current_index = int(state.get("current_step_index", 0) or 0)
        steps_total = int(state.get("steps_total", len(steps)) or len(steps))

        if not isinstance(steps, list):
            steps = []

        if not steps or current_index >= steps_total:
            finish_result = self.runtime.mark_finished(
                task,
                current_tick=current_tick,
                final_answer=state.get("final_answer", ""),
            )
            return {
                "ok": True,
                "action": "task_finished",
                "status": finish_result.get("status", "finished"),
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                "runtime_result": finish_result,
            }

        raw_step = steps[current_index]
        step = self._normalize_step_metadata(
            step=raw_step,
            step_index=current_index,
            steps_total=steps_total,
            task_state=state,
        )

        self._persist_normalized_step(
            task=task,
            step=step,
            step_index=current_index,
        )

        result = self.step_executor.execute_step(
            task=task,
            step=step,
            context={"cwd": state.get("task_dir")},
            step_index=current_index,
            step_count=steps_total,
        )

        if not isinstance(result, dict):
            result = {
                "ok": bool(result),
                "result": {},
            }

        result["step"] = copy.deepcopy(step)

        result = self._attach_step_metadata_to_result(
            step=step,
            result=result,
        )

        if hasattr(self.runtime, "append_step_result"):
            self.runtime.append_step_result(task, result)

        state = self.runtime.load_runtime_state(task)
        reflection = self.reflection_engine.reflect(
            goal=state.get("goal"),
            step=step,
            step_result=result,
            runtime_state_file=state.get("runtime_state_file"),
            plan_file=state.get("plan_file"),
            log_file=state.get("log_file"),
        )

        if not isinstance(reflection, dict):
            reflection = {
                "decision": "fail",
                "reason": "reflection returned non-dict result",
                "failure_type": "internal_error",
            }

        decision = str(reflection.get("decision", "fail") or "fail").strip().lower()
        reason = str(reflection.get("reason", "") or "")

        if decision == "continue":
            self.runtime.advance_step(task)
            after_advance = self.runtime.load_runtime_state(task)

            new_index = int(after_advance.get("current_step_index", 0) or 0)
            new_total = int(after_advance.get("steps_total", len(after_advance.get("steps", []))) or 0)

            if new_index >= new_total:
                finish_result = self.runtime.mark_finished(
                    task,
                    current_tick=current_tick,
                    final_answer=after_advance.get("final_answer", ""),
                )
                return {
                    "ok": True,
                    "action": "task_finished",
                    "status": finish_result.get("status", "finished"),
                    "reflection": reflection,
                    "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                    "runtime_result": finish_result,
                }

            return {
                "ok": True,
                "action": "step_completed",
                "status": after_advance.get("status", "running"),
                "reflection": reflection,
                "task": copy.deepcopy(after_advance),
            }

        if decision == "finish":
            finish_result = self.runtime.mark_finished(
                task,
                current_tick=current_tick,
                final_answer=reflection.get("final_answer", ""),
            )
            return {
                "ok": True,
                "action": "task_finished",
                "status": finish_result.get("status", "finished"),
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                "runtime_result": finish_result,
            }

        if decision == "wait":
            state = self.runtime.load_runtime_state(task)
            state, _ = self.runtime.state_machine.mark_waiting(
                state,
                reason="reflection_wait",
            )
            state = self.runtime.save_runtime_state(task, state)

            return {
                "ok": True,
                "action": "waiting",
                "status": state.get("status", "waiting"),
                "reflection": reflection,
                "task": copy.deepcopy(state),
            }

        failure_type = self._determine_failure_type(step=step, result=result, reflection=reflection)

        preferred_action = None
        if decision in {"retry", "replan"}:
            preferred_action = decision

        return self._apply_failure_policy(
            task=task,
            step=step,
            result=result,
            reflection=reflection,
            current_tick=current_tick,
            reason=reason,
            failure_type=failure_type,
            preferred_action=preferred_action,
        )

    # ============================================================
    # failure policy
    # ============================================================

    def _apply_failure_policy(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        result: Dict[str, Any],
        reflection: Dict[str, Any],
        current_tick: int,
        reason: str,
        failure_type: str,
        preferred_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self.runtime.load_runtime_state(task)
        policy = self.DEFAULT_POLICY.get(
            failure_type,
            self.DEFAULT_POLICY["internal_error"],
        )

        if policy.get("wait"):
            state, _ = self.runtime.state_machine.mark_waiting(
                state,
                reason="failure_policy_wait",
            )
            state["blocked_reason"] = reason or state.get("blocked_reason", "")
            state = self.runtime.save_runtime_state(task, state)

            return {
                "ok": True,
                "action": "waiting",
                "status": state.get("status", "waiting"),
                "reflection": reflection,
                "failure_type": failure_type,
                "task": copy.deepcopy(state),
            }

        action_order = self._build_action_order(policy, preferred_action=preferred_action)

        self._trace(
            task,
            "apply_failure_policy",
            {
                "failure_type": failure_type,
                "preferred_action": preferred_action,
                "action_order": action_order,
                "reason": reason,
                "step_type": step.get("type"),
                "step_key": step.get("step_key"),
                "idempotent": step.get("idempotent"),
                "retry_safe": step.get("retry_safe"),
                "replan_safe": step.get("replan_safe"),
                "side_effects": step.get("side_effects"),
            },
        )

        for action_name in action_order:
            if action_name == "retry":
                retry_result = self._attempt_retry(
                    task=task,
                    step=step,
                    current_tick=current_tick,
                    reason=reason,
                    reflection=reflection,
                    failure_type=failure_type,
                )
                if retry_result is not None:
                    return retry_result

            elif action_name == "replan":
                replan_result = self._attempt_replan(
                    task=task,
                    step=step,
                    current_tick=current_tick,
                    reason=reason,
                    reflection=reflection,
                    failure_type=failure_type,
                )
                if replan_result is not None:
                    return replan_result

            elif action_name == "fail":
                return self._fail_step(
                    task=task,
                    current_tick=current_tick,
                    reason=reason,
                    reflection=reflection,
                    failure_type=failure_type,
                )

        return self._fail_step(
            task=task,
            current_tick=current_tick,
            reason=reason or "no valid policy action available",
            reflection=reflection,
            failure_type=failure_type,
        )

    def _build_action_order(
        self,
        policy: Dict[str, Any],
        preferred_action: Optional[str] = None,
    ) -> list[str]:
        actions = []

        if preferred_action == "replan":
            if policy.get("replan"):
                actions.append("replan")
            if policy.get("retry"):
                actions.append("retry")
        else:
            if policy.get("retry"):
                actions.append("retry")
            if policy.get("replan"):
                actions.append("replan")

        if policy.get("fail") or not actions:
            actions.append("fail")

        deduped: list[str] = []
        seen = set()
        for item in actions:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped

    # ============================================================
    # retry / replan helpers
    # ============================================================

    def _attempt_retry(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        current_tick: int,
        reason: str,
        reflection: Dict[str, Any],
        failure_type: str,
    ) -> Optional[Dict[str, Any]]:
        state = self.runtime.load_runtime_state(task)

        if not self.runtime.should_retry(task=state, failure_type=failure_type):
            return None

        retry_safe = self._is_retry_safe(step=step, result=None, reflection=reflection)
        if not retry_safe:
            self._trace(
                task,
                "retry_blocked_non_idempotent",
                {
                    "failure_type": failure_type,
                    "reason": reason,
                    "step_type": step.get("type"),
                    "step_key": step.get("step_key"),
                },
            )
            return None

        retry_delay = int(state.get("retry_delay", 0) or 0)
        next_retry_tick = current_tick + max(1, retry_delay if retry_delay > 0 else 1)

        retry_result = self.runtime.mark_retrying(
            task=task,
            current_tick=current_tick,
            failure_type=failure_type,
            failure_message=reason,
            next_retry_tick=next_retry_tick,
        )

        return {
            "ok": True,
            "action": "retry_scheduled",
            "status": retry_result.get("status", "retrying"),
            "reflection": reflection,
            "failure_type": failure_type,
            "task": copy.deepcopy(retry_result.get("runtime_state", {})),
            "runtime_result": retry_result,
        }

    def _attempt_replan(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        current_tick: int,
        reason: str,
        reflection: Dict[str, Any],
        failure_type: str,
    ) -> Optional[Dict[str, Any]]:
        state = self.runtime.load_runtime_state(task)

        replan_safe = self._is_replan_safe(step=step, result=None, reflection=reflection)
        if not replan_safe:
            self._trace(
                task,
                "replan_blocked_non_idempotent",
                {
                    "failure_type": failure_type,
                    "reason": reason,
                    "step_type": step.get("type"),
                    "step_key": step.get("step_key"),
                },
            )
            return None

        replan_count = int(state.get("replan_count", 0) or 0)
        max_replans = int(state.get("max_replans", 1) or 1)

        if replan_count >= max_replans:
            self._trace(
                task,
                "replan_exhausted_before_call",
                {
                    "replan_count": replan_count,
                    "max_replans": max_replans,
                    "reason": reason,
                    "step_key": step.get("step_key"),
                },
            )
            return None

        if not self.replanner:
            self._trace(
                task,
                "replan_missing_replanner",
                {
                    "reason": reason,
                    "step_key": step.get("step_key"),
                },
            )
            return None

        state, _ = self.runtime.state_machine.mark_replanning(
            state,
            reason="task_runner_attempt_replan",
        )
        self.runtime.save_runtime_state(task, state)

        replan_result = self.replanner.replan(
            goal=state.get("goal"),
            task_dir=state.get("task_dir"),
            plan_file=state.get("plan_file"),
            runtime_file=state.get("runtime_state_file"),
            reason=reason,
            failed_step=copy.deepcopy(step),
        )

        if not isinstance(replan_result, dict) or not replan_result.get("ok"):
            self._trace(
                task,
                "replan_failed",
                {
                    "reason": reason,
                    "replan_result": replan_result,
                    "step_key": step.get("step_key"),
                },
            )
            return None

        latest_state = self.runtime.load_runtime_state(task)

        return {
            "ok": True,
            "action": "replanned",
            "status": latest_state.get("status", "ready"),
            "reflection": reflection,
            "failure_type": failure_type,
            "task": copy.deepcopy(latest_state),
            "replan_result": replan_result,
        }

    def _fail_step(
        self,
        task: Dict[str, Any],
        current_tick: int,
        reason: str,
        reflection: Dict[str, Any],
        failure_type: str,
    ) -> Dict[str, Any]:
        fail_result = self.runtime.mark_failed(
            task=task,
            current_tick=current_tick,
            failure_type=failure_type,
            failure_message=reason,
        )

        return {
            "ok": False,
            "action": "step_failed",
            "status": fail_result.get("status", "failed"),
            "reflection": reflection,
            "failure_type": failure_type,
            "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
            "runtime_result": fail_result,
        }

    # ============================================================
    # failure type / side effect helpers
    # ============================================================

    def _determine_failure_type(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        reflection: Dict[str, Any],
    ) -> str:
        for source in (reflection, result):
            if isinstance(source, dict):
                value = str(source.get("failure_type", "") or "").strip().lower()
                if value:
                    return self._normalize_failure_type(value)

        if isinstance(result, dict):
            error_text = str(result.get("error", "") or "").lower()
            if "timeout" in error_text:
                return "timeout"
            if "unsafe" in error_text:
                return "unsafe_action_blocked"
            if "validation" in error_text:
                return "validation_error"
            if "dependency" in error_text or "blocked" in error_text:
                return "dependency_unmet"

        if isinstance(reflection, dict):
            decision = str(reflection.get("decision", "") or "").strip().lower()
            if decision == "retry":
                return "tool_error"
            if decision == "replan":
                return "validation_error"
            if decision == "wait":
                return "dependency_unmet"

        step_type = str(step.get("type", "") or "").strip().lower()
        if step_type in {"command", "call_api", "write_file", "delete_file"}:
            return "tool_error"

        return "internal_error"

    def _normalize_failure_type(self, value: str) -> str:
        value = str(value or "").strip().lower()
        if value in self.DEFAULT_POLICY:
            return value
        if value == "unsafe_action":
            return "unsafe_action"
        return "internal_error"

    def _is_retry_safe(
        self,
        step: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        reflection: Optional[Dict[str, Any]] = None,
    ) -> bool:
        explicit = self._get_explicit_safety_flag(
            step=step,
            result=result,
            reflection=reflection,
            keys=["retry_safe", "idempotent"],
        )
        if explicit is not None:
            return explicit

        return self._default_idempotent_by_step_type(step)

    def _is_replan_safe(
        self,
        step: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        reflection: Optional[Dict[str, Any]] = None,
    ) -> bool:
        explicit = self._get_explicit_safety_flag(
            step=step,
            result=result,
            reflection=reflection,
            keys=["replan_safe", "idempotent"],
        )
        if explicit is not None:
            return explicit

        return self._default_idempotent_by_step_type(step)

    def _get_explicit_safety_flag(
        self,
        step: Optional[Dict[str, Any]],
        result: Optional[Dict[str, Any]],
        reflection: Optional[Dict[str, Any]],
        keys: list[str],
    ) -> Optional[bool]:
        sources = [step, result, reflection]
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                if key in source:
                    return bool(source.get(key))
        return None

    def _default_idempotent_by_step_type(self, step: Dict[str, Any]) -> bool:
        step_type = str(step.get("type", "") or "").strip().lower()

        if step_type in self.READ_ONLY_STEP_TYPES:
            return True

        if step_type in self.SIDE_EFFECT_STEP_TYPES:
            return False

        if bool(step.get("side_effects", False)):
            return False

        return False

    # ============================================================
    # step metadata / idempotency system
    # ============================================================

    def _normalize_step_metadata(
        self,
        step: Dict[str, Any],
        step_index: int,
        steps_total: int,
        task_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = copy.deepcopy(step or {})
        step_type = str(normalized.get("type", "") or "").strip().lower()

        if not step_type:
            step_type = "unknown"
            normalized["type"] = step_type

        step_key = normalized.get("step_key")
        if not isinstance(step_key, str) or not step_key.strip():
            step_key = self._build_step_key(
                step=normalized,
                step_index=step_index,
                task_name=str(task_state.get("task_name", "") or ""),
            )
        normalized["step_key"] = step_key

        if "step_index" not in normalized:
            normalized["step_index"] = step_index
        if "step_count" not in normalized:
            normalized["step_count"] = steps_total

        defaults = self._infer_step_metadata_defaults(normalized)

        for key, value in defaults.items():
            if key not in normalized:
                normalized[key] = value

        normalized.setdefault("produces_files", [])
        normalized.setdefault("consumes_files", [])
        normalized.setdefault("external_effects", [])

        normalized["produces_files"] = self._normalize_string_list(normalized.get("produces_files"))
        normalized["consumes_files"] = self._normalize_string_list(normalized.get("consumes_files"))
        normalized["external_effects"] = self._normalize_string_list(normalized.get("external_effects"))

        return normalized

    def _infer_step_metadata_defaults(self, step: Dict[str, Any]) -> Dict[str, Any]:
        step_type = str(step.get("type", "") or "").strip().lower()
        metadata: Dict[str, Any] = {}

        if step_type in self.READ_ONLY_STEP_TYPES:
            metadata["idempotent"] = True
            metadata["side_effects"] = False
            metadata["retry_safe"] = True
            metadata["replan_safe"] = True
            metadata["safety_class"] = "read_only"
            return metadata

        if step_type == "write_file":
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "file_write"

            path = str(step.get("path", "") or "").strip()
            if path:
                metadata["produces_files"] = [path]
            return metadata

        if step_type == "delete_file":
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "file_delete"

            path = str(step.get("path", "") or "").strip()
            if path:
                metadata["external_effects"] = [f"delete:{path}"]
            return metadata

        if step_type in {"command", "shell", "execute"}:
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "command"

            command = str(step.get("command", "") or "").strip()
            if command:
                metadata["external_effects"] = [f"command:{command}"]
            return metadata

        if step_type in {"call_api", "http_request"}:
            method = str(step.get("method", "") or "POST").strip().upper()

            if method == "GET":
                metadata["idempotent"] = True
                metadata["side_effects"] = False
                metadata["retry_safe"] = True
                metadata["replan_safe"] = True
                metadata["safety_class"] = "http_read"
            else:
                metadata["idempotent"] = False
                metadata["side_effects"] = True
                metadata["retry_safe"] = False
                metadata["replan_safe"] = False
                metadata["safety_class"] = "http_write"

            url = str(step.get("url", "") or "").strip()
            if url:
                metadata["external_effects"] = [f"http:{method}:{url}"]
            return metadata

        metadata["idempotent"] = False
        metadata["side_effects"] = False
        metadata["retry_safe"] = False
        metadata["replan_safe"] = False
        metadata["safety_class"] = "unknown"
        return metadata

    def _build_step_key(
        self,
        step: Dict[str, Any],
        step_index: int,
        task_name: str,
    ) -> str:
        safe_step = copy.deepcopy(step or {})
        safe_step.pop("step_key", None)
        raw = {
            "task_name": task_name,
            "step_index": step_index,
            "type": safe_step.get("type"),
            "command": safe_step.get("command"),
            "path": safe_step.get("path"),
            "url": safe_step.get("url"),
            "method": safe_step.get("method"),
            "content": safe_step.get("content"),
        }
        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
        return f"step_{step_index}_{digest}"

    def _persist_normalized_step(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        step_index: int,
    ) -> None:
        try:
            state = self.runtime.load_runtime_state(task)
            steps = copy.deepcopy(state.get("steps", []))
            if not isinstance(steps, list):
                return
            if step_index < 0 or step_index >= len(steps):
                return

            steps[step_index] = copy.deepcopy(step)
            state["steps"] = steps
            state["steps_total"] = len(steps)
            self.runtime.save_runtime_state(task, state)

            self._trace(
                task,
                "step_metadata_normalized",
                {
                    "step_index": step_index,
                    "step_key": step.get("step_key"),
                    "step_type": step.get("type"),
                    "idempotent": step.get("idempotent"),
                    "side_effects": step.get("side_effects"),
                    "retry_safe": step.get("retry_safe"),
                    "replan_safe": step.get("replan_safe"),
                    "safety_class": step.get("safety_class"),
                },
            )
        except Exception:
            pass

    def _attach_step_metadata_to_result(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = copy.deepcopy(result or {})
        merged["step_key"] = step.get("step_key")
        merged["idempotent"] = step.get("idempotent")
        merged["side_effects"] = step.get("side_effects")
        merged["retry_safe"] = step.get("retry_safe")
        merged["replan_safe"] = step.get("replan_safe")
        merged["safety_class"] = step.get("safety_class")
        return merged

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []

        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result

        text = str(value).strip()
        return [text] if text else []

    # ============================================================
    # helpers
    # ============================================================

    def _get_max_steps_per_tick(self, state: Dict[str, Any]) -> int:
        try:
            v = int(state.get("max_steps_per_tick", 20))
            return max(1, v)
        except Exception:
            return 20

    def _trace(self, task: Dict[str, Any], label: str, payload: Any) -> None:
        try:
            task_dir = task.get("task_dir")
            if not task_dir:
                return

            os.makedirs(task_dir, exist_ok=True)
            trace_path = os.path.join(task_dir, "task_runner_trace.log")

            record = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                "label": label,
                "payload": payload,
            }

            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass