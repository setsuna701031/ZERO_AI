from __future__ import annotations

import copy
import json
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, List

from core.memory.context_builder import build_context
from core.runtime.task_runner import TaskRunner


class AgentLoop:
    """
    ZERO Agent Loop v2 - decision record first pass

    本版重點：
    1. 保留 direct / task / llm / single-shot 主幹
    2. document flow 仍強制走 planner + task mode
    3. task mode 仍優先 scheduler.create_task + submit_existing_task
    4. run_task_loop() 保持 single-task / one-step-per-cycle
    5. 每一輪 loop 顯性輸出：
       - observation
       - decision
       - decision_reason
       - next_action
       - terminal_reason
    6. decision record 會回寫到 task：
       - last_observation
       - last_decision
       - last_decision_reason
       - next_action
       - terminal_reason
       - loop_cycle_count
       - loop_history
    """

    def __init__(
        self,
        router=None,
        planner=None,
        llm_planner=None,
        step_executor=None,
        verifier=None,
        safety_guard=None,
        memory_store=None,
        runtime_store=None,
        scheduler=None,
        task_manager=None,
        task_workspace=None,
        task_runtime=None,
        task_runner=None,
        replanner=None,
        llm_client=None,
        debug: bool = False,
        **kwargs,
    ) -> None:
        self.router = router
        self.planner = planner
        self.llm_planner = llm_planner
        self.step_executor = step_executor
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.llm_client = llm_client

        self.task_manager = task_manager
        self.scheduler = scheduler or task_manager

        self.task_workspace = task_workspace
        self.task_runtime = task_runtime
        self.replanner = replanner
        self.debug = debug
        self.extra_kwargs = kwargs

        self.task_runner = task_runner or TaskRunner(
            task_runtime=self.task_runtime,
            step_executor=self.step_executor,
            replanner=self.replanner,
            verifier=self.verifier,
            debug=self.debug,
        )

    # ============================================================
    # public entry
    # ============================================================

    def run(self, user_input: str) -> Dict[str, Any]:
        user_text = str(user_input or "").strip()
        if not user_text:
            return {"ok": False, "error": "empty input"}

        context = self._build_context(user_text)
        route = self._call_router(context=context, user_input=user_text)

        if self.debug:
            print("[AgentLoop] input =", user_text)
            print("[AgentLoop] route =", route)

        if self._should_force_planner_document_flow(user_text):
            if self.debug:
                print("[AgentLoop] document flow detected -> force task mode path")
            return self._run_task_mode(
                context=context,
                user_input=user_text,
                route=route,
            )

        direct_result = self._try_handle_direct_route(
            context=context,
            user_input=user_text,
            route=route,
        )
        if direct_result is not None:
            return direct_result

        if self._should_enter_task_mode(route=route, user_input=user_text):
            return self._run_task_mode(
                context=context,
                user_input=user_text,
                route=route,
            )

        llm_result = self._try_handle_llm_route(
            context=context,
            user_input=user_text,
            route=route,
        )
        if llm_result is not None:
            return llm_result

        return self._run_single_shot_mode(
            context=context,
            user_input=user_text,
            route=route,
        )

    def run_task(
        self,
        task: Any,
        *,
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.run_task_loop(
            task=task,
            current_tick=current_tick,
            user_input=user_input,
            original_plan=original_plan,
        )

    def run_task_loop(
        self,
        task: Any,
        *,
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Agent Loop v2 第一刀：
        single-task / one-step-per-cycle / explicit observation + decision record
        """
        try:
            task_dict = self._normalize_task_input(task)
            if not isinstance(task_dict, dict):
                return {
                    "ok": False,
                    "mode": "task_loop",
                    "action": "loop_failed",
                    "status": "failed",
                    "error": "task must be dict-like",
                }

            effective_user_input = str(user_input or task_dict.get("goal") or "").strip()
            effective_original_plan = (
                original_plan
                if isinstance(original_plan, dict)
                else task_dict.get("planner_result")
            )

            task_id = str(
                task_dict.get("task_id")
                or task_dict.get("task_name")
                or task_dict.get("id")
                or ""
            ).strip()

            task_dict.setdefault("loop_cycle_count", 0)
            task_dict.setdefault("loop_history", [])
            task_dict.setdefault("last_observation", {})
            task_dict.setdefault("last_decision", "")
            task_dict.setdefault("last_decision_reason", "")
            task_dict.setdefault("next_action", "")
            task_dict.setdefault("terminal_reason", "")

            loop_start_snapshot = self._snapshot_task_state(task_dict)

            if self.debug:
                print(
                    "[AgentLoop] run_task_loop:",
                    task_id,
                    "tick=",
                    current_tick,
                )

            backend_name = ""
            raw_runner_result: Dict[str, Any]

            try:
                raw_runner_result = self._call_task_runner_compat(
                    task=task_dict,
                    current_tick=current_tick,
                    user_input=effective_user_input,
                    original_plan=effective_original_plan,
                )
                backend_name = "task_runner"
            except Exception as runner_error:
                if self.debug:
                    print(f"[AgentLoop] task_runner compat failed: {runner_error}")

                scheduler_fallback = self._call_scheduler_simple_fallback(
                    task=task_dict,
                    current_tick=current_tick,
                )
                if scheduler_fallback is not None:
                    raw_runner_result = scheduler_fallback
                    backend_name = "scheduler_simple_fallback"
                else:
                    raise runner_error

            normalized_runner_result = self._normalize_loop_runner_result(
                runner_result=raw_runner_result,
                fallback_task=task_dict,
                backend_name=backend_name,
            )

            effective_task = self._derive_effective_task_from_runner_result(
                original_task=task_dict,
                runner_result=normalized_runner_result,
            )

            observation = self._build_loop_observation(
                before_snapshot=loop_start_snapshot,
                effective_task=effective_task,
                runner_result=normalized_runner_result,
                current_tick=current_tick,
            )

            transition = self._build_loop_transition(
                before_snapshot=loop_start_snapshot,
                after_task=effective_task,
                runner_result=normalized_runner_result,
            )

            decision_bundle = self._build_loop_decision(
                before_snapshot=loop_start_snapshot,
                effective_task=effective_task,
                runner_result=normalized_runner_result,
                observation=observation,
                transition=transition,
            )

            effective_task["last_observation"] = copy.deepcopy(observation)
            effective_task["last_decision"] = decision_bundle["decision"]
            effective_task["last_decision_reason"] = decision_bundle["decision_reason"]
            effective_task["next_action"] = decision_bundle["next_action"]
            effective_task["terminal_reason"] = decision_bundle["terminal_reason"]
            effective_task["loop_cycle_count"] = int(effective_task.get("loop_cycle_count", 0)) + 1

            history_item = {
                "tick": int(current_tick),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "observation": copy.deepcopy(observation),
                "transition": copy.deepcopy(transition),
                "decision": decision_bundle["decision"],
                "decision_reason": decision_bundle["decision_reason"],
                "next_action": decision_bundle["next_action"],
                "terminal_reason": decision_bundle["terminal_reason"],
            }
            loop_history = effective_task.get("loop_history")
            if not isinstance(loop_history, list):
                loop_history = []
            loop_history.append(history_item)
            effective_task["loop_history"] = loop_history

            write_back = self._write_back_loop_state(
                task=effective_task,
                plan=effective_original_plan,
            )

            final_answer = self._extract_loop_final_answer(
                runner_result=normalized_runner_result,
                effective_task=effective_task,
                fallback=effective_user_input,
            )

            result: Dict[str, Any] = {
                "ok": bool(normalized_runner_result.get("ok", True)),
                "mode": "task_loop",
                "action": "one_step_cycle",
                "loop_backend": backend_name,
                "current_tick": int(current_tick),
                "task_id": task_id,
                "task": effective_task,
                "status": str(
                    normalized_runner_result.get("status")
                    or effective_task.get("status")
                    or "running"
                ).strip().lower(),
                "final_answer": final_answer,
                "error": normalized_runner_result.get("error"),
                "observation": observation,
                "transition": transition,
                "decision": decision_bundle["decision"],
                "decision_reason": decision_bundle["decision_reason"],
                "next_action": decision_bundle["next_action"],
                "terminal_reason": decision_bundle["terminal_reason"],
                "write_back": write_back,
                "runner_result": normalized_runner_result,
            }

            return result

        except Exception as e:
            return {
                "ok": False,
                "mode": "task_loop",
                "action": "loop_failed",
                "status": "failed",
                "error": f"agent_loop.run_task_loop failed: {e}",
                "traceback": traceback.format_exc(),
            }

    def _call_task_runner_compat(
        self,
        *,
        task: Dict[str, Any],
        current_tick: int,
        user_input: str,
        original_plan: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        runner = self.task_runner
        if runner is None:
            raise AttributeError("task_runner missing")

        candidates = [
            "run_one_tick",
            "run_one_step",
            "run_task",
            "run",
        ]

        for method_name in candidates:
            fn = getattr(runner, method_name, None)
            if not callable(fn):
                continue

            call_variants = [
                {
                    "task": task,
                    "current_tick": current_tick,
                    "user_input": user_input,
                    "original_plan": original_plan,
                },
                {
                    "task": task,
                    "current_tick": current_tick,
                    "user_input": user_input,
                },
                {
                    "task": task,
                    "current_tick": current_tick,
                },
                {
                    "task": task,
                    "user_input": user_input,
                },
                {
                    "task": task,
                },
            ]

            for kwargs in call_variants:
                try:
                    result = fn(**kwargs)
                    return result if isinstance(result, dict) else {
                        "ok": bool(result),
                        "action": method_name,
                        "status": "running",
                        "result": result,
                    }
                except TypeError:
                    continue

            positional_variants = [
                (task,),
                (task, current_tick),
                (task, current_tick, user_input),
            ]

            for args in positional_variants:
                try:
                    result = fn(*args)
                    return result if isinstance(result, dict) else {
                        "ok": bool(result),
                        "action": method_name,
                        "status": "running",
                        "result": result,
                    }
                except TypeError:
                    continue

        raise AttributeError(
            "TaskRunner has no compatible method among: run_one_tick, run_one_step, run_task, run"
        )

    def _call_scheduler_simple_fallback(
        self,
        *,
        task: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        scheduler = self.scheduler
        if scheduler is None:
            return None

        fallback_fn = getattr(scheduler, "_run_simple_task_tick", None)
        if not callable(fallback_fn):
            return None

        return fallback_fn(
            task=copy.deepcopy(task),
            current_tick=current_tick,
        )

    # ============================================================
    # Agent Loop v2 helpers
    # ============================================================

    def _snapshot_task_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": str(task.get("status") or "").strip().lower(),
            "current_step_index": self._safe_int(task.get("current_step_index"), 0),
            "steps_total": self._safe_int(task.get("steps_total"), len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0),
            "final_answer": str(task.get("final_answer") or ""),
            "last_error": str(task.get("last_error") or ""),
            "blocked_reason": str(task.get("blocked_reason") or ""),
        }

    def _normalize_loop_runner_result(
        self,
        *,
        runner_result: Any,
        fallback_task: Dict[str, Any],
        backend_name: str,
    ) -> Dict[str, Any]:
        if isinstance(runner_result, dict):
            normalized = copy.deepcopy(runner_result)
        else:
            normalized = {
                "ok": bool(runner_result),
                "result": runner_result,
            }

        normalized.setdefault("ok", True)
        normalized.setdefault("mode", "task_loop")
        normalized.setdefault("loop_backend", backend_name)

        if "status" not in normalized or not str(normalized.get("status") or "").strip():
            candidate_task = normalized.get("task")
            if isinstance(candidate_task, dict):
                normalized["status"] = str(candidate_task.get("status") or "").strip().lower()
            else:
                normalized["status"] = str(fallback_task.get("status") or "running").strip().lower()

        if "action" not in normalized or not str(normalized.get("action") or "").strip():
            normalized["action"] = "loop_cycle"

        return normalized

    def _derive_effective_task_from_runner_result(
        self,
        *,
        original_task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        effective_task = copy.deepcopy(original_task)

        candidate_task = runner_result.get("task")
        if isinstance(candidate_task, dict):
            merged = copy.deepcopy(effective_task)
            merged.update(copy.deepcopy(candidate_task))
            effective_task = merged

        overlay_keys = [
            "status",
            "final_answer",
            "last_error",
            "failure_message",
            "blocked_reason",
            "current_step_index",
            "steps",
            "steps_total",
            "results",
            "step_results",
            "execution_log",
            "last_step_result",
            "current_step",
            "replanned",
            "replan_reason",
            "replan_count",
        ]
        for key in overlay_keys:
            if key in runner_result:
                effective_task[key] = copy.deepcopy(runner_result.get(key))

        return effective_task

    def _build_loop_observation(
        self,
        *,
        before_snapshot: Dict[str, Any],
        effective_task: Dict[str, Any],
        runner_result: Dict[str, Any],
        current_tick: int,
    ) -> Dict[str, Any]:
        after_status = str(
            runner_result.get("status")
            or effective_task.get("status")
            or ""
        ).strip().lower()

        after_step_index = self._safe_int(
            effective_task.get("current_step_index"),
            before_snapshot.get("current_step_index", 0),
        )

        steps_total = self._safe_int(
            effective_task.get("steps_total"),
            len(effective_task.get("steps", [])) if isinstance(effective_task.get("steps"), list) else before_snapshot.get("steps_total", 0),
        )

        observed_result = runner_result.get("last_step_result")
        if observed_result is None:
            observed_result = effective_task.get("last_step_result")
        if observed_result is None:
            observed_result = runner_result.get("result")

        return {
            "tick": int(current_tick),
            "before_status": before_snapshot.get("status", ""),
            "after_status": after_status,
            "before_step_index": before_snapshot.get("current_step_index", 0),
            "after_step_index": after_step_index,
            "steps_total": steps_total,
            "observed_result": copy.deepcopy(observed_result),
            "last_error": str(
                runner_result.get("error")
                or effective_task.get("last_error")
                or ""
            ).strip(),
            "final_answer": str(
                runner_result.get("final_answer")
                or effective_task.get("final_answer")
                or ""
            ).strip(),
        }

    def _build_loop_transition(
        self,
        *,
        before_snapshot: Dict[str, Any],
        after_task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        before_status = str(before_snapshot.get("status") or "").strip().lower()
        after_status = str(
            runner_result.get("status")
            or after_task.get("status")
            or ""
        ).strip().lower()

        before_step = self._safe_int(before_snapshot.get("current_step_index"), 0)
        after_step = self._safe_int(after_task.get("current_step_index"), before_step)

        return {
            "from_status": before_status,
            "to_status": after_status,
            "from_step_index": before_step,
            "to_step_index": after_step,
            "step_advanced": after_step > before_step,
            "status_changed": before_status != after_status,
        }

    def _build_loop_decision(
        self,
        *,
        before_snapshot: Dict[str, Any],
        effective_task: Dict[str, Any],
        runner_result: Dict[str, Any],
        observation: Dict[str, Any],
        transition: Dict[str, Any],
    ) -> Dict[str, str]:
        status = str(
            runner_result.get("status")
            or effective_task.get("status")
            or ""
        ).strip().lower()

        last_error = str(
            runner_result.get("error")
            or effective_task.get("last_error")
            or ""
        ).strip()

        blocked_reason = str(effective_task.get("blocked_reason") or "").strip()

        if status == "finished":
            return {
                "decision": "terminate_success",
                "decision_reason": "task reached finished state",
                "next_action": "none",
                "terminal_reason": "finished",
            }

        if status in {"failed", "error"}:
            return {
                "decision": "terminate_failure",
                "decision_reason": last_error or "task entered failed state",
                "next_action": "none",
                "terminal_reason": "failed",
            }

        if status == "blocked":
            return {
                "decision": "pause_blocked",
                "decision_reason": blocked_reason or "task entered blocked state",
                "next_action": "wait_or_unblock",
                "terminal_reason": "blocked",
            }

        if transition.get("step_advanced"):
            return {
                "decision": "continue",
                "decision_reason": "step advanced this cycle",
                "next_action": "run_next_cycle",
                "terminal_reason": "",
            }

        if transition.get("status_changed"):
            return {
                "decision": "continue",
                "decision_reason": f"status changed to {status}",
                "next_action": "run_next_cycle",
                "terminal_reason": "",
            }

        if last_error:
            return {
                "decision": "inspect",
                "decision_reason": last_error,
                "next_action": "review_last_error",
                "terminal_reason": "",
            }

        return {
            "decision": "continue",
            "decision_reason": "task remains active after this cycle",
            "next_action": "run_next_cycle",
            "terminal_reason": "",
        }

    def _write_back_loop_state(
        self,
        *,
        task: Dict[str, Any],
        plan: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        write_back = {
            "ok": True,
            "task_snapshot_saved": False,
            "plan_saved": False,
            "runtime_state_ensured": False,
            "runtime_state_saved": False,
            "repo_persisted": False,
            "errors": [],
        }

        workspace = self.task_workspace
        runtime = self.task_runtime
        scheduler = self.scheduler

        if workspace is None and scheduler is not None:
            workspace = getattr(scheduler, "task_workspace", None)

        if runtime is None and scheduler is not None:
            runtime = getattr(scheduler, "task_runtime", None)

        runtime_state: Optional[Dict[str, Any]] = None
        loop_keys = (
            "last_observation",
            "last_decision",
            "last_decision_reason",
            "next_action",
            "terminal_reason",
            "loop_cycle_count",
            "loop_history",
        )

        if runtime is not None:
            try:
                load_fn = getattr(runtime, "load_runtime_state", None)
                if callable(load_fn):
                    loaded = load_fn(task)
                    if isinstance(loaded, dict):
                        runtime_state = copy.deepcopy(loaded)
            except Exception as e:
                write_back["ok"] = False
                write_back["errors"].append(f"load_runtime_state failed: {e}")

            if not isinstance(runtime_state, dict):
                runtime_state = {}

            for key in loop_keys:
                if key in task:
                    runtime_state[key] = copy.deepcopy(task.get(key))

            for key in (
                "status",
                "final_answer",
                "last_error",
                "failure_message",
                "blocked_reason",
                "current_step_index",
                "steps",
                "steps_total",
                "results",
                "step_results",
                "execution_log",
                "last_step_result",
                "planner_result",
                "history",
                "task_name",
                "task_id",
                "goal",
                "task_dir",
                "runtime_state_file",
                "plan_file",
                "result_file",
                "execution_log_file",
                "log_file",
                "workspace_root",
                "workspace_dir",
                "shared_dir",
            ):
                if key in task:
                    runtime_state[key] = copy.deepcopy(task.get(key))

            ensure_fn = getattr(runtime, "ensure_runtime_state", None)
            if callable(ensure_fn):
                try:
                    ensured = ensure_fn(task)
                    if isinstance(ensured, dict):
                        runtime_state = copy.deepcopy(ensured)
                    write_back["runtime_state_ensured"] = True
                except Exception as e:
                    write_back["ok"] = False
                    write_back["errors"].append(f"ensure_runtime_state failed: {e}")

            for key in loop_keys:
                if key in task:
                    runtime_state[key] = copy.deepcopy(task.get(key))

            save_runtime_state_fn = getattr(runtime, "save_runtime_state", None)
            if callable(save_runtime_state_fn):
                try:
                    saved = save_runtime_state_fn(task, runtime_state)
                    if isinstance(saved, dict):
                        runtime_state = copy.deepcopy(saved)
                    write_back["runtime_state_saved"] = True
                except Exception as e:
                    write_back["ok"] = False
                    write_back["errors"].append(f"save_runtime_state failed: {e}")
            else:
                save_state_fn = getattr(runtime, "save_state", None)
                if callable(save_state_fn):
                    try:
                        saved = save_state_fn(task, runtime_state)
                        if isinstance(saved, dict):
                            runtime_state = copy.deepcopy(saved)
                        write_back["runtime_state_saved"] = True
                    except TypeError:
                        try:
                            save_state_fn(task)
                            write_back["runtime_state_saved"] = True
                        except Exception as e:
                            write_back["ok"] = False
                            write_back["errors"].append(f"save_state failed: {e}")
                    except Exception as e:
                        write_back["ok"] = False
                        write_back["errors"].append(f"save_state failed: {e}")

            sync_task_fn = getattr(runtime, "_sync_task_from_runtime_state", None)
            if callable(sync_task_fn) and isinstance(runtime_state, dict):
                try:
                    sync_task_fn(task, runtime_state)
                except Exception as e:
                    write_back["ok"] = False
                    write_back["errors"].append(f"_sync_task_from_runtime_state failed: {e}")

        if workspace is not None:
            save_snapshot_fn = getattr(workspace, "save_task_snapshot", None)
            if callable(save_snapshot_fn):
                try:
                    save_snapshot_fn(task)
                    write_back["task_snapshot_saved"] = True
                except Exception as e:
                    write_back["ok"] = False
                    write_back["errors"].append(f"save_task_snapshot failed: {e}")

            save_plan_fn = getattr(workspace, "save_plan", None)
            if callable(save_plan_fn) and isinstance(plan, dict):
                try:
                    save_plan_fn(task, plan)
                    write_back["plan_saved"] = True
                except Exception as e:
                    write_back["ok"] = False
                    write_back["errors"].append(f"save_plan failed: {e}")

        if scheduler is not None:
            persist_fn = getattr(scheduler, "_persist_task_payload", None)
            if callable(persist_fn):
                task_id = str(
                    task.get("task_id")
                    or task.get("task_name")
                    or task.get("id")
                    or ""
                ).strip()
                if task_id:
                    try:
                        persist_fn(task_id=task_id, task=copy.deepcopy(task))
                        write_back["repo_persisted"] = True
                    except Exception as e:
                        write_back["ok"] = False
                        write_back["errors"].append(f"_persist_task_payload failed: {e}")

        if isinstance(runtime_state, dict):
            write_back["runtime_state"] = copy.deepcopy(runtime_state)

        return write_back

    def _extract_loop_final_answer(
        self,
        *,
        runner_result: Dict[str, Any],
        effective_task: Dict[str, Any],
        fallback: str,
    ) -> str:
        direct = runner_result.get("final_answer")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        task_answer = effective_task.get("final_answer")
        if isinstance(task_answer, str) and task_answer.strip():
            return task_answer.strip()

        last_step_result = runner_result.get("last_step_result")
        if isinstance(last_step_result, dict):
            summary = self._summarize_step_result(
                last_step_result,
                failed=bool(last_step_result.get("ok") is False),
            )
            if isinstance(summary, str) and summary.strip():
                return summary.strip()

        return self._extract_final_answer(runner_result, None, fallback)

    # ============================================================
    # special routing guard
    # ============================================================

    def _should_force_planner_document_flow(self, user_input: str) -> bool:
        text = str(user_input or "").strip().lower()
        if not text:
            return False

        if self._looks_like_summary_document_flow(text):
            return True

        if self._looks_like_action_items_document_flow(text):
            return True

        return False

    def _looks_like_summary_document_flow(self, text: str) -> bool:
        summary_keywords = ["summary", "summarize", "summarise", "摘要", "總結"]
        has_summary = any(k in text for k in summary_keywords)
        has_doc_path = bool(re.search(r"[a-z0-9_\-./\\]+\.(txt|md|log|json|csv|yaml|yml)\b", text))
        return has_summary and has_doc_path

    def _looks_like_action_items_document_flow(self, text: str) -> bool:
        action_keywords = ["action item", "action items", "待辦事項", "行動項目", "todo", "to-do"]
        has_action = any(k in text for k in action_keywords)
        has_doc_path = bool(re.search(r"[a-z0-9_\-./\\]+\.(txt|md|log|json|csv|yaml|yml)\b", text))
        return has_action and has_doc_path

    # ============================================================
    # router-first handling
    # ============================================================

    def _try_handle_direct_route(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(route, dict):
            return None

        if route.get("mode") != "direct":
            return None

        step = route.get("step")
        if not isinstance(step, dict):
            return {
                "ok": False,
                "mode": "direct",
                "context": context,
                "route": route,
                "error": "router returned direct mode but step missing",
            }

        execution_result = self._execute_direct_step(
            step=step,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)

        return {
            "ok": bool(execution_result.get("ok", True)) if isinstance(execution_result, dict) else True,
            "mode": "direct",
            "context": context,
            "route": route,
            "plan": None,
            "execution": execution_result,
            "final_answer": self._extract_final_answer(execution_result, None, user_input),
        }

    def _try_handle_llm_route(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(route, dict):
            return None

        if route.get("mode") != "llm":
            return None

        if self.llm_client is None:
            return {
                "ok": True,
                "mode": "llm",
                "context": context,
                "route": route,
                "plan": None,
                "execution": None,
                "final_answer": "目前聊天模式尚未啟用。",
            }

        if self.llm_planner is None:
            fallback_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(fallback_result, dict):
                fallback_result["mode"] = "llm_fallback_single_shot"
            return fallback_result

        llm_plan = self._call_llm_planner(
            context=context,
            user_input=user_input,
            route=route,
        )

        if self.debug:
            print("[AgentLoop] llm_plan =", llm_plan)

        if not isinstance(llm_plan, dict):
            fallback_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(fallback_result, dict):
                fallback_result["mode"] = "llm_fallback_single_shot"
                fallback_result["llm_plan_error"] = "llm_plan invalid"
            return fallback_result

        if llm_plan.get("ok") is False:
            fallback_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(fallback_result, dict):
                fallback_result["mode"] = "llm_fallback_single_shot"
                fallback_result["llm_plan_error"] = llm_plan.get("error")
            return fallback_result

        steps = self._extract_steps_from_plan(llm_plan)

        if not steps:
            return {
                "ok": True,
                "mode": "llm",
                "context": context,
                "route": route,
                "plan": llm_plan,
                "execution": None,
                "final_answer": self._extract_final_answer(None, llm_plan, user_input),
            }

        execution_result = self._execute_single_shot_steps(
            steps=steps,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)

        return {
            "ok": bool(execution_result.get("ok", True)) if isinstance(execution_result, dict) else True,
            "mode": "llm",
            "context": context,
            "route": route,
            "plan": llm_plan,
            "execution": execution_result,
            "final_answer": self._extract_final_answer(execution_result, llm_plan, user_input),
        }

    def _execute_direct_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        if not self.step_executor:
            return {
                "ok": False,
                "error": "step_executor missing",
                "step": copy.deepcopy(step),
                "final_answer": "step_executor missing",
            }

        step_result = self._call_step_executor(
            step=step,
            context=context,
            user_input=user_input,
            route=route,
            previous_result=None,
            step_index=1,
            step_count=1,
        )

        if not isinstance(step_result, dict):
            step_result = {
                "ok": False,
                "error": "step_executor returned invalid result",
                "raw_result": step_result,
                "step": copy.deepcopy(step),
            }

        return {
            "ok": bool(step_result.get("ok", True)),
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": copy.deepcopy(step),
                    "result": copy.deepcopy(step_result),
                }
            ],
            "last_result": step_result,
            "final_answer": self._summarize_step_result(
                step_result,
                failed=bool(step_result.get("ok") is False),
            ),
        }

    # ============================================================
    # single-shot mode
    # ============================================================

    def _run_single_shot_mode(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        plan = self._call_planner(
            context=context,
            user_input=user_input,
            route=route,
        )

        if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
            return {
                "ok": False,
                "mode": "single_shot",
                "error": plan.get("error", "planner call failed"),
                "traceback": plan.get("traceback"),
            }

        if plan is None:
            return {
                "ok": True,
                "mode": "single_shot",
                "context": context,
                "route": route,
                "final_answer": user_input,
            }

        steps = self._extract_steps_from_plan(plan)

        if self.debug:
            print("[AgentLoop] single-shot steps =", steps)

        if not steps:
            return {
                "ok": True,
                "mode": "single_shot",
                "context": context,
                "route": route,
                "plan": plan,
                "execution": None,
                "final_answer": self._extract_final_answer(None, plan, user_input),
            }

        execution_result = self._execute_single_shot_steps(
            steps=steps,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)

        try:
            self._maybe_write_document_flow_trace(
                steps=steps,
                execution_result=execution_result,
            )
        except Exception as e:
            if self.debug:
                print(f"[AgentLoop] document flow trace write failed: {e}")

        return {
            "ok": bool(execution_result.get("ok", True)) if isinstance(execution_result, dict) else True,
            "mode": "single_shot",
            "context": context,
            "route": route,
            "plan": plan,
            "execution": execution_result,
            "final_answer": self._extract_final_answer(execution_result, plan, user_input),
        }

    def _execute_single_shot_steps(
        self,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        if not self.step_executor:
            return {
                "ok": False,
                "error": "step_executor missing",
                "steps": copy.deepcopy(steps),
                "final_answer": "step_executor missing",
            }

        results: List[Dict[str, Any]] = []
        previous_result: Any = None
        last_result: Dict[str, Any] = {}

        for index, step in enumerate(steps, start=1):
            step_result = self._call_step_executor(
                step=step,
                context=context,
                user_input=user_input,
                route=route,
                previous_result=previous_result,
                step_index=index,
                step_count=len(steps),
            )

            if not isinstance(step_result, dict):
                step_result = {
                    "ok": False,
                    "error": "step_executor returned invalid result",
                    "raw_result": step_result,
                    "step": copy.deepcopy(step),
                }

            results.append(
                {
                    "step_index": index,
                    "step": copy.deepcopy(step),
                    "result": copy.deepcopy(step_result),
                }
            )

            last_result = step_result
            previous_result = step_result

            if step_result.get("ok") is False:
                return {
                    "ok": False,
                    "steps_executed": index,
                    "results": results,
                    "last_result": last_result,
                    "final_answer": self._summarize_step_result(last_result, failed=True),
                }

        return {
            "ok": True,
            "steps_executed": len(steps),
            "results": results,
            "last_result": last_result,
            "final_answer": self._summarize_step_result(last_result, failed=False),
        }

    # ============================================================
    # document flow trace integration
    # ============================================================

    def _maybe_write_document_flow_trace(
        self,
        *,
        steps: List[Dict[str, Any]],
        execution_result: Dict[str, Any],
    ) -> None:
        if not isinstance(execution_result, dict):
            return
        if not execution_result.get("ok", False):
            return
        if not isinstance(steps, list) or len(steps) < 3:
            return

        flow_kind = self._detect_document_flow_kind(steps)
        if not flow_kind:
            return

        step_results = execution_result.get("results")
        if not isinstance(step_results, list) or len(step_results) < 3:
            return

        read_result = self._get_result_payload(step_results, 0)
        llm_result = self._get_result_payload(step_results, 1)
        write_result = self._get_result_payload(step_results, 2)

        input_full_path = self._extract_path_from_payload(read_result) or self._default_shared_path("input.txt")
        output_full_path = self._extract_path_from_payload(write_result) or self._default_shared_path(
            "action_items.txt" if flow_kind == "action_items" else "summary.txt"
        )

        input_content = self._extract_content_from_payload(read_result)
        output_content = self._extract_content_from_payload(write_result)
        if not output_content:
            output_content = self._extract_content_from_payload(llm_result)

        runtime_info = self._get_runtime_info()

        trace = self._build_document_flow_trace(
            flow_kind=flow_kind,
            input_path=input_full_path,
            output_path=output_full_path,
            input_text=input_content,
            output_text=output_content,
            runtime_info=runtime_info,
        )

        trace_path = self._default_shared_path("document_flow_trace.json")
        os.makedirs(os.path.dirname(trace_path), exist_ok=True)
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)

        if self.debug:
            print(f"[AgentLoop] wrote document flow trace: {trace_path}")

    def _detect_document_flow_kind(self, steps: List[Dict[str, Any]]) -> str:
        if len(steps) < 3:
            return ""

        step1 = steps[0] if isinstance(steps[0], dict) else {}
        step2 = steps[1] if isinstance(steps[1], dict) else {}
        step3 = steps[2] if isinstance(steps[2], dict) else {}

        type1 = str(step1.get("type", "")).strip().lower()
        type2 = str(step2.get("type", "")).strip().lower()
        type3 = str(step3.get("type", "")).strip().lower()

        mode2 = str(step2.get("mode", "")).strip().lower()
        path3 = str(step3.get("path", "")).strip().lower()

        if type1 != "read_file" or type2 not in {"llm", "llm_generate"} or type3 != "write_file":
            return ""

        if mode2 == "action_items" or "action_items" in path3 or "action-items" in path3:
            return "action_items"

        if mode2 == "summary" or "summary" in path3:
            return "summary"

        return ""

    def _build_document_flow_trace(
        self,
        *,
        flow_kind: str,
        input_path: str,
        output_path: str,
        input_text: str,
        output_text: str,
        runtime_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        if flow_kind == "action_items":
            return {
                "flow": "document_action_items_demo",
                "status": "finished",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "workspace_root": os.path.abspath("workspace"),
                "shared_dir": self._default_shared_dir(),
                "input_path": input_path,
                "output_path": output_path,
                "trace_path": self._default_shared_path("document_flow_trace.json"),
                "input_chars": len(input_text),
                "action_items_chars": len(output_text),
                "runtime_info": runtime_info,
                "error": "",
                "steps": [
                    {"step": 1, "name": "read_input", "path": input_path},
                    {"step": 2, "name": "extract_action_items"},
                    {"step": 3, "name": "write_action_items", "path": output_path},
                ],
            }

        return {
            "flow": "document_summary_demo",
            "status": "finished",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "workspace_root": os.path.abspath("workspace"),
            "shared_dir": self._default_shared_dir(),
            "input_path": input_path,
            "output_path": output_path,
            "trace_path": self._default_shared_path("document_flow_trace.json"),
            "input_chars": len(input_text),
            "summary_chars": len(output_text),
            "runtime_info": runtime_info,
            "error": "",
            "steps": [
                {"step": 1, "name": "read_input", "path": input_path},
                {"step": 2, "name": "summarize_document"},
                {"step": 3, "name": "write_summary", "path": output_path},
            ],
        }

    def _get_result_payload(self, execution_results: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
        if not isinstance(execution_results, list):
            return {}
        if index < 0 or index >= len(execution_results):
            return {}
        item = execution_results[index]
        if not isinstance(item, dict):
            return {}
        result = item.get("result")
        if isinstance(result, dict):
            return result
        return {}

    def _extract_path_from_payload(self, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        result_block = payload.get("result")
        if isinstance(result_block, dict):
            for key in ("full_path", "path"):
                value = result_block.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("full_path", "path"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_content_from_payload(self, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        result_block = payload.get("result")
        if isinstance(result_block, dict):
            for key in ("content", "text", "message"):
                value = result_block.get(key)
                if isinstance(value, str):
                    return value
        for key in ("content", "text", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return ""

    def _get_runtime_info(self) -> Dict[str, Any]:
        llm_client = self.llm_client
        if llm_client is None and self.step_executor is not None:
            llm_client = getattr(self.step_executor, "llm_client", None)

        if llm_client is None:
            return {}

        get_runtime_info = getattr(llm_client, "get_runtime_info", None)
        if callable(get_runtime_info):
            try:
                info = get_runtime_info()
                if isinstance(info, dict):
                    return info
            except Exception:
                return {}

        return {
            "plugin_name": str(getattr(llm_client, "plugin_name", "") or ""),
            "provider": str(getattr(llm_client, "provider", "") or ""),
            "base_url": str(getattr(llm_client, "base_url", "") or ""),
            "model": str(getattr(llm_client, "model", "") or ""),
            "coder_model": str(getattr(llm_client, "coder_model", "") or ""),
            "timeout": getattr(llm_client, "timeout", None),
        }

    def _default_shared_dir(self) -> str:
        return os.path.abspath(os.path.join("workspace", "shared"))

    def _default_shared_path(self, filename: str) -> str:
        return os.path.abspath(os.path.join("workspace", "shared", filename))

    # ============================================================
    # task mode
    # ============================================================

    def _run_task_mode(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        task_entry = self.scheduler or self.task_manager
        if task_entry is None:
            return {
                "ok": False,
                "mode": "task",
                "error": "scheduler/task_manager missing",
            }

        if self.planner is None:
            return {
                "ok": False,
                "mode": "task",
                "error": "planner missing",
            }

        try:
            plan = self._call_planner(
                context=context,
                user_input=user_input,
                route=route,
            )

            if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
                return {
                    "ok": False,
                    "mode": "task",
                    "error": plan.get("error", "planner call failed"),
                    "traceback": plan.get("traceback"),
                }

            if self._supports_scheduler_create_submit(task_entry):
                return self._run_task_mode_via_scheduler(
                    task_entry=task_entry,
                    context=context,
                    user_input=user_input,
                    route=route,
                    plan=plan,
                )

            return self._run_task_mode_legacy_enqueue(
                task_entry=task_entry,
                context=context,
                user_input=user_input,
                route=route,
                plan=plan,
            )

        except Exception as e:
            return {
                "ok": False,
                "mode": "task",
                "error": f"task mode failed: {e}",
                "traceback": traceback.format_exc(),
            }

    def _run_task_mode_via_scheduler(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        priority = self._route_int(route, "priority", 0)
        max_replans = self._route_int(route, "max_replans", 1)
        timeout_ticks = self._route_int(route, "timeout_ticks", 0)
        depends_on = self._route_depends_on(route)

        create_result = task_entry.create_task(
            goal=user_input,
            priority=priority,
            timeout_ticks=timeout_ticks,
            depends_on=depends_on,
        )

        if not isinstance(create_result, dict) or not create_result.get("ok"):
            return {
                "ok": False,
                "mode": "task",
                "error": (
                    create_result.get("error", "scheduler.create_task failed")
                    if isinstance(create_result, dict)
                    else "scheduler.create_task failed"
                ),
                "create_result": create_result,
            }

        created_task = create_result.get("task")
        if not isinstance(created_task, dict):
            task_id = str(create_result.get("task_name") or "").strip()
            created_task = self._get_task_from_entry(task_entry, task_id)
        else:
            created_task = self._normalize_task_input(created_task)

        if not isinstance(created_task, dict):
            return {
                "ok": False,
                "mode": "task",
                "error": "created task missing or invalid",
                "create_result": create_result,
            }

        created_task["planner_result"] = plan if isinstance(plan, dict) else {}
        created_task["steps"] = self._extract_steps_from_plan(plan)
        created_task["steps_total"] = len(created_task["steps"])
        created_task["final_answer"] = ""
        created_task["max_replans"] = max_replans

        if isinstance(route, dict):
            created_task["route"] = copy.deepcopy(route)
        if isinstance(context, dict):
            created_task["context_snapshot"] = copy.deepcopy(context)

        created_task.setdefault("results", [])
        created_task.setdefault("step_results", [])
        created_task.setdefault("execution_log", [])
        created_task.setdefault("last_step_result", None)
        created_task.setdefault("last_error", None)
        created_task.setdefault("current_step_index", 0)
        created_task.setdefault("replanned", False)
        created_task.setdefault("replan_reason", "")
        created_task.setdefault("replan_count", 0)
        created_task.setdefault("loop_cycle_count", 0)
        created_task.setdefault("loop_history", [])
        created_task.setdefault("last_observation", {})
        created_task.setdefault("last_decision", "")
        created_task.setdefault("last_decision_reason", "")
        created_task.setdefault("next_action", "")
        created_task.setdefault("terminal_reason", "")

        self._save_task_plan_and_runtime(
            task=created_task,
            plan=created_task["planner_result"],
        )
        self._persist_task_to_entry(task_entry=task_entry, task=created_task)

        task_id = str(
            created_task.get("task_id")
            or created_task.get("id")
            or created_task.get("task_name")
            or ""
        ).strip()

        submit_result = task_entry.submit_existing_task(task_id)
        refreshed_task = self._get_task_from_entry(task_entry, task_id) or created_task

        return {
            "ok": True,
            "mode": "task",
            "context": context,
            "route": route,
            "task": refreshed_task,
            "task_id": task_id,
            "task_dir": refreshed_task.get("task_dir"),
            "plan": refreshed_task.get("planner_result"),
            "create_result": create_result,
            "submit_result": submit_result,
            "final_answer": f"已建立任務：{refreshed_task.get('title') or refreshed_task.get('goal')}",
        }

    def _run_task_mode_legacy_enqueue(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        task = self._build_task_shell(
            user_input=user_input,
            context=context,
            route=route,
        )

        if self.task_workspace is not None:
            try:
                task = self.task_workspace.create_workspace(task)
            except Exception as e:
                return {
                    "ok": False,
                    "mode": "task",
                    "error": f"task_workspace.create_workspace failed: {e}",
                    "traceback": traceback.format_exc(),
                }

        task["planner_result"] = plan if isinstance(plan, dict) else {}
        task["steps"] = self._extract_steps_from_plan(plan)
        task["steps_total"] = len(task["steps"])
        task["final_answer"] = ""
        task.setdefault("loop_cycle_count", 0)
        task.setdefault("loop_history", [])
        task.setdefault("last_observation", {})
        task.setdefault("last_decision", "")
        task.setdefault("last_decision_reason", "")
        task.setdefault("next_action", "")
        task.setdefault("terminal_reason", "")

        if self.task_workspace is not None:
            try:
                self.task_workspace.save_plan(task, task["planner_result"])
            except Exception:
                pass

        if self.task_runtime is not None:
            try:
                self.task_runtime.ensure_runtime_state(task)
            except Exception:
                pass

        enqueue_result = self._enqueue_task(task_entry, task)

        enqueued_task_dict = self._normalize_task_input(enqueue_result) if enqueue_result is not None else None
        if isinstance(enqueued_task_dict, dict):
            task = enqueued_task_dict

        return {
            "ok": True,
            "mode": "task",
            "context": context,
            "route": route,
            "task": task,
            "task_id": task.get("task_id") or task.get("id") or task.get("task_name"),
            "task_dir": task.get("task_dir"),
            "plan": task.get("planner_result"),
            "enqueue_result": enqueue_result,
            "final_answer": f"已建立任務：{task.get('title') or task.get('goal')}",
        }

    # ============================================================
    # loop helpers
    # ============================================================

    def _build_context(self, user_input: str) -> Dict[str, Any]:
        context = build_context(
            user_input=user_input,
            memory_store=self.memory_store,
            runtime_store=self.runtime_store,
        )
        if self.debug:
            print("[AgentLoop] context =", context)
        return context

    def _looks_like_explicit_task_request(self, text: str) -> bool:
        t = str(text or "").strip().lower()
        if not t:
            return False

        explicit_patterns = [
            r"^\s*task\s+",
            r"\bcreate task\b",
            r"\bnew task\b",
            r"\bsubmit task\b",
            r"\bschedule\b",
            r"\bqueue\b",
            r"\bbackground\b",
            r"\blong[- ]running\b",
            r"\brun in background\b",
            r"\benqueue\b",
            r"建立任務",
            r"新增任務",
            r"提交任務",
            r"排程",
            r"加入佇列",
            r"背景執行",
            r"長任務",
        ]

        return any(re.search(p, t) for p in explicit_patterns)

    def _should_enter_task_mode(self, route: Any, user_input: str) -> bool:
        if isinstance(route, dict):
            if route.get("mode") == "task":
                return True
            if route.get("type") == "task":
                return True
            if route.get("task") is True:
                return True
            if route.get("long_running") is True:
                return True

            route_intent = str(route.get("intent") or "").strip().lower()
            if route_intent in {"task", "task_execution", "agent_task"}:
                return True

            route_action = str(route.get("action") or "").strip().lower()
            if route_action in {"create_task", "submit_task", "background_task"}:
                return True

        return self._looks_like_explicit_task_request(user_input)

    def _extract_steps_from_plan(self, plan: Any) -> list:
        if isinstance(plan, dict):
            if isinstance(plan.get("steps"), list):
                return copy.deepcopy(plan["steps"])

            nested_plan = plan.get("plan")
            if isinstance(nested_plan, dict) and isinstance(nested_plan.get("steps"), list):
                return copy.deepcopy(nested_plan["steps"])

            for key in ("actions", "tasks"):
                value = plan.get(key)
                if isinstance(value, list):
                    return copy.deepcopy(value)

        if isinstance(plan, list):
            return copy.deepcopy(plan)

        return []

    def _make_task_id(self) -> str:
        return f"task_{int(time.time() * 1000)}"

    # ============================================================
    # task shell
    # ============================================================

    def _build_task_shell(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        route: Any = None,
    ) -> Dict[str, Any]:
        task_id = self._make_task_id()
        task_name = task_id

        workspace_dir = "workspace/tasks"
        task_dir = f"{workspace_dir}/{task_name}"
        runtime_state_file = f"{task_dir}/runtime_state.json"
        plan_file = f"{task_dir}/plan.json"
        log_file = f"{task_dir}/task.log"

        task: Dict[str, Any] = {
            "id": task_id,
            "task_id": task_id,
            "task_name": task_name,
            "title": user_input,
            "goal": user_input,
            "status": "created",
            "priority": 0,
            "retry_count": 0,
            "max_retries": 0,
            "retry_delay": 0,
            "timeout_ticks": 0,
            "depends_on": [],
            "simulate": "",
            "required_ticks": 1,
            "progress_ticks": 0,
            "history": ["created"],
            "workspace_dir": workspace_dir,
            "task_dir": task_dir,
            "runtime_state_file": runtime_state_file,
            "plan_file": plan_file,
            "log_file": log_file,
            "max_replans": 1,
            "replanned": False,
            "replan_reason": "",
            "replan_count": 0,
            "current_step_index": 0,
            "steps_total": 0,
            "steps": [],
            "results": [],
            "step_results": [],
            "execution_log": [],
            "last_step_result": None,
            "last_error": None,
            "current_step": None,
            "final_result": None,
            "final_answer": "",
            "loop_cycle_count": 0,
            "loop_history": [],
            "last_observation": {},
            "last_decision": "",
            "last_decision_reason": "",
            "next_action": "",
            "terminal_reason": "",
        }

        if isinstance(route, dict):
            task["route"] = copy.deepcopy(route)

            if route.get("priority") is not None:
                try:
                    task["priority"] = int(route.get("priority", 0))
                except Exception:
                    pass

            if route.get("max_replans") is not None:
                try:
                    task["max_replans"] = int(route.get("max_replans", 1))
                except Exception:
                    pass

            if route.get("timeout_ticks") is not None:
                try:
                    task["timeout_ticks"] = int(route.get("timeout_ticks", 0))
                except Exception:
                    pass

            depends_on = route.get("depends_on")
            if isinstance(depends_on, list):
                task["depends_on"] = [str(x).strip() for x in depends_on if str(x).strip()]
            elif isinstance(depends_on, str) and depends_on.strip():
                task["depends_on"] = [depends_on.strip()]

        if isinstance(context, dict):
            task["context_snapshot"] = copy.deepcopy(context)

        return task

    # ============================================================
    # controlled scheduler helpers
    # ============================================================

    def _supports_scheduler_create_submit(self, task_entry: Any) -> bool:
        create_fn = getattr(task_entry, "create_task", None)
        submit_fn = getattr(task_entry, "submit_existing_task", None)
        return callable(create_fn) and callable(submit_fn)

    def _persist_task_to_entry(self, task_entry: Any, task: Dict[str, Any]) -> None:
        task_id = str(
            task.get("task_id")
            or task.get("id")
            or task.get("task_name")
            or ""
        ).strip()
        if not task_id:
            return

        persist_fn = getattr(task_entry, "_persist_task_payload", None)
        if callable(persist_fn):
            try:
                persist_fn(task_id=task_id, task=copy.deepcopy(task))
                return
            except Exception:
                pass

        repo = getattr(task_entry, "task_repo", None)
        if repo is not None:
            replace_fn = getattr(repo, "replace_task", None)
            upsert_fn = getattr(repo, "upsert_task", None)
            create_fn = getattr(repo, "create_task", None)
            add_fn = getattr(repo, "add_task", None)

            try:
                if callable(replace_fn):
                    replace_fn(task_id, copy.deepcopy(task))
                    return
                if callable(upsert_fn):
                    upsert_fn(copy.deepcopy(task))
                    return
                if callable(create_fn):
                    create_fn(copy.deepcopy(task))
                    return
                if callable(add_fn):
                    add_fn(copy.deepcopy(task))
                    return
            except Exception:
                pass

    def _get_task_from_entry(self, task_entry: Any, task_id: str) -> Optional[Dict[str, Any]]:
        if not task_id:
            return None

        get_fn = getattr(task_entry, "_get_task_from_repo", None)
        if callable(get_fn):
            try:
                value = get_fn(task_id)
                if isinstance(value, dict):
                    return copy.deepcopy(value)
            except Exception:
                pass

        repo = getattr(task_entry, "task_repo", None)
        if repo is not None:
            for method_name in ("get_task", "get", "load_task", "find_task"):
                fn = getattr(repo, method_name, None)
                if callable(fn):
                    try:
                        value = fn(task_id)
                        if isinstance(value, dict):
                            return copy.deepcopy(value)
                    except Exception:
                        pass

        return None

    def _save_task_plan_and_runtime(self, task: Dict[str, Any], plan: Any) -> None:
        workspace = self.task_workspace
        runtime = self.task_runtime

        if workspace is None:
            workspace = getattr(self.scheduler, "task_workspace", None)

        if runtime is None:
            runtime = getattr(self.scheduler, "task_runtime", None)

        if workspace is not None:
            try:
                workspace.save_plan(task, plan if isinstance(plan, dict) else {})
            except Exception:
                pass
            try:
                workspace.save_task_snapshot(task)
            except Exception:
                pass

        if runtime is not None:
            try:
                runtime.ensure_runtime_state(task)
            except Exception:
                pass

    def _enqueue_task(self, task_entry: Any, task: Dict[str, Any]) -> Any:
        for method_name in ("add_task", "enqueue", "submit_task", "create_task"):
            fn = getattr(task_entry, method_name, None)
            if callable(fn):
                return fn(task)
        raise RuntimeError("scheduler/task_manager has no add_task / enqueue / submit_task / create_task")

    def _route_int(self, route: Any, key: str, default: int) -> int:
        if isinstance(route, dict) and route.get(key) is not None:
            try:
                return int(route.get(key))
            except Exception:
                return default
        return default

    def _route_depends_on(self, route: Any) -> Optional[list]:
        if not isinstance(route, dict):
            return None

        value = route.get("depends_on")
        if value is None:
            return None

        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]

        if isinstance(value, str) and value.strip():
            return [value.strip()]

        return None

    # ============================================================
    # router
    # ============================================================

    def _call_router(self, context: Dict[str, Any], user_input: str) -> Any:
        if not self.router:
            return None

        router_fn = self._pick_callable(self.router, ["route", "run", "handle", "__call__"])
        if router_fn is None:
            return None

        candidate_calls = [
            {"context": context, "user_input": user_input},
            {"context": context},
            {"user_input": user_input},
        ]

        for kwargs in candidate_calls:
            try:
                return router_fn(**kwargs)
            except TypeError:
                continue
            except Exception as e:
                return {"router_error": str(e)}

        try:
            return router_fn(context)
        except Exception as e:
            return {"router_error": str(e)}

    # ============================================================
    # planner
    # ============================================================

    def _call_planner(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        if not self.planner:
            return None

        planner_fn = self._pick_callable(
            self.planner,
            [
                "plan",
                "run",
                "create_plan",
                "build_plan",
                "build",
                "make_plan",
                "generate_plan",
                "generate",
                "handle",
                "__call__",
            ],
        )

        if planner_fn is None:
            return {
                "ok": False,
                "_planner_error": True,
                "error": "planner has no callable method",
            }

        candidate_calls = [
            {"context": context, "user_input": user_input, "route": route},
            {"context": context, "user_input": user_input},
            {"context": context},
            {"user_input": user_input, "route": route},
            {"user_input": user_input},
            {"input_text": user_input},
            {"message": user_input},
            {"prompt": user_input},
            {"task": context},
            {"payload": context},
        ]

        for kwargs in candidate_calls:
            try:
                return planner_fn(**kwargs)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "ok": False,
                    "_planner_error": True,
                    "error": f"planner 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        positional_calls = [
            context,
            user_input,
            {"context": context, "user_input": user_input, "route": route},
        ]

        for arg in positional_calls:
            try:
                return planner_fn(arg)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "ok": False,
                    "_planner_error": True,
                    "error": f"planner 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        return {
            "ok": False,
            "_planner_error": True,
            "error": "planner 存在，但沒有找到相容的呼叫方式",
        }

    def _call_llm_planner(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        if not self.llm_planner:
            return None

        planner_fn = self._pick_callable(
            self.llm_planner,
            [
                "plan",
                "run",
                "create_plan",
                "build_plan",
                "build",
                "make_plan",
                "generate_plan",
                "generate",
                "handle",
                "__call__",
            ],
        )

        if planner_fn is None:
            return {
                "ok": False,
                "_planner_error": True,
                "error": "llm_planner has no callable method",
            }

        candidate_calls = [
            {"context": context, "user_input": user_input, "route": route},
            {"context": context, "user_input": user_input},
            {"context": context},
            {"user_input": user_input, "route": route},
            {"user_input": user_input},
            {"input_text": user_input},
            {"message": user_input},
            {"prompt": user_input},
            {"task": context},
            {"payload": context},
        ]

        for kwargs in candidate_calls:
            try:
                return planner_fn(**kwargs)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "ok": False,
                    "_planner_error": True,
                    "error": f"llm_planner 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        positional_calls = [
            context,
            user_input,
            {"context": context, "user_input": user_input, "route": route},
        ]

        for arg in positional_calls:
            try:
                return planner_fn(arg)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "ok": False,
                    "_planner_error": True,
                    "error": f"llm_planner 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        return {
            "ok": False,
            "_planner_error": True,
            "error": "llm_planner 存在，但沒有找到相容的呼叫方式",
        }

    # ============================================================
    # step executor
    # ============================================================

    def _call_step_executor(
        self,
        step: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        previous_result: Any = None,
        step_index: Optional[int] = None,
        step_count: Optional[int] = None,
    ) -> Any:
        if not self.step_executor:
            return None

        executor_fn = self._pick_callable(
            self.step_executor,
            [
                "execute",
                "run",
                "execute_step",
                "run_step",
                "execute_one_step",
                "handle",
                "__call__",
            ],
        )

        if executor_fn is None:
            return {"error": "step_executor has no callable method"}

        candidate_calls = [
            {
                "step": step,
                "context": context,
                "user_input": user_input,
                "route": route,
                "previous_result": previous_result,
                "step_index": step_index,
                "step_count": step_count,
            },
            {
                "step": step,
                "context": context,
                "previous_result": previous_result,
                "step_index": step_index,
                "step_count": step_count,
            },
            {
                "step": step,
                "context": context,
            },
            {
                "step": step,
            },
            {
                "payload": step,
            },
        ]

        for kwargs in candidate_calls:
            try:
                return executor_fn(**kwargs)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "error": f"step_executor 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        for arg in (step, context):
            try:
                return executor_fn(arg)
            except TypeError:
                continue
            except Exception as e:
                return {
                    "error": f"step_executor 呼叫失敗: {e}",
                    "traceback": traceback.format_exc(),
                }

        return {"error": "step_executor 存在，但沒有找到相容的呼叫方式"}

    # ============================================================
    # verifier / safety
    # ============================================================

    def _run_verifier(self, execution_result: Any) -> Any:
        if not self.verifier:
            return execution_result

        try:
            verify_fn = self._pick_callable(self.verifier, ["verify", "check", "review", "run"])
            if verify_fn is None:
                return execution_result

            try:
                return verify_fn(result=execution_result)
            except TypeError:
                try:
                    return verify_fn(payload=execution_result)
                except TypeError:
                    return verify_fn(execution_result)
        except Exception:
            return execution_result

    def _run_safety_guard(self, execution_result: Any) -> Any:
        if not self.safety_guard:
            return execution_result

        try:
            guard_fn = self._pick_callable(self.safety_guard, ["check", "review", "evaluate", "run"])
            if guard_fn is None:
                return execution_result

            try:
                return guard_fn(result=execution_result)
            except TypeError:
                try:
                    return guard_fn(payload=execution_result)
                except TypeError:
                    return guard_fn(execution_result)
        except Exception:
            return execution_result

    # ============================================================
    # result formatting
    # ============================================================

    def _summarize_step_result(self, result: Any, failed: bool = False) -> str:
        if not isinstance(result, dict):
            return str(result) if result is not None else ("執行失敗" if failed else "執行完成")

        if failed:
            error = result.get("error")
            if isinstance(error, str) and error.strip():
                return f"執行失敗：{error.strip()}"

        step = result.get("step")
        step_type = ""
        if isinstance(step, dict):
            step_type = str(step.get("type", "") or "").strip().lower()

        payload = result.get("result")
        if not isinstance(payload, dict):
            payload = {}

        if step_type == "write_file":
            path = payload.get("path")
            if isinstance(path, str) and path.strip():
                return f"已寫入檔案：{path.strip()}"
            return "已寫入檔案"

        if step_type == "read_file":
            path = payload.get("path")
            content = payload.get("content")
            if isinstance(path, str) and isinstance(content, str):
                return f"已讀取檔案：{path}\n\n{content}"
            if isinstance(path, str):
                return f"已讀取檔案：{path}"
            return "已讀取檔案"

        if step_type in {"llm", "llm_generate"}:
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

            response = payload.get("response")
            if isinstance(response, str) and response.strip():
                return response.strip()

            return "LLM 已完成回應"

        if step_type in {"respond", "final_answer"}:
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

        if step_type == "command":
            stdout = payload.get("stdout")
            stderr = payload.get("stderr")
            returncode = payload.get("returncode")

            if isinstance(stdout, str) and stdout.strip():
                return stdout.strip()

            if isinstance(stderr, str) and stderr.strip():
                return f"命令執行失敗：{stderr.strip()}"

            if returncode == 0:
                return "命令執行完成"

        if step_type == "verify":
            if payload.get("verified") is True:
                checked = str(payload.get("checked_text") or "").strip()
                if checked:
                    return f"verify ok\n內容：{checked}"
                return "verify ok"

        for key in ("message", "content", "text", "answer", "response", "final_answer"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        error = result.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()

        return "執行完成" if not failed else "執行失敗"

    # ============================================================
    # utils
    # ============================================================

    def _pick_callable(self, obj: Any, names: list[str]):
        for name in names:
            fn = getattr(obj, name, None)
            if callable(fn):
                return fn
        return None

    def _extract_final_answer(self, execution: Any, plan: Any, fallback: str) -> str:
        if isinstance(execution, dict):
            value = execution.get("final_answer")
            if isinstance(value, str) and value.strip():
                return value.strip()

            last_result = execution.get("last_result")
            if isinstance(last_result, dict):
                summary = self._summarize_step_result(last_result, failed=bool(last_result.get("ok") is False))
                if isinstance(summary, str) and summary.strip():
                    return summary.strip()

        if isinstance(plan, dict):
            for key in ("answer", "response", "message", "summary", "final_answer"):
                value = plan.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()

        return "執行完成"

    def _normalize_task_input(self, task: Any) -> Dict[str, Any]:
        if task is None:
            raise ValueError("task is None")

        to_dict = getattr(task, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return copy.deepcopy(result)

        if hasattr(task, "__dict__"):
            raw = dict(vars(task))
            if isinstance(raw, dict):
                return copy.deepcopy(raw)

        if isinstance(task, dict):
            return copy.deepcopy(task)

        raise TypeError("task must be dict-like or object with to_dict()")

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)