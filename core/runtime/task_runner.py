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
from core.runtime.failure_policy import FailurePolicy  # ✅ NEW


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
    SIDE_EFFECT_STEP_TYPES = {"command", "write_file", "delete_file", "call_api", "shell"}

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

            return {
                "ok": False,
                "action": "exception_failed",
                "error": str(e),
                "task": fail_result,
                "status": "failed",
            }

    # ============================================================
    # step execution
    # ============================================================

    def _run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.runtime.load_runtime_state(task)
        steps = state.get("steps", [])
        idx = state.get("current_step_index", 0)

        if idx >= len(steps):
            return self.runtime.mark_finished(task, current_tick)

        step = steps[idx]

        result = self.step_executor.execute_step(
            task=task,
            step=step,
            context={"cwd": state.get("task_dir")},
        )

        if not result.get("ok"):
            # ============================================================
            # 🔥 核心：failure decision 注入
            # ============================================================

            failure_type = self._determine_failure_type(step, result)
            decision = FailurePolicy.decide(failure_type)

            failure_decision = {
                "retry": decision.retry,
                "replan": decision.replan,
                "fail": decision.fail,
                "wait": decision.wait,
            }

            # trace
            self._trace(
                task,
                "failure_decision",
                {
                    "failure_type": failure_type,
                    "decision": failure_decision,
                    "error": result.get("error"),
                },
            )

            # ============================================================
            # policy 分支
            # ============================================================

            if decision.retry:
                return {
                    "ok": False,
                    "action": "retry",
                    "failure_type": failure_type,
                    "failure_decision": failure_decision,
                    "error": result.get("error"),
                }

            if decision.replan and self.replanner:
                self.replanner.replan(
                    goal=state.get("goal"),
                    failed_step=step,
                    reason=result.get("error"),
                )
                return {
                    "ok": False,
                    "action": "replan",
                    "failure_type": failure_type,
                    "failure_decision": failure_decision,
                }

            # 最終 fail（這裡會寫入 runtime）
            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type=failure_type,
                failure_message=result.get("error"),
            )

            # 👉 把 decision 帶出去
            fail_result["failure_decision"] = failure_decision

            return {
                "ok": False,
                "action": "step_failed",
                "failure_type": failure_type,
                "failure_decision": failure_decision,
                "task": fail_result,
            }

        # success
        self.runtime.advance_step(task)

        return {
            "ok": True,
            "action": "step_completed",
        }

    # ============================================================
    # helpers
    # ============================================================

    def _determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        err = str(result.get("error", "")).lower()

        if "unsafe" in err or "blocked" in err:
            return "unsafe_action_blocked"
        if "not exist" in err:
            return "tool_error"
        if "timeout" in err:
            return "timeout"

        return "internal_error"

    def _finalize_public_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
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