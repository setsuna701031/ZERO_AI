from __future__ import annotations

import copy
import time
from typing import Any, Dict, Optional, List

from core.agent.agent_component_invoker import (
    call_llm_planner,
    call_planner,
    call_router,
    call_step_executor,
    run_safety_guard,
    run_verifier,
)
from core.agent.agent_route_policy import (
    looks_like_action_items_document_flow,
    looks_like_explicit_task_request,
    looks_like_summary_document_flow,
    should_enter_task_mode,
    should_force_planner_document_flow,
)
from core.agent.document_flow_trace_writer import maybe_write_document_flow_trace
from core.memory.context_builder import build_context
from core.runtime.task_runner import TaskRunner


class AgentLoop:
    """
    ZERO Agent Loop v3 - interface contract stabilization

    本版重點：
    1. 保留 direct / task / llm / single-shot 主幹
    2. 保留 document flow 強制走 planner + task mode
    3. 保留 task mode scheduler.create_task + submit_existing_task 流程
    4. 不重寫既有主線行為，只補 interface contract 收束
    5. planner result / execution result / final response 皆做正規化
    6. 減少 agent_loop 對 planner 回傳細節飄移的依賴
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
        text = str(user_input or "").strip()
        if not text:
            return self._make_agent_response(
                ok=False,
                mode="empty",
                context={},
                route=None,
                plan=None,
                execution=None,
                final_answer="",
                error="user_input is empty",
            )

        context = self._build_context(text)
        route = self._call_router(context, text)

        if self.debug:
            print("[AgentLoop] user_input =", text)
            print("[AgentLoop] route =", route)

        if self._should_force_planner_document_flow(text):
            forced_route: Dict[str, Any] = {}
            if isinstance(route, dict):
                forced_route.update(copy.deepcopy(route))
            forced_route["mode"] = "task"
            forced_route["task"] = True
            forced_route["forced_document_flow"] = True
            route = forced_route

            if self.debug:
                print("[AgentLoop] forced document flow route =", route)

        direct_result = self._try_handle_direct_route(
            context=context,
            user_input=text,
            route=route,
        )
        if direct_result is not None:
            return self._normalize_agent_response(direct_result)

        llm_result = self._try_handle_llm_route(
            context=context,
            user_input=text,
            route=route,
        )
        if llm_result is not None:
            return self._normalize_agent_response(llm_result)

        if self._should_enter_task_mode(route, text):
            return self._normalize_agent_response(
                self._run_task_mode(
                    context=context,
                    user_input=text,
                    route=route,
                )
            )

        return self._normalize_agent_response(
            self._run_single_shot_mode(
                context=context,
                user_input=text,
                route=route,
            )
        )


    def run_task_loop(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            effective_task = self._normalize_task_input(task)
        except Exception as e:
            return {
                "ok": False,
                "mode": "task_loop",
                "action": "invalid_task_input",
                "status": "failed",
                "final_answer": "",
                "error": f"invalid task input: {e}",
                "task": copy.deepcopy(task) if isinstance(task, dict) else {"raw_task": task},
                "execution": None,
            }

        self._ensure_loop_state_defaults(effective_task)
        effective_task.setdefault("results", [])
        effective_task.setdefault("step_results", [])
        effective_task.setdefault("execution_log", [])
        effective_task.setdefault("execution_trace", [])
        effective_task.setdefault("last_step_result", None)
        effective_task.setdefault("last_error", None)
        effective_task.setdefault("final_answer", "")

        if isinstance(original_plan, dict):
            effective_task["planner_result"] = copy.deepcopy(original_plan)
            if not isinstance(effective_task.get("steps"), list) or not effective_task.get("steps"):
                effective_task["steps"] = self._extract_steps_from_plan(original_plan)
                effective_task["steps_total"] = len(effective_task["steps"])

        runner = self.task_runner
        if runner is None:
            return {
                "ok": False,
                "mode": "task_loop",
                "action": "task_runner_missing",
                "status": "failed",
                "final_answer": "",
                "error": "task_runner missing",
                "task": copy.deepcopy(effective_task),
                "execution": None,
            }

        runner_result = runner.run_task(
            task=effective_task,
            current_tick=current_tick,
            user_input=user_input,
            original_plan=original_plan,
        )
        if not isinstance(runner_result, dict):
            return {
                "ok": False,
                "mode": "task_loop",
                "action": "invalid_runner_result",
                "status": "failed",
                "final_answer": "",
                "error": "task_runner returned non-dict result",
                "task": copy.deepcopy(effective_task),
                "raw_result": copy.deepcopy(runner_result),
                "execution": None,
            }

        self._sync_task_from_runner_result(effective_task, runner_result)
        self._ensure_loop_state_defaults(effective_task)

        runtime_state = runner_result.get("runtime_state")
        if isinstance(runtime_state, dict):
            self._overlay_loop_state(effective_task, runtime_state)

        execution = self._build_task_loop_execution(
            runner_result=runner_result,
            effective_task=effective_task,
        )
        normalized_execution = self._normalize_execution_result(execution)

        final_answer = self._extract_loop_final_answer(
            runner_result=runner_result,
            effective_task=effective_task,
            fallback=user_input,
        )

        return {
            "ok": bool(runner_result.get("ok", True)),
            "mode": "task_loop",
            "action": str(runner_result.get("action") or "task_loop_tick"),
            "status": str(effective_task.get("status") or runner_result.get("status") or "running"),
            "final_answer": final_answer,
            "error": runner_result.get("error"),
            "task": copy.deepcopy(effective_task),
            "runtime_state": copy.deepcopy(runner_result.get("runtime_state")) if isinstance(runner_result.get("runtime_state"), dict) else None,
            "execution": normalized_execution,
            "last_result": copy.deepcopy(runner_result.get("last_result")) if isinstance(runner_result.get("last_result"), dict) else None,
        }

    def run_task(
        self,
        task: Dict[str, Any],
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

    def _build_task_loop_execution(
        self,
        *,
        runner_result: Dict[str, Any],
        effective_task: Dict[str, Any],
    ) -> Dict[str, Any]:
        results = effective_task.get("results")
        if not isinstance(results, list):
            results = []

        execution_trace = self._extract_execution_trace_from_runner_result(
            runner_result=runner_result,
            task=effective_task,
        )

        steps_executed = 0
        if isinstance(results, list):
            steps_executed = len(results)
        if steps_executed <= 0:
            steps_executed = self._safe_int(runner_result.get("current_step_index"), 0)
        if steps_executed <= 0:
            steps_executed = self._safe_int(effective_task.get("current_step_index"), 0)

        execution: Dict[str, Any] = {
            "ok": bool(runner_result.get("ok", True)),
            "steps_executed": steps_executed,
            "results": copy.deepcopy(results),
            "execution_trace": execution_trace,
            "last_result": copy.deepcopy(runner_result.get("last_result")) if isinstance(runner_result.get("last_result"), dict) else copy.deepcopy(effective_task.get("last_step_result")),
            "final_answer": str(runner_result.get("final_answer") or effective_task.get("final_answer") or ""),
            "error": runner_result.get("error"),
        }
        return execution

    def _extract_execution_trace_from_runner_result(
        self,
        *,
        runner_result: Dict[str, Any],
        task: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        trace = runner_result.get("execution_trace")
        if isinstance(trace, list):
            return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]

        runtime_state = runner_result.get("runtime_state")
        if isinstance(runtime_state, dict):
            trace = runtime_state.get("execution_trace")
            if isinstance(trace, list):
                return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]

        trace = task.get("execution_trace")
        if isinstance(trace, list):
            return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]

        last_result = runner_result.get("last_result")
        if isinstance(last_result, dict):
            step = last_result.get("step") if isinstance(last_result.get("step"), dict) else None
            step_index = self._safe_int(last_result.get("step_index"), self._safe_int(task.get("current_step_index"), 0) or 1)
            return [self._make_execution_trace_event(step_index=step_index, step=step, step_result=last_result)]

        return []

    def _sync_task_from_runner_result(
        self,
        task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> None:
        if not isinstance(task, dict) or not isinstance(runner_result, dict):
            return

        runtime_state = runner_result.get("runtime_state")
        if isinstance(runtime_state, dict):
            for key in (
                "status",
                "current_step_index",
                "steps_total",
                "steps",
                "results",
                "step_results",
                "execution_log",
                "execution_trace",
                "last_step_result",
                "last_error",
                "final_answer",
                "final_result",
                "failure_type",
                "failure_message",
                "failure_decision",
            ):
                if key in runtime_state:
                    task[key] = copy.deepcopy(runtime_state.get(key))
            task["runtime_state"] = copy.deepcopy(runtime_state)

        for key in (
            "status",
            "current_step_index",
            "steps_total",
            "results",
            "step_results",
            "execution_log",
            "execution_trace",
            "last_step_result",
            "last_error",
            "final_answer",
            "final_result",
        ):
            if key in runner_result:
                task[key] = copy.deepcopy(runner_result.get(key))


    def _ensure_loop_state_defaults(self, task_dict: Dict[str, Any]) -> Dict[str, Any]:
        task_dict.setdefault("loop_cycle_count", 0)
        task_dict.setdefault("loop_history", [])
        task_dict.setdefault("last_observation", {})
        task_dict.setdefault("last_decision", "")
        task_dict.setdefault("last_decision_reason", "")
        task_dict.setdefault("next_action", "")
        task_dict.setdefault("terminal_reason", "")
        return task_dict

    def _overlay_loop_state(
        self,
        target: Dict[str, Any],
        source: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(target, dict) or not isinstance(source, dict):
            return target

        for key in (
            "last_observation",
            "last_decision",
            "last_decision_reason",
            "next_action",
            "terminal_reason",
            "loop_cycle_count",
            "loop_history",
        ):
            if key in source:
                target[key] = copy.deepcopy(source.get(key))
        return target

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
    # contract normalization
    # ============================================================

    def _make_agent_response(
        self,
        *,
        ok: bool,
        mode: str,
        context: Optional[Dict[str, Any]],
        route: Any,
        plan: Any,
        execution: Any,
        final_answer: str,
        error: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": bool(ok),
            "mode": str(mode or "unknown"),
            "context": context if isinstance(context, dict) else {},
            "route": copy.deepcopy(route),
            "plan": self._normalize_plan_result(plan),
            "execution": self._normalize_execution_result(execution),
            "final_answer": str(final_answer or ""),
            "error": error,
        }

        if isinstance(extra, dict):
            for key, value in extra.items():
                if key in result:
                    continue
                result[key] = value

        return result

    def _normalize_agent_response(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return self._make_agent_response(
                ok=False,
                mode="invalid_response",
                context={},
                route=None,
                plan=None,
                execution=None,
                final_answer="",
                error="agent_loop returned invalid response",
                extra={"raw_result": copy.deepcopy(result)},
            )

        normalized = dict(result)
        normalized["ok"] = bool(normalized.get("ok", True))
        normalized["mode"] = str(normalized.get("mode") or "unknown")
        normalized["context"] = normalized.get("context") if isinstance(normalized.get("context"), dict) else {}
        normalized["route"] = copy.deepcopy(normalized.get("route"))
        normalized["plan"] = self._normalize_plan_result(normalized.get("plan"))
        normalized["execution"] = self._normalize_execution_result(normalized.get("execution"))
        normalized["final_answer"] = str(normalized.get("final_answer") or "")
        normalized["error"] = normalized.get("error")
        return normalized

    def _normalize_plan_result(self, plan: Any) -> Optional[Dict[str, Any]]:
        if plan is None:
            return None

        if not isinstance(plan, dict):
            return {
                "ok": False,
                "planner_mode": "invalid_plan",
                "intent": "respond",
                "final_answer": "",
                "steps": [],
                "error": "planner returned non-dict result",
                "meta": {
                    "fallback_used": False,
                    "step_count": 0,
                },
                "raw_plan": copy.deepcopy(plan),
            }

        steps = self._normalize_steps(self._extract_steps_from_plan(plan))

        normalized = dict(plan)
        normalized["ok"] = bool(normalized.get("ok", True))
        normalized["planner_mode"] = str(normalized.get("planner_mode") or "unknown")
        normalized["intent"] = str(normalized.get("intent") or "respond")
        normalized["final_answer"] = str(normalized.get("final_answer") or "")
        normalized["steps"] = steps
        normalized["error"] = normalized.get("error")

        meta = normalized.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        meta["fallback_used"] = bool(meta.get("fallback_used", False))
        meta["step_count"] = len(steps)
        normalized["meta"] = meta

        return normalized

    def _normalize_execution_result(self, execution: Any) -> Optional[Dict[str, Any]]:
        if execution is None:
            return None

        if not isinstance(execution, dict):
            return {
                "ok": False,
                "steps_executed": 0,
                "results": [],
                "last_result": None,
                "final_answer": "",
                "error": "execution returned non-dict result",
                "raw_execution": copy.deepcopy(execution),
            }

        normalized = dict(execution)
        normalized["ok"] = bool(normalized.get("ok", True))
        normalized["steps_executed"] = self._safe_int(normalized.get("steps_executed", 0), 0)

        results = normalized.get("results")
        if not isinstance(results, list):
            results = []
        normalized["results"] = self._normalize_execution_items(results)

        last_result = normalized.get("last_result")
        if isinstance(last_result, dict):
            normalized["last_result"] = copy.deepcopy(last_result)
        elif normalized["results"]:
            last_item = normalized["results"][-1]
            if isinstance(last_item, dict) and isinstance(last_item.get("result"), dict):
                normalized["last_result"] = copy.deepcopy(last_item.get("result"))
            else:
                normalized["last_result"] = None
        else:
            normalized["last_result"] = None

        execution_trace = normalized.get("execution_trace")
        if isinstance(execution_trace, list):
            normalized["execution_trace"] = [copy.deepcopy(item) for item in execution_trace if isinstance(item, dict)]
        else:
            normalized["execution_trace"] = []

        normalized["final_answer"] = str(normalized.get("final_answer") or "")
        if "error" in normalized:
            normalized["error"] = normalized.get("error")
        else:
            normalized["error"] = None

        return normalized

    def _normalize_execution_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []

        for idx, item in enumerate(items, start=1):
            if isinstance(item, dict):
                step = item.get("step")
                result = item.get("result")
                step_index = self._safe_int(item.get("step_index", idx), idx)

                normalized.append(
                    {
                        "step_index": step_index,
                        "step": self._normalize_step(step, step_index),
                        "result": copy.deepcopy(result) if isinstance(result, dict) else {"ok": False, "raw_result": result},
                    }
                )
                continue

            normalized.append(
                {
                    "step_index": idx,
                    "step": self._normalize_step(None, idx),
                    "result": {"ok": False, "raw_result": item},
                }
            )

        return normalized

    def _normalize_steps(self, steps: Any) -> List[Dict[str, Any]]:
        if not isinstance(steps, list):
            return []

        task_name = self._make_task_id()
        return [self._normalize_step(step, idx, task_name=task_name) for idx, step in enumerate(steps, start=1)]

    def _normalize_step(
        self,
        step: Any,
        index: int,
        task_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if isinstance(step, dict):
            normalized = dict(step)
        else:
            normalized = {"type": "unknown", "value": step}

        resolved_task_name = str(normalized.get("task_name") or task_name or "task_unknown").strip() or "task_unknown"
        resolved_step_type = str(normalized.get("type") or "unknown").strip() or "unknown"
        resolved_step_id = str(normalized.get("id") or f"{resolved_task_name}_step_{index}").strip() or f"{resolved_task_name}_step_{index}"

        normalized["type"] = resolved_step_type
        normalized["task_name"] = resolved_task_name
        normalized["id"] = resolved_step_id

        if resolved_step_type in {"read_file", "write_file", "ensure_file", "run_python", "verify", "verify_file"}:
            normalized["path"] = str(normalized.get("path") or "")

        if resolved_step_type == "command":
            normalized["command"] = str(normalized.get("command") or "")

        if resolved_step_type == "web_search":
            normalized["query"] = str(normalized.get("query") or "")

        if resolved_step_type == "llm":
            normalized["prompt"] = str(normalized.get("prompt") or "")
            if "mode" in normalized and normalized["mode"] is not None:
                normalized["mode"] = str(normalized.get("mode") or "")

        if resolved_step_type == "write_file":
            normalized["content"] = str(normalized.get("content") or "")

        if "scope" in normalized and normalized["scope"] is not None:
            normalized["scope"] = str(normalized.get("scope") or "")

        return normalized

    # ============================================================
    # special routing guard
    # ============================================================

    def _should_force_planner_document_flow(self, user_input: str) -> bool:
        return should_force_planner_document_flow(user_input)

    def _looks_like_summary_document_flow(self, text: str) -> bool:
        return looks_like_summary_document_flow(text)

    def _looks_like_action_items_document_flow(self, text: str) -> bool:
        return looks_like_action_items_document_flow(text)

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
            return self._make_agent_response(
                ok=False,
                mode="direct",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer="",
                error="router returned direct mode but step missing",
            )

        execution_result = self._execute_direct_step(
            step=step,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)

        normalized_execution = self._normalize_execution_result(execution_result)

        return self._make_agent_response(
            ok=bool(normalized_execution.get("ok", True)) if isinstance(normalized_execution, dict) else True,
            mode="direct",
            context=context,
            route=route,
            plan=None,
            execution=normalized_execution,
            final_answer=self._extract_final_answer(normalized_execution, None, user_input),
        )

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
            return self._make_agent_response(
                ok=True,
                mode="llm",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer="目前聊天模式尚未啟用。",
            )

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
        llm_plan = self._normalize_plan_result(llm_plan)

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
            return self._make_agent_response(
                ok=True,
                mode="llm",
                context=context,
                route=route,
                plan=llm_plan,
                execution=None,
                final_answer=self._extract_final_answer(None, llm_plan, user_input),
            )

        execution_result = self._execute_single_shot_steps(
            steps=steps,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)
        normalized_execution = self._normalize_execution_result(execution_result)

        return self._make_agent_response(
            ok=bool(normalized_execution.get("ok", True)) if isinstance(normalized_execution, dict) else True,
            mode="llm",
            context=context,
            route=route,
            plan=llm_plan,
            execution=normalized_execution,
            final_answer=self._extract_final_answer(normalized_execution, llm_plan, user_input),
        )

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

        normalized_step = self._normalize_step(step, 1)

        step_result = self._call_step_executor(
            step=normalized_step,
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
                "step": copy.deepcopy(normalized_step),
            }

        execution_trace = [
            self._make_execution_trace_event(
                step_index=1,
                step=normalized_step,
                step_result=step_result,
            )
        ]

        return {
            "ok": bool(step_result.get("ok", True)),
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": copy.deepcopy(normalized_step),
                    "result": copy.deepcopy(step_result),
                }
            ],
            "execution_trace": execution_trace,
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
        raw_plan = self._call_planner(
            context=context,
            user_input=user_input,
            route=route,
        )
        plan = self._normalize_plan_result(raw_plan)

        if isinstance(plan, dict) and plan.get("ok") is False and raw_plan is not None and isinstance(raw_plan, dict) and raw_plan.get("_planner_error"):
            return self._make_agent_response(
                ok=False,
                mode="single_shot",
                context=context,
                route=route,
                plan=plan,
                execution=None,
                final_answer="",
                error=plan.get("error", "planner call failed"),
                extra={"traceback": raw_plan.get("traceback")},
            )

        if plan is None:
            return self._make_agent_response(
                ok=True,
                mode="single_shot",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer=user_input,
            )

        steps = self._extract_steps_from_plan(plan)

        if self.debug:
            print("[AgentLoop] single-shot steps =", steps)

        if not steps:
            return self._make_agent_response(
                ok=True,
                mode="single_shot",
                context=context,
                route=route,
                plan=plan,
                execution=None,
                final_answer=self._extract_final_answer(None, plan, user_input),
            )

        execution_result = self._execute_single_shot_steps(
            steps=steps,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)
        normalized_execution = self._normalize_execution_result(execution_result)

        try:
            self._maybe_write_document_flow_trace(
                steps=steps,
                execution_result=normalized_execution or {},
            )
        except Exception as e:
            if self.debug:
                print(f"[AgentLoop] document flow trace write failed: {e}")

        return self._make_agent_response(
            ok=bool(normalized_execution.get("ok", True)) if isinstance(normalized_execution, dict) else True,
            mode="single_shot",
            context=context,
            route=route,
            plan=plan,
            execution=normalized_execution,
            final_answer=self._extract_final_answer(normalized_execution, plan, user_input),
        )

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

        normalized_steps = self._normalize_steps(steps)

        results: List[Dict[str, Any]] = []
        execution_trace: List[Dict[str, Any]] = []
        previous_result: Any = None
        last_result: Dict[str, Any] = {}

        for index, step in enumerate(normalized_steps, start=1):
            step_result = self._call_step_executor(
                step=step,
                context=context,
                user_input=user_input,
                route=route,
                previous_result=previous_result,
                step_index=index,
                step_count=len(normalized_steps),
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
            execution_trace.append(
                self._make_execution_trace_event(
                    step_index=index,
                    step=step,
                    step_result=step_result,
                )
            )

            last_result = step_result
            previous_result = step_result

            if step_result.get("ok") is False:
                return {
                    "ok": False,
                    "steps_executed": index,
                    "results": results,
                    "execution_trace": execution_trace,
                    "last_result": last_result,
                    "final_answer": self._summarize_step_result(last_result, failed=True),
                    "error": step_result.get("error"),
                }

        return {
            "ok": True,
            "steps_executed": len(normalized_steps),
            "results": results,
            "execution_trace": execution_trace,
            "last_result": last_result,
            "final_answer": self._summarize_step_result(last_result, failed=False),
            "error": None,
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
        maybe_write_document_flow_trace(
            steps=steps,
            execution_result=execution_result,
            llm_client=self.llm_client,
            step_executor=self.step_executor,
            debug=self.debug,
        )

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
            return self._make_agent_response(
                ok=False,
                mode="task",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer="",
                error="scheduler/task_manager missing",
            )

        if self.planner is None:
            return self._make_agent_response(
                ok=False,
                mode="task",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer="",
                error="planner missing",
            )

        try:
            raw_plan = self._call_planner(
                context=context,
                user_input=user_input,
                route=route,
            )
            plan = self._normalize_plan_result(raw_plan)

            if isinstance(plan, dict) and plan.get("ok") is False and raw_plan is not None and isinstance(raw_plan, dict) and raw_plan.get("_planner_error"):
                return self._make_agent_response(
                    ok=False,
                    mode="task",
                    context=context,
                    route=route,
                    plan=plan,
                    execution=None,
                    final_answer="",
                    error=plan.get("error", "planner call failed"),
                    extra={"traceback": raw_plan.get("traceback")},
                )

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
            return self._make_agent_response(
                ok=False,
                mode="task",
                context=context,
                route=route,
                plan=None,
                execution=None,
                final_answer="",
                error=f"task mode failed: {e}",
                extra={"traceback": __import__("traceback").format_exc()},
            )

    def _run_task_mode_via_scheduler(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        normalized_plan = self._normalize_plan_result(plan)

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
            return self._make_agent_response(
                ok=False,
                mode="task",
                context=context,
                route=route,
                plan=normalized_plan,
                execution=None,
                final_answer="",
                error=(
                    create_result.get("error", "scheduler.create_task failed")
                    if isinstance(create_result, dict)
                    else "scheduler.create_task failed"
                ),
                extra={"create_result": create_result},
            )

        created_task = create_result.get("task")
        if not isinstance(created_task, dict):
            task_id = str(create_result.get("task_name") or "").strip()
            created_task = self._get_task_from_entry(task_entry, task_id)
        else:
            created_task = self._normalize_task_input(created_task)

        if not isinstance(created_task, dict):
            return self._make_agent_response(
                ok=False,
                mode="task",
                context=context,
                route=route,
                plan=normalized_plan,
                execution=None,
                final_answer="",
                error="created task missing or invalid",
                extra={"create_result": create_result},
            )

        created_task["planner_result"] = normalized_plan if isinstance(normalized_plan, dict) else {}
        created_task["steps"] = self._extract_steps_from_plan(normalized_plan)
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
        created_task.setdefault("execution_trace", [])
        created_task.setdefault("last_step_result", None)
        created_task.setdefault("last_error", None)
        created_task.setdefault("current_step_index", 0)
        created_task.setdefault("replanned", False)
        created_task.setdefault("replan_reason", "")
        created_task.setdefault("replan_count", 0)
        self._ensure_loop_state_defaults(created_task)

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

        return self._make_agent_response(
            ok=True,
            mode="task",
            context=context,
            route=route,
            plan=refreshed_task.get("planner_result"),
            execution=None,
            final_answer=f"已建立任務：{refreshed_task.get('title') or refreshed_task.get('goal')}",
            extra={
                "task": refreshed_task,
                "task_id": task_id,
                "task_dir": refreshed_task.get("task_dir"),
                "create_result": create_result,
                "submit_result": submit_result,
            },
        )

    def _run_task_mode_legacy_enqueue(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        normalized_plan = self._normalize_plan_result(plan)

        task = self._build_task_shell(
            user_input=user_input,
            context=context,
            route=route,
        )

        if self.task_workspace is not None:
            try:
                task = self.task_workspace.create_workspace(task)
            except Exception as e:
                return self._make_agent_response(
                    ok=False,
                    mode="task",
                    context=context,
                    route=route,
                    plan=normalized_plan,
                    execution=None,
                    final_answer="",
                    error=f"task_workspace.create_workspace failed: {e}",
                    extra={"traceback": __import__("traceback").format_exc()},
                )

        task["planner_result"] = normalized_plan if isinstance(normalized_plan, dict) else {}
        task["steps"] = self._extract_steps_from_plan(normalized_plan)
        task["steps_total"] = len(task["steps"])
        task["final_answer"] = ""
        self._ensure_loop_state_defaults(task)

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

        return self._make_agent_response(
            ok=True,
            mode="task",
            context=context,
            route=route,
            plan=task.get("planner_result"),
            execution=None,
            final_answer=f"已建立任務：{task.get('title') or task.get('goal')}",
            extra={
                "task": task,
                "task_id": task.get("task_id") or task.get("id") or task.get("task_name"),
                "task_dir": task.get("task_dir"),
                "enqueue_result": enqueue_result,
            },
        )

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
        return looks_like_explicit_task_request(text)

    def _should_enter_task_mode(self, route: Any, user_input: str) -> bool:
        return should_enter_task_mode(route, user_input)

    def _extract_steps_from_plan(self, plan: Any) -> list:
        if isinstance(plan, dict):
            if isinstance(plan.get("steps"), list):
                return self._normalize_steps(copy.deepcopy(plan["steps"]))

            nested_plan = plan.get("plan")
            if isinstance(nested_plan, dict) and isinstance(nested_plan.get("steps"), list):
                return self._normalize_steps(copy.deepcopy(nested_plan["steps"]))

            for key in ("actions", "tasks"):
                value = plan.get(key)
                if isinstance(value, list):
                    return self._normalize_steps(copy.deepcopy(value))

        if isinstance(plan, list):
            return self._normalize_steps(copy.deepcopy(plan))

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
            "execution_trace": [],
            "last_step_result": None,
            "last_error": None,
            "current_step": None,
            "final_result": None,
            "final_answer": "",
        }
        self._ensure_loop_state_defaults(task)

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
    # component invocation adapter
    # ============================================================

    def _call_router(self, context: Dict[str, Any], user_input: str) -> Any:
        return call_router(
            router=self.router,
            context=context,
            user_input=user_input,
        )

    def _call_planner(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        return call_planner(
            planner=self.planner,
            context=context,
            user_input=user_input,
            route=route,
        )

    def _call_llm_planner(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        return call_llm_planner(
            llm_planner=self.llm_planner,
            context=context,
            user_input=user_input,
            route=route,
        )

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
        return call_step_executor(
            step_executor=self.step_executor,
            step=step,
            context=context,
            user_input=user_input,
            route=route,
            previous_result=previous_result,
            step_index=step_index,
            step_count=step_count,
        )

    # ============================================================
    # verifier / safety
    # ============================================================

    def _run_verifier(self, execution_result: Any) -> Any:
        return run_verifier(
            verifier=self.verifier,
            execution_result=execution_result,
        )

    def _run_safety_guard(self, execution_result: Any) -> Any:
        return run_safety_guard(
            safety_guard=self.safety_guard,
            execution_result=execution_result,
        )

    # ============================================================
    # execution trace helpers
    # ============================================================

    def _make_execution_trace_event(
        self,
        *,
        step_index: int,
        step: Optional[Dict[str, Any]],
        step_result: Any,
    ) -> Dict[str, Any]:
        safe_step = copy.deepcopy(step) if isinstance(step, dict) else {}
        safe_result = copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result}

        error_payload = safe_result.get("error")
        if not isinstance(error_payload, dict):
            error_payload = {}

        error_details = error_payload.get("details")
        if not isinstance(error_details, dict):
            error_details = {}

        retry_payload = safe_result.get("retry")
        if not isinstance(retry_payload, dict):
            retry_payload = {}

        event: Dict[str, Any] = {
            "step_index": self._safe_int(step_index, 0),
            "step_type": str(
                safe_result.get("step_type")
                or safe_step.get("type")
                or ""
            ).strip().lower(),
            "ok": bool(safe_result.get("ok", False)),
            "message": str(safe_result.get("message") or ""),
            "final_answer": str(safe_result.get("final_answer") or ""),
            "error_type": str(error_payload.get("type") or ""),
            "classification": error_details.get("classification"),
            "attempts": self._safe_int(retry_payload.get("attempts", 1), 1),
            "max_attempts": self._safe_int(retry_payload.get("max_attempts", 1), 1),
            "retry_used": bool(retry_payload.get("used", False)),
        }

        if isinstance(safe_result.get("step"), dict):
            event["step_id"] = str(safe_result["step"].get("id") or "")
        elif isinstance(safe_step, dict):
            event["step_id"] = str(safe_step.get("id") or "")

        return event

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

        if step_type in {"verify", "verify_file"}:
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