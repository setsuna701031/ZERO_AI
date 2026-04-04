from __future__ import annotations

import copy
import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from core.runtime.task_runtime import TaskRuntime
from core.runtime.step_executor import StepExecutor
from core.memory.step_reflection_engine import StepReflectionEngine


class TaskRunner:
    def __init__(
        self,
        step_executor=None,
        replanner=None,
        verifier=None,
        debug: bool = False,
        task_runtime=None,
        reflection_engine=None,
    ):
        self.runtime = task_runtime if task_runtime is not None else TaskRuntime()
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
        self._trace(task, "run_task_tick_enter", {
            "current_tick": current_tick,
        })

        try:
            state = self.runtime.ensure_runtime_state(task)

            # cancel
            cancel_result = self.runtime.check_cancel_before_run(task, current_tick=current_tick)
            if cancel_result.get("cancel_applied"):
                return cancel_result

            # timeout
            timeout_result = self.runtime.check_timeout_before_run(task, current_tick=current_tick)
            if timeout_result.get("timed_out"):
                return timeout_result

            # dependency
            blocked_result = self.runtime.check_blocked_by_dependencies(
                task,
                dependency_status_map={},
                current_tick=current_tick,
            )
            if blocked_result.get("blocked"):
                return blocked_result

            state = self.runtime.load_runtime_state(task)
            status = str(state.get("status", "")).lower()

            # ----------------------------------------------------
            # retrying → 等 next_retry_tick
            # ----------------------------------------------------
            if status == "retrying":
                next_retry_tick = int(state.get("next_retry_tick", 0) or 0)
                if current_tick < next_retry_tick:
                    return {
                        "ok": True,
                        "action": "waiting_retry",
                        "message": "waiting for next retry tick",
                        "task": copy.deepcopy(state),
                    }

                # 到時間 → 變回 running
                state["status"] = "running"
                self.runtime.save_runtime_state(task, state)

            if status not in ["queued", "ready", "running", "retrying"]:
                return {
                    "ok": True,
                    "action": "skip",
                    "message": f"task status = {status}, skip",
                    "task": copy.deepcopy(state),
                }

            self.runtime.mark_running(task, current_tick)

            max_steps_per_tick = self._get_max_steps_per_tick(state)

            loop_result = None
            executed_steps = 0

            while executed_steps < max_steps_per_tick:
                loop_result = self._run_one_step(task, current_tick=current_tick)
                executed_steps += 1

                if not isinstance(loop_result, dict):
                    break

                action = str(loop_result.get("action", "")).lower()

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

                if action == "step_completed":
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

    def run_one_tick(self, task: Dict[str, Any], current_tick: int = 0, **kwargs) -> Dict[str, Any]:
        return self.run_task_tick(task, current_tick=current_tick)

    # ============================================================
    # step execution
    # ============================================================

    def _run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.runtime.load_runtime_state(task)

        steps = state.get("steps", [])
        current_index = int(state.get("current_step_index", 0) or 0)
        steps_total = int(state.get("steps_total", len(steps)) or len(steps))

        # no steps → finished
        if not steps or current_index >= steps_total:
            finish_result = self.runtime.mark_finished(
                task,
                current_tick=current_tick,
                final_answer=state.get("final_answer", ""),
            )

            return {
                "ok": True,
                "action": "task_finished",
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                "runtime_result": finish_result,
            }

        step = steps[current_index]

        # --------------------------------------------------------
        # execute step
        # --------------------------------------------------------
        result = self.step_executor.execute_step(
            task=task,
            step=step,
            context={"cwd": state.get("task_dir")},
            step_index=current_index,
            step_count=steps_total,
        )

        if not isinstance(result, dict):
            result = {"ok": bool(result), "result": {}}

        # save result
        if hasattr(self.runtime, "append_step_result"):
            self.runtime.append_step_result(task, result)

        # --------------------------------------------------------
        # reflection
        # --------------------------------------------------------
        state = self.runtime.load_runtime_state(task)
        reflection = self.reflection_engine.reflect(
            goal=state.get("goal"),
            step=step,
            step_result=result,
            runtime_state_file=state.get("runtime_state_file"),
            plan_file=state.get("plan_file"),
            log_file=state.get("log_file"),
        )

        decision = reflection.get("decision", "fail")
        reason = reflection.get("reason", "")

        # ========================================================
        # decision handling
        # ========================================================

        if decision == "continue":
            self.runtime.advance_step(task)
            return {
                "ok": True,
                "action": "step_completed",
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
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
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
            }

        if decision == "retry":
            return self._handle_retry(task, current_tick, reason, reflection)

        if decision == "replan":
            return self._handle_replan(task, current_tick, reason, reflection)

        if decision == "wait":
            return {
                "ok": True,
                "action": "waiting",
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
            }

        # fail
        fail_result = self.runtime.mark_failed(
            task=task,
            current_tick=current_tick,
            failure_type="tool_error",
            failure_message=reason,
        )

        return {
            "ok": False,
            "action": "step_failed",
            "reflection": reflection,
            "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
            "runtime_result": fail_result,
        }

    # ============================================================
    # retry / replan helpers
    # ============================================================

    def _handle_retry(self, task, current_tick, reason, reflection):
        state = self.runtime.load_runtime_state(task)

        retry_count = int(state.get("retry_count", 0) or 0)
        max_retries = int(state.get("max_retries", 0) or 0)

        if retry_count >= max_retries:
            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="retry_exhausted",
                failure_message=reason,
            )
            return {
                "ok": False,
                "action": "step_failed",
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                "runtime_result": fail_result,
            }

        state["retry_count"] = retry_count + 1
        state["status"] = "retrying"
        state["last_error"] = reason
        state["failure_type"] = "tool_error"
        state["next_retry_tick"] = current_tick + 1

        self.runtime.save_runtime_state(task, state)

        return {
            "ok": True,
            "action": "retry_scheduled",
            "reflection": reflection,
            "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
        }

    def _handle_replan(self, task, current_tick, reason, reflection):
        state = self.runtime.load_runtime_state(task)

        replan_count = int(state.get("replan_count", 0) or 0)
        max_replans = int(state.get("max_replans", 1) or 1)

        if replan_count >= max_replans:
            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="replan_exhausted",
                failure_message=reason,
            )
            return {
                "ok": False,
                "action": "step_failed",
                "reflection": reflection,
                "task": copy.deepcopy(self.runtime.load_runtime_state(task)),
                "runtime_result": fail_result,
            }

        state["replan_count"] = replan_count + 1
        self.runtime.save_runtime_state(task, state)

        if self.replanner:
            replan_result = self.replanner.replan(
                goal=state.get("goal"),
                task_dir=state.get("task_dir"),
                plan_file=state.get("plan_file"),
                runtime_file=state.get("runtime_state_file"),
                reason=reason,
            )

            state = self.runtime.load_runtime_state(task)
            state["current_step_index"] = 0
            self.runtime.save_runtime_state(task, state)

            return {
                "ok": True,
                "action": "replanned",
                "reflection": reflection,
                "task": copy.deepcopy(state),
                "replan_result": replan_result,
            }

        return {
            "ok": False,
            "action": "step_failed",
            "reflection": reflection,
            "task": copy.deepcopy(state),
        }

    # ============================================================
    # helpers
    # ============================================================

    def _get_max_steps_per_tick(self, state: Dict[str, Any]) -> int:
        try:
            v = int(state.get("max_steps_per_tick", 1))
            return max(1, v)
        except Exception:
            return 1

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