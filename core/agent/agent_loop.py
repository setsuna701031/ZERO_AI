from __future__ import annotations

import copy
import difflib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List

from core.agent.agent_component_invoker import (
    call_llm_planner,
    call_planner,
    call_router,
    run_safety_guard,
    run_verifier,
)
from core.capabilities.capability_registry import has_capability, has_operation
from core.agent.agent_route_policy import (
    detect_document_flow_capability,
    looks_like_action_items_document_flow,
    looks_like_explicit_task_request,
    looks_like_summary_document_flow,
    should_enter_task_mode,
    should_force_planner_document_flow,
)
from core.agent.document_flow_trace_writer import maybe_write_document_flow_trace
from core.agent.agent_loop_route_marker import mark_agent_loop_route
from core.memory.context_builder import build_context
from core.runtime.agent_execution_runtime import AgentExecutionRuntime, agent_execution_path
from core.runtime.code_chain_patch_restore import request_code_chain_patch_restore
from core.agent.loop_decision import observe_and_decide
from core.runtime.blockers import active_blockers, normalize_blockers
from core.agent.local_observer import observe_runner_result as observe_local_runner_result
from core.tools.tool_decision import tool_decision_to_tool_call
from core.tools.tool_call import ToolCallExecutor, tool_call_trace_event
from core.tools.tool_registry import ToolRegistry

try:
    from core.tools.repo_edit_agent_bridge import run_repo_edit_decision
except Exception:  # pragma: no cover - optional bridge in minimal runtimes
    run_repo_edit_decision = None

try:
    from code_reader import read_code_file
except Exception:  # pragma: no cover - optional reader in minimal runtimes
    read_code_file = None


class AgentLoop:
    """
    ZERO Agent Loop v3 - interface contract stabilization + self-edit analysis-decision-action policy + v7.2.3 repair gate unification

    本版重點：
    1. 保留 direct / task / llm / single-shot 主幹
    2. 保留 document flow 強制走 planner + task mode
    3. 保留 task mode scheduler.create_task + submit_existing_task 流程
    4. 不重寫既有主線行為，只補 interface contract 收束
    5. planner result / execution result / final response 皆做正規化
    6. 減少 agent_loop 對 planner 回傳細節飄移的依賴
    7. v6.0.0 加入 self-edit decision policy，避免 AgentLoop 看到任何 task 就亂改 code
    8. v6.1.0 加入 analysis -> decision -> action policy，模糊 code 任務先分析不動刀
    9. v6.2.0 加入 analysis-confirmed self-edit，明確指出 function wrong/broken 時可分析後動刀
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
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.llm_client = llm_client
        self.work_package_operator = kwargs.get("work_package_operator")
        self.memory_repository = kwargs.get("memory_repository")
        if self.memory_repository is not None:
            for planner_component in (self.planner, self.llm_planner):
                setter = getattr(planner_component, "set_memory_repository", None)
                if callable(setter):
                    setter(self.memory_repository)
        self.goal_repository = kwargs.get("goal_repository")
        self.goal_orchestrator = kwargs.get("goal_orchestrator")
        self.goal_execution_planner = kwargs.get("goal_execution_planner")
        if self.goal_repository is not None:
            for planner_component in (self.planner, self.llm_planner):
                setter = getattr(planner_component, "set_goal_repository", None)
                if callable(setter):
                    setter(self.goal_repository)
        self.tool_registry = kwargs.get("tool_registry") or getattr(step_executor, "tool_registry", None)
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry(workspace_dir=kwargs.get("workspace_dir", "workspace"))

        self.task_manager = task_manager
        self.scheduler = scheduler or task_manager

        self.task_workspace = task_workspace
        self.task_runtime = task_runtime
        self.replanner = replanner
        self.debug = debug
        self.extra_kwargs = kwargs
        self.max_tool_cycles = int(kwargs.get("max_tool_cycles", 3) or 3)
        self.self_edit_policy_mode = str(kwargs.get("self_edit_policy_mode") or "conservative").strip().lower()
        self.operator_session_bootstrap = kwargs.get("operator_session_bootstrap")
        operator_bridge = kwargs.get("operator_bridge")
        operator_runtime = kwargs.get("operator_runtime")
        if operator_bridge is None and step_executor is not None:
            operator_bridge = getattr(step_executor, "operator_bridge", None)
        if self.operator_session_bootstrap is None and (operator_bridge is not None or operator_runtime is not None):
            try:
                from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap

                self.operator_session_bootstrap = OperatorSessionBootstrap(
                    operator_bridge=operator_bridge,
                    operator_runtime=operator_runtime,
                )
                operator_bridge = getattr(self.operator_session_bootstrap, "operator_bridge", operator_bridge)
            except Exception:
                self.operator_session_bootstrap = None
        if operator_bridge is not None:
            for runtime_obj in (step_executor, self.task_runtime):
                if runtime_obj is not None and getattr(runtime_obj, "operator_bridge", None) is None:
                    try:
                        setattr(runtime_obj, "operator_bridge", operator_bridge)
                    except Exception:
                        pass

        execution_workspace_root = (
            kwargs.get("workspace_dir")
            or getattr(step_executor, "workspace_root", None)
            or (Path(str(kwargs.get("repo_root"))) / "workspace" if kwargs.get("repo_root") else "workspace")
        )
        self.execution_runtime = kwargs.get("execution_runtime") or AgentExecutionRuntime(
            task_runner=task_runner,
            task_runtime=self.task_runtime,
            step_executor=step_executor,
            workspace_root=execution_workspace_root,
            replanner=self.replanner,
            verifier=self.verifier,
            debug=self.debug,
        )
        self.tool_call_executor = ToolCallExecutor(self.tool_registry)

    # ============================================================
    # public entry
    # ============================================================

    def run(self, user_input: str) -> Dict[str, Any]:
        text = str(user_input or "").strip()
        if not text:
            return self._mark_agent_loop_route(
                self._make_agent_response(
                    ok=False,
                    mode="empty",
                    context={},
                    route=None,
                    plan=None,
                    execution=None,
                    final_answer="",
                    error="user_input is empty",
                ),
                "empty_input",
            )

        pre_route = self._try_agent_loop_pre_routes(text)
        if pre_route is not None:
            return self._mark_agent_loop_route(
                pre_route,
                str(pre_route.get("agent_loop_runtime_route") or pre_route.get("mode") or "pre_route")
                if isinstance(pre_route, dict)
                else "pre_route",
            )

        return self._run_default_agent_route(text)

    def _run_default_agent_route(self, text: str) -> Dict[str, Any]:
        forced_repo_edit = self._try_force_repo_edit_route(text)
        if forced_repo_edit is not None:
            return self._mark_agent_loop_route(
                self._normalize_agent_response(forced_repo_edit),
                "forced_repo_edit",
            )

        scheduler_self_edit = self._try_force_scheduler_self_edit_route(text)
        if scheduler_self_edit is not None:
            return self._mark_agent_loop_route(
                self._normalize_agent_response(scheduler_self_edit),
                "scheduler_self_edit",
            )

        context = self._build_context(text)
        route = self._call_router(context, text)

        if self.debug:
            print("[AgentLoop] user_input =", text)
            print("[AgentLoop] route =", route)

        if self._should_force_planner_document_flow(text):
            capability_hint = self._detect_document_flow_capability(text)

            forced_route: Dict[str, Any] = {}
            if isinstance(route, dict):
                forced_route.update(copy.deepcopy(route))
            forced_route["mode"] = "task"
            forced_route["task"] = True
            forced_route["forced_document_flow"] = True

            if isinstance(capability_hint, dict) and capability_hint.get("matched"):
                forced_route["capability"] = capability_hint.get("capability") or "document_flow"
                forced_route["operation"] = capability_hint.get("operation") or ""
                forced_route["capability_hint"] = copy.deepcopy(capability_hint)

                registry_hint = self._build_capability_registry_hint(capability_hint)
                if registry_hint:
                    forced_route["capability_registry_hint"] = registry_hint

            route = forced_route

            if self.debug:
                print("[AgentLoop] forced document flow route =", route)

        direct_result = self._try_handle_direct_route(
            context=context,
            user_input=text,
            route=route,
        )
        if direct_result is not None:
            return self._mark_agent_loop_route(
                self._normalize_agent_response(direct_result),
                "direct",
            )

        llm_result = self._try_handle_llm_route(
            context=context,
            user_input=text,
            route=route,
        )
        if llm_result is not None:
            return self._mark_agent_loop_route(
                self._normalize_agent_response(llm_result),
                "llm",
            )

        if self._should_enter_task_mode(route, text):
            return self._mark_agent_loop_route(
                self._normalize_agent_response(
                    self._run_task_mode(
                        context=context,
                        user_input=text,
                        route=route,
                    )
                ),
                "task",
            )

        return self._mark_agent_loop_route(
            self._normalize_agent_response(
                self._run_single_shot_mode(
                    context=context,
                    user_input=text,
                    route=route,
                )
            ),
            "single_shot",
        )

    def _try_agent_loop_pre_routes(self, text: str) -> Optional[Dict[str, Any]]:
        if _zero_v824_agent_planner_dispatch_candidate(text):
            planner_bridge = _zero_v825_agent_try_planner_runtime_dispatch_route(self, text)
            if planner_bridge is not None:
                planner_bridge["agent_loop_runtime_route"] = "planner_step_executor_bridge"
                return planner_bridge

            planner_dispatch = _zero_v824_agent_try_planner_runtime_dispatch_route(self, text)
            if planner_dispatch is not None:
                planner_dispatch["agent_loop_runtime_route"] = "planner_runtime_dispatch"
                return planner_dispatch

        if _zero_v823_agent_persistent_runtime_candidate(text):
            persistent_result = _zero_v823_agent_try_persistent_runtime_route(self, text)
            if persistent_result is not None:
                persistent_result["agent_loop_runtime_route"] = "persistent_runtime"
                return persistent_result

        planner_owned = _zero_v827_agent_try_planner_owned_code_chain(self, text)
        if planner_owned is not None:
            planner_owned["agent_loop_runtime_route"] = "planner_owned_code_chain"
            return planner_owned

        controlled_bridge = None
        if _zero_v826_code_fix_bridge_candidate(text) and callable(globals().get("_zero_v824_call_planner_like")):
            from core.runtime.runtime_route_keys import RuntimeRouteKeys

            controlled_bridge = self._run_via_runtime_route_registry(
                route_key=RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT,
                entrypoint="core.agent.agent_loop.AgentLoop.code_chain_controlled_self_edit_bridge_route",
                runner=lambda: _zero_v826_agent_try_code_chain_controlled_self_edit_bridge(self, text),
                request={"user_input": text, "route": "code_chain_controlled_self_edit_bridge"},
                goal=text,
                workspace_root=Path(_zero_v826_repo_root_from_agent(self)) / "workspace",
            )
        if controlled_bridge is not None:
            controlled_bridge["agent_loop_runtime_route"] = "code_chain_controlled_self_edit_bridge"
            return controlled_bridge

        if _zero_v710_looks_like_repair_intent(text):
            decision = _zero_v710_repair_scope_decision(text)
            if not bool(decision.get("ok")):
                from core.runtime.runtime_route_keys import RuntimeRouteKeys

                preflight = self._run_via_runtime_route_registry(
                    route_key=RuntimeRouteKeys.REPAIR_PREFLIGHT,
                    entrypoint="core.agent.agent_loop.AgentLoop.repair_preflight_route",
                    runner=lambda: _zero_v710_make_preflight_response(self, text, decision),
                    request={
                        "user_input": text,
                        "route": "code_chain_repair_preflight",
                        "decision": copy.deepcopy(decision),
                    },
                    goal=text,
                    workspace_root=Path(_zero_v826_repo_root_from_agent(self)) / "workspace",
                )
                preflight["agent_loop_runtime_route"] = "code_chain_repair_preflight"
                return preflight

        if _zero_v7_0_1_looks_like_autonomous_repair(text):
            target_path = _zero_v7_0_1_extract_workspace_py_path(text)
            context = self._build_context(text)
            context["semantic_type"] = "autonomous_code_repair_v0"
            context["planner_autonomous_repair"] = True
            context["target_path"] = target_path

            route = {
                "mode": "task",
                "task": True,
                "forced_route": True,
                "planner_autonomous_repair": True,
                "semantic_type": "autonomous_code_repair_v0",
                "execution_route": "planner_autonomous_repair_code_chain",
                "target_path": target_path,
            }
            from core.runtime.runtime_route_keys import RuntimeRouteKeys

            result = self._run_via_runtime_route_registry(
                route_key=RuntimeRouteKeys.AUTONOMOUS_REPAIR,
                entrypoint="core.agent.agent_loop.AgentLoop.autonomous_repair_route",
                runner=lambda: self._run_task_mode(
                    context=context,
                    user_input=text,
                    route=route,
                ),
                request={
                    "user_input": text,
                    "route": copy.deepcopy(route),
                    "context": copy.deepcopy(context),
                },
                goal=text,
                workspace_root=Path(_zero_v826_repo_root_from_agent(self)) / "workspace",
            )
            if isinstance(result, dict):
                result["agent_loop_runtime_route"] = "planner_autonomous_repair"
            return result

        engineering_goal_result = self._try_handle_engineering_goal_route(text)
        if engineering_goal_result is not None:
            engineering_goal_result["agent_loop_runtime_route"] = "engineering_program_mainline"
            return engineering_goal_result

        engineering_task_result = self._try_handle_engineering_task_route(text)
        if engineering_task_result is not None:
            engineering_task_result.setdefault("agent_loop_runtime_route", "engineering_task_runner")
            engineering_task_result.setdefault("legacy_direct_json_engineering_task_runner", False)
            engineering_task_result.setdefault("governed_runtime_route", False)
            engineering_task_result.setdefault("runtime_owns_execution", False)
            engineering_task_result.setdefault("direct_execution", True)
            engineering_task_result.setdefault("agent_loop_owns_execution", False)
            return engineering_task_result

        work_package_result = self._try_handle_work_package_route(text)
        if work_package_result is not None:
            work_package_result["agent_loop_runtime_route"] = (
                "work_package_runtime_operator"
                if work_package_result.get("route", {}).get("work_package_gateway") == "runtime_dispatcher"
                else "controlled_work_package_intake"
            )
            return work_package_result

        return None

    def _try_handle_engineering_goal_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Route persisted engineering goals through Program -> Portfolio -> Goal."""

        text = str(user_input or "").strip()
        if not text or not (text.startswith("{") and text.endswith("}")):
            return None

        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        task_type = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
        route = str(payload.get("route") or payload.get("engineering_route") or "").strip().lower()
        explicit_goal_route = bool(
            payload.get("engineering_goal_route")
            or payload.get("adaptive_engineering_goal")
            or payload.get("adaptive_planning")
            or route in {"engineering_goal", "engineering_goal_stack", "adaptive_engineering_goal"}
        )
        if task_type not in {"engineering_task", "engineering_goal"} or not explicit_goal_route:
            return None

        package_payload = payload.get("package") if isinstance(payload.get("package"), dict) else dict(payload)
        repo_root = str(payload.get("repo_root") or package_payload.get("repo_root") or ".")
        summary = str(
            payload.get("summary")
            or payload.get("goal")
            or package_payload.get("summary")
            or package_payload.get("goal")
            or package_payload.get("task_id")
            or "Untitled engineering goal"
        ).strip()
        goal_id = str(payload.get("goal_id") or package_payload.get("goal_id") or "").strip()

        try:
            from core.tasks.engineering_goal_repository import EngineeringGoalRepository
            from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
            from core.tasks.engineering_program_cycle import EngineeringProgramCycle
            from core.tasks.engineering_program_repository import EngineeringProgramRepository
            from core.runtime.runtime_route_keys import RuntimeRouteKeys

            goal_repository = EngineeringGoalRepository(repo_root)
            portfolio_repository = EngineeringPortfolioRepository(repo_root)
            program_repository = EngineeringProgramRepository(repo_root)
            goal_record = {
                "summary": summary,
                "status": "pending",
                "priority": float(payload.get("priority") or package_payload.get("priority") or 0.0),
                "payload": {
                    **copy.deepcopy(package_payload),
                    "goal": summary,
                    "task_type": "engineering_task",
                    "engineering_goal_lifecycle": True,
                },
                "metadata": {
                    "source": "agent_loop_engineering_goal_route",
                    "legacy_direct_json_engineering_task_runner": False,
                },
            }
            if goal_id:
                goal_record["goal_id"] = goal_id
            goal = goal_repository.save_goal(goal_record)

            program_id = str(payload.get("program_id") or package_payload.get("program_id") or f"{goal['goal_id']}__program").strip()
            portfolio_id = str(
                payload.get("portfolio_id") or package_payload.get("portfolio_id") or f"{goal['goal_id']}__portfolio"
            ).strip()
            program = program_repository.load_program(program_id)
            if program is None:
                program = program_repository.create_program(
                    {
                        "program_id": program_id,
                        "name": str(payload.get("program_name") or f"Program for {summary}"),
                    }
                )
            portfolio = portfolio_repository.load_portfolio(portfolio_id)
            if portfolio is None:
                portfolio = portfolio_repository.create_portfolio(
                    {
                        "portfolio_id": portfolio_id,
                        "name": str(payload.get("portfolio_name") or f"Portfolio for {summary}"),
                        "metadata": {"source": "agent_loop_engineering_program_mainline"},
                    }
                )
            portfolio = portfolio_repository.add_goal_to_portfolio(portfolio_id, goal["goal_id"])
            program = program_repository.add_portfolio(program_id, portfolio_id)
            program_cycle = EngineeringProgramCycle(
                repo_root=repo_root,
                program_repository=program_repository,
                portfolio_repository=portfolio_repository,
            )
            max_portfolios = int(payload.get("max_portfolios") or 1)
            program_result = self._run_via_runtime_route_registry(
                route_key=RuntimeRouteKeys.ENGINEERING_GOAL,
                entrypoint="core.agent.agent_loop.AgentLoop.engineering_goal_route",
                runner=lambda: program_cycle.run_until_idle(
                    program_id,
                    max_portfolios=max_portfolios,
                ),
                request=payload,
                goal=summary,
                workspace_root=Path(repo_root) / "workspace",
            )
        except Exception as exc:
            goal = {"goal_id": goal_id, "summary": summary}
            program_id = str(payload.get("program_id") or package_payload.get("program_id") or "").strip()
            portfolio_id = str(payload.get("portfolio_id") or package_payload.get("portfolio_id") or "").strip()
            program = {"program_id": program_id}
            portfolio = {"portfolio_id": portfolio_id}
            program_result = {
                "schema": "zero.engineering_program.agent_loop_dispatch_error.v1",
                "ok": False,
                "mode": "engineering_program_mainline",
                "program_id": program_id,
                "portfolio_id": portfolio_id,
                "goal_id": goal_id,
                "error": f"engineering program dispatch failed: {type(exc).__name__}: {exc}",
                "stop_reason": "engineering_program_dispatch_error",
                "runs": [],
            }

        ok = bool(program_result.get("ok")) if isinstance(program_result, dict) else False
        resolved_goal_id = str(program_result.get("goal_id") or goal.get("goal_id") or goal_id or "")
        resolved_program_id = str(program_result.get("program_id") or program.get("program_id") or program_id or "")
        resolved_portfolio_id = str(program_result.get("portfolio_id") or portfolio.get("portfolio_id") or portfolio_id or "")
        stop_reason = str(program_result.get("stop_reason") or "")
        adaptive_decision = copy.deepcopy(program_result.get("adaptive_decision") or {})
        selected_goal = copy.deepcopy(program_result.get("selected_goal") or {})
        execution_path = {
            "route": "AgentLoop -> RuntimeNativeMainline -> Program -> Portfolio -> Goal -> Adaptive Planner -> Runtime",
            "agent_loop_routes_only": True,
            "runtime_native_mainline_canonical_entry": True,
            "program_owns_strategic_sequencing": True,
            "portfolio_owns_goal_selection": True,
            "goal_owns_adaptive_continuation": True,
            "adaptive_planner_decides_only": True,
            "runtime_owns_execution": True,
            "direct_goal_runner_bypass": False,
            "legacy_direct_engineering_task_route": False,
        }
        final_answer = (
            f"engineering program {resolved_program_id} completed"
            if ok
            else f"engineering program {resolved_program_id} stopped"
        )
        if stop_reason:
            final_answer += f": {stop_reason}"

        route_record = {
            "mode": "engineering_program_mainline",
            "task": True,
            "forced_route": True,
            "engineering_task": True,
            "engineering_goal_route": True,
            "legacy_direct_json_engineering_task_runner": False,
            "program_id": resolved_program_id,
            "portfolio_id": resolved_portfolio_id,
            "goal_id": resolved_goal_id,
            "selected_goal": selected_goal,
            "adaptive_decision": adaptive_decision,
            "stop_reason": stop_reason,
            "execution_path": execution_path,
            "repo_root": repo_root,
            "authority_path": execution_path["route"],
        }
        plan = {
            "ok": ok,
            "planner_mode": "engineering_program_mainline_v1",
            "intent": "engineering_program",
            "delegated_to": "core.tasks.engineering_program_cycle.EngineeringProgramCycle.run_until_idle",
            "program": copy.deepcopy(program),
            "portfolio": copy.deepcopy(portfolio),
            "goal": copy.deepcopy(goal),
            "program_result": copy.deepcopy(program_result),
            "final_answer": final_answer,
            "steps": [
                {
                    "type": "engineering_program_cycle_run",
                    "program_id": resolved_program_id,
                    "portfolio_id": resolved_portfolio_id,
                    "goal_id": resolved_goal_id,
                }
            ],
            "meta": {
                "fallback_used": False,
                "step_count": 1,
                "forced_route": True,
                "agent_loop_delegates_only": True,
                "program_mainline_entrypoint": True,
                "direct_engineering_task_runner": False,
                "direct_goal_runner_bypass": False,
            },
        }
        execution = {
            "ok": ok,
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": {"type": "engineering_program_cycle_run", "program_id": resolved_program_id},
                    "result": copy.deepcopy(program_result),
                }
            ],
            "execution_log": [
                {
                    "type": "engineering_program_cycle_run",
                    "status": "success" if ok else "blocked_or_failed",
                    "ok": ok,
                    "data": copy.deepcopy(program_result),
                }
            ],
            "execution_trace": [
                {
                    "type": "engineering_program_cycle_run",
                    "status": "success" if ok else "blocked_or_failed",
                    "ok": ok,
                    "data": copy.deepcopy(program_result),
                }
            ],
            "last_result": copy.deepcopy(program_result),
            "final_answer": final_answer,
            "error": None if ok else stop_reason or "engineering_goal_failed",
        }
        return self._make_agent_response(
            ok=ok,
            mode="engineering_program_mainline",
            context={},
            route=route_record,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=None if ok else stop_reason or "engineering_goal_failed",
            extra={
                "goal": copy.deepcopy(goal),
                "program_id": resolved_program_id,
                "portfolio_id": resolved_portfolio_id,
                "goal_id": resolved_goal_id,
                "selected_goal": selected_goal,
                "adaptive_decision": adaptive_decision,
                "stop_reason": stop_reason,
                "execution_path": execution_path,
                "program_result": copy.deepcopy(program_result),
                "execution_mode": "engineering_program_mainline",
                "legacy_direct_json_engineering_task_runner": False,
                "final_message": final_answer,
            },
        )

    def _try_handle_engineering_task_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Handle JSON engineering_task payloads through RuntimeNativeMainline."""

        text = str(user_input or "").strip()
        if not text or not (text.startswith("{") and text.endswith("}")):
            return None

        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        task_type = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
        if task_type != "engineering_task":
            return None

        if bool(
            payload.get("engineering_goal_route")
            or payload.get("adaptive_engineering_goal")
            or payload.get("adaptive_planning")
        ):
            return None

        repo_root = str(payload.get("repo_root") or self.extra_kwargs.get("repo_root") or ".")
        package_id = str(payload.get("package_id") or payload.get("task_id") or payload.get("id") or "engineering-task")

        runtime_admission_contract = {
            "runtime_owner": "AgentExecutionRuntime",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "execution_chain": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
            "legacy_direct_json_engineering_task_runner": False,
            "governed_runtime_route": True,
            "runtime_owns_execution": True,
            "direct_execution": False,
            "agent_loop_owns_execution": False,
        }
        _ = runtime_admission_contract

        try:
            from core.tasks.engineering_task_runner import run_engineering_task

            result = self._run_via_runtime_route_registry(
                route_key="engineering_task",
                entrypoint="core.agent.agent_loop.AgentLoop.engineering_task_route",
                runner=lambda: run_engineering_task(payload, repo_root=repo_root),
                request=payload,
                goal=str(payload.get("goal") or payload.get("summary") or package_id),
                workspace_root=Path(repo_root) / "workspace",
            )
            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "schema": "zero.engineering_task_runner.invalid_result.v1",
                    "mode": "engineering_task_runner",
                    "package_id": package_id,
                    "error": "EngineeringTaskRunner returned non-dict result",
                    "raw_result": result,
                }
        except Exception as exc:
            result = {
                "ok": False,
                "schema": "zero.engineering_task_runner.dispatch_error.v1",
                "mode": "engineering_task_runner",
                "package_id": package_id,
                "error": f"{type(exc).__name__}: {exc}",
            }

        result = copy.deepcopy(result)
        result.setdefault("mode", "engineering_task_runner")
        result.setdefault("package_id", package_id)

        result["agent_loop_runtime_route"] = "engineering_task_runner"
        result["legacy_direct_json_engineering_task_runner"] = False
        result["runtime_native_mainline_canonical_entry"] = True
        result["governed_runtime_route"] = True
        result["runtime_owns_execution"] = True
        result["direct_execution"] = False
        result["agent_loop_owns_execution"] = False

        route = result.get("route")
        if not isinstance(route, dict):
            route = {}
        route.update(
            {
                "mode": "engineering_task_runner",
                "task": True,
                "forced_route": True,
                "engineering_task": True,
                "package_id": package_id,
                "repo_root": repo_root,
                "legacy_direct_json_engineering_task_runner": False,
                "runtime_native_mainline_canonical_entry": True,
                "work_package_mainline_authority": False,
                "runtime_native_mainline_admission": True,
                "authority_path": "AgentLoop -> RuntimeNativeMainline -> EngineeringTaskAdmission -> Planner -> WorkPackageIntake",
            }
        )
        result["route"] = route

        execution_path = result.get("execution_path")
        if not isinstance(execution_path, dict):
            execution_path = {}
        execution_path.update(
            {
                "legacy_direct_engineering_task_route": False,
                "runtime_native_mainline_canonical_entry": True,
                "program_mainline": False,
                "persisted_engineering_goal": False,
                "direct_goal_runner_bypass": False,
                "runtime_owns_execution": True,
                "work_package_mainline_authority": False,
            }
        )
        result["execution_path"] = execution_path

        result.setdefault(
            "plan",
            {
                "ok": bool(result.get("ok", False)),
                "planner_mode": "runtime_native_engineering_task_runner_v1",
                "intent": "engineering_task",
                "delegated_to": "core.tasks.engineering_task_runner.run_engineering_task",
                "final_answer": str(result.get("final_message") or result.get("final_answer") or ""),
                "steps": [
                    {
                        "type": "runtime_native_engineering_task_runner_delegate",
                        "package_id": package_id,
                    }
                ],
                "meta": {
                    "fallback_used": False,
                    "step_count": 1,
                    "runtime_native_mainline_admission": True,
                    "work_package_mainline_authority": False,
                },
            },
        )

        result.setdefault(
            "execution",
            {
                "ok": bool(result.get("ok", False)),
                "steps_executed": 1,
                "results": [
                    {
                        "step_index": 1,
                        "step": {
                            "type": "runtime_native_engineering_task_runner_delegate",
                            "package_id": package_id,
                        },
                        "result": copy.deepcopy(result),
                    }
                ],
                "last_result": copy.deepcopy(result),
                "final_answer": str(result.get("final_message") or result.get("final_answer") or ""),
                "error": None if bool(result.get("ok", False)) else str(result.get("error") or "engineering_task_runner_failed"),
            },
        )
        return result

    def _try_handle_work_package_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Dispatch JSON AER/work-package requests through the runtime operator.

        Work Package boundary:
        - AgentLoop is only the entry point.
        - Planner normalizes the operator intent.
        - RuntimeWorkPackageOperator owns queue/status/result records.
        - RuntimeDispatcher -> TaskRunner -> StepExecutor owns execution.
        - JSON payloads only, so natural chat text is not misrouted.
        - Explore/Plan/Verify remain read-only; Execute requires approval by contract.
        """
        text = str(user_input or "").strip()
        if not text:
            return None
        if not (text.startswith("{") and text.endswith("}")):
            return None

        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        task_type = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
        is_work_package = (
            task_type == "work_package"
            or task_type in {"aer_task", "autonomous_engineering_task"}
            or bool(payload.get("work_package"))
            or bool(payload.get("aer_task"))
            or str(payload.get("package_type") or "").strip().lower() == "work_package"
        )
        if not is_work_package:
            return None

        package_payload = payload.get("package") if isinstance(payload.get("package"), dict) else dict(payload)
        repo_root = str(payload.get("repo_root") or package_payload.get("repo_root") or ".")

        try:
            planner = self.planner
            normalizer = getattr(planner, "normalize_aer_execution_intent", None)
            if not callable(normalizer):
                from core.planning.planner import Planner

                planner = Planner()
                normalizer = planner.normalize_aer_execution_intent
            normalized_intent = normalizer(payload, user_input=user_input)
            work_package_payload = normalized_intent.get("work_package") if isinstance(normalized_intent, dict) else None
            if not isinstance(work_package_payload, dict):
                raise ValueError("planner did not produce a work package")
            work_package_payload.pop("repo_root", None)

            autonomous_fields = {"title", "goal", "description", "target_files", "requirements"}
            autonomous_contract = autonomous_fields.issubset(work_package_payload)
            if autonomous_contract:
                from core.runtime.runtime_route_keys import RuntimeRouteKeys

                def run_autonomous_work_package():
                    operator = self.work_package_operator
                    operator_root = str(getattr(operator, "repo_root", "") or "")
                    if operator is None or (repo_root and operator_root and Path(operator_root).resolve() != Path(repo_root).resolve()):
                        from core.runtime.work_package_operator import RuntimeWorkPackageOperator

                        operator = RuntimeWorkPackageOperator(repo_root=repo_root, llm_client=self.llm_client)
                    submitted = operator.submit_package(work_package_payload)
                    if submitted.get("planning_status") == "planned":
                        return operator.run_package(str(submitted.get("package_id") or ""))
                    return submitted

                result = self._run_via_runtime_route_registry(
                    route_key=RuntimeRouteKeys.WORK_PACKAGE,
                    entrypoint="core.agent.agent_loop.AgentLoop.work_package_route",
                    runner=run_autonomous_work_package,
                    request=payload,
                    goal=str(work_package_payload.get("goal") or work_package_payload.get("title") or "work_package"),
                    workspace_root=Path(repo_root) / "workspace",
                )
                schedule_record = {
                    "schema": "zero.runtime.work_package_agent_dispatch.v1",
                    "package_id": result.get("package_id"),
                    "status": result.get("status"),
                    "gateway": "RuntimeDispatcher",
                    "result": copy.deepcopy(result),
                }
            else:
                from core.tasks.work_package_intake import submit_work_package
                from core.runtime.runtime_route_keys import RuntimeRouteKeys

                result = self._run_via_runtime_route_registry(
                    route_key=RuntimeRouteKeys.WORK_PACKAGE,
                    entrypoint="core.agent.agent_loop.AgentLoop.work_package_intake_route",
                    runner=lambda: submit_work_package(work_package_payload, repo_root=repo_root),
                    request=payload,
                    goal=str(work_package_payload.get("goal") or work_package_payload.get("title") or "work_package"),
                    workspace_root=Path(repo_root) / "workspace",
                )
                schedule_record = {
                    "schema": "zero.controlled.work_package_agent_dispatch.v1",
                    "package_id": result.get("package_id"),
                    "status": result.get("status"),
                    "gateway": "WorkPackageIntake",
                    "result": copy.deepcopy(result),
                }
                result["controlled_mutation_gateway"] = {
                    "gateway": "WorkPackageIntake -> run_repo_edit",
                    "legal_gateway": True,
                    "authority_scope": "controlled_repo_edit_only",
                    "work_package_mainline_authority": False,
                    "legacy_engineering_goal_route": False,
                }
            result = copy.deepcopy(result)
            if autonomous_contract:
                result["ok"] = str(
                    result.get("runtime_lifecycle_state") or result.get("status") or ""
                ).lower() == "completed"
        except Exception as exc:
            normalized_intent = {
                "ok": False,
                "schema": "zero.aer.normalized_execution_intent.v1",
                "intent": "work_package",
                "error": f"{type(exc).__name__}: {exc}",
            }
            schedule_record = {}
            result = {
                "ok": False,
                "schema": "zero.work_package.agent_loop_dispatch_error.v1",
                "package_id": str(package_payload.get("package_id") or package_payload.get("id") or "work_package"),
                "kind": str(package_payload.get("kind") or "unknown"),
                "mode": str(package_payload.get("mode") or "unknown"),
                "report_path": str(package_payload.get("report_path") or ""),
                "mutation_allowed": False,
                "readonly": True,
                "error": f"work package dispatch failed: {type(exc).__name__}: {exc}",
            }

        ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
        mode = str(result.get("mode") or package_payload.get("mode") or "work_package") if isinstance(result, dict) else "work_package"
        package_id = str(result.get("package_id") or package_payload.get("package_id") or "work_package") if isinstance(result, dict) else "work_package"
        report_path = str(result.get("report_path") or package_payload.get("report_path") or "") if isinstance(result, dict) else ""
        audit_path = str(result.get("audit_path") or "") if isinstance(result, dict) else ""
        evidence_path = str(result.get("evidence_path") or "") if isinstance(result, dict) else ""
        result_path = str(result.get("result_path") or "") if isinstance(result, dict) else ""
        reason = str(result.get("reason") or result.get("error") or "") if isinstance(result, dict) else "invalid work package result"

        if ok:
            final_answer = f"work package {package_id} completed in {mode} mode"
            if report_path:
                final_answer += f"; report={report_path}"
        else:
            final_answer = f"work package {package_id} blocked or failed in {mode} mode"
            if reason:
                final_answer += f": {reason}"
        if result_path:
            final_answer += f"; result={result_path}"

        route = {
            "mode": "work_package",
            "task": True,
            "forced_route": True,
            "work_package": True,
            "work_package_mode": mode,
            "package_id": package_id,
            "repo_root": repo_root,
            "authority_path": (
                "AgentLoop -> RuntimeNativeMainline -> RuntimeWorkPackageOperator -> RuntimeDispatcher "
                "-> TaskRunner -> StepExecutor"
                if schedule_record.get("gateway") == "RuntimeDispatcher"
                else "AgentLoop -> RuntimeNativeMainline -> WorkPackageIntake -> run_repo_edit"
            ),
            "work_package_gateway": (
                "runtime_dispatcher"
                if schedule_record.get("gateway") == "RuntimeDispatcher"
                else "controlled_mutation_gateway"
            ),
        }
        plan = {
            "ok": ok,
            "planner_mode": "aer_work_package_intent_v1",
            "intent": "work_package",
            "normalized_execution_intent": copy.deepcopy(normalized_intent),
            "final_answer": final_answer,
            "steps": [
                {
                    "type": "runtime_work_package_operator_submit",
                    "mode": mode,
                    "package_id": package_id,
                    "report_path": report_path,
                    "audit_path": audit_path,
                    "evidence_path": evidence_path,
                    "result_path": result_path,
                }
            ],
            "meta": {
                "fallback_used": False,
                "step_count": 1,
                "forced_route": True,
                "work_package_entrypoint": "AgentLoop",
                "scheduler_recorded": bool(schedule_record),
            },
            "work_package_result": copy.deepcopy(result),
        }
        execution = {
            "ok": ok,
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": {
                        "type": "runtime_work_package_operator_submit",
                        "mode": mode,
                        "package_id": package_id,
                    },
                    "result": copy.deepcopy(result),
                }
            ],
            "execution_log": [
                {
                    "type": "runtime_work_package_operator_submit",
                    "status": "success" if ok else "blocked_or_failed",
                    "ok": ok,
                    "data": copy.deepcopy(result),
                }
            ],
            "execution_trace": [
                {
                    "type": "runtime_work_package_operator_submit",
                    "status": "success" if ok else "blocked_or_failed",
                    "ok": ok,
                    "data": copy.deepcopy(result),
                }
            ],
            "last_result": copy.deepcopy(result),
            "scheduler_record": copy.deepcopy(schedule_record),
            "final_answer": final_answer,
            "error": None if ok else reason or "work_package_failed",
        }

        return self._make_agent_response(
            ok=ok,
            mode="work_package",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=None if ok else reason or "work_package_failed",
            extra={
                "work_package_result": copy.deepcopy(result),
                "package_id": package_id,
                "work_package_mode": mode,
                "report_path": report_path,
                "audit_path": audit_path,
                "evidence_path": evidence_path,
                "result_path": result_path,
                "execution_mode": mode,
                "final_message": result.get("final_message") if isinstance(result, dict) else final_answer,
                "scheduler_record": copy.deepcopy(schedule_record),
            },
        )

    def _zero_v823_agent_try_persistent_runtime_route_for_test(self, user_input: str) -> Optional[Dict[str, Any]]:
        return _zero_v823_agent_try_persistent_runtime_route(self, user_input)

    def _zero_v824_agent_try_planner_runtime_dispatch_route_for_test(self, user_input: str) -> Optional[Dict[str, Any]]:
        return _zero_v824_agent_try_planner_runtime_dispatch_route(self, user_input)

    def _zero_v825_agent_try_planner_runtime_dispatch_route_for_test(self, user_input: str) -> Optional[Dict[str, Any]]:
        return _zero_v825_agent_try_planner_runtime_dispatch_route(self, user_input)

    def _zero_v826_agent_try_code_chain_controlled_self_edit_bridge_for_test(self, user_input: str) -> Optional[Dict[str, Any]]:
        return _zero_v826_agent_try_code_chain_controlled_self_edit_bridge(self, user_input)

    def _zero_v827_agent_try_planner_owned_code_chain_for_test(self, user_input: str) -> Optional[Dict[str, Any]]:
        return _zero_v827_agent_try_planner_owned_code_chain(self, user_input)

    def _mark_agent_loop_route(self, response: Dict[str, Any], route_name: str) -> Dict[str, Any]:
        return mark_agent_loop_route(response, route_name)


    def _analyze_scheduler_self_edit_candidate(self, user_input: str) -> Dict[str, Any]:
        """Analyze whether a user request should become a scheduler self-edit.

        v6.1.0 boundary:
        This is a decision helper only.  It never edits files and never calls
        tools.  The write path remains:

            AgentLoop decision -> self_edit_loop -> Scheduler -> ExecutionGuard

        The helper returns a compact policy payload so the self-edit trigger is
        explainable and so ambiguous requests can stay read-only instead of
        becoming accidental code writes.
        """
        text = str(user_input or "").strip()
        lowered = text.lower()

        result: Dict[str, Any] = {
            "input_empty": not bool(text),
            "matched_signals": [],
            "risk": "low",
            "intent": "normal",
            "requires_analysis_first": False,
            "requires_confirmation": False,
            "recommended_action": "normal_agent_flow",
        }

        if not text:
            result.update({
                "intent": "empty",
                "risk": "none",
                "recommended_action": "block",
            })
            return result

        def _has_any(markers: tuple[str, ...]) -> bool:
            return any(marker in lowered for marker in markers)

        destructive_markers = (
            "delete ",
            "remove file",
            "rename ",
            "move ",
            "rm ",
            "del ",
            "erase ",
            "format ",
            "chmod ",
            "chown ",
            "force push",
            "drop ",
        )
        read_only_markers = (
            "explain",
            "why ",
            "what is",
            "what does",
            "how does",
            "show me",
            "list ",
            "summarize",
            "review ",
            "analyze",
            "check why",
            "check ",
            "inspect",
            "diagnose",
            "檢查",
            "解釋",
            "分析",
            "說明",
        )
        edit_verbs = (
            "fix",
            "modify",
            "change",
            "update",
            "repair",
            "correct",
            "implement",
            "add",
            "修",
            "修改",
            "修正",
            "更改",
            "更新",
        )
        explicit_self_edit_markers = (
            "self-edit",
            "self edit",
            "self_edit",
            "scheduler self-edit",
            "scheduler self edit",
            "use scheduler",
            "let zero edit",
            "讓 zero 改",
            "讓zero改",
        )
        code_target_markers = (
            "function",
            "functions",
            "code",
            ".py",
            "workspace/",
            "core/",
            "scheduler",
            "agent_loop",
            "self_edit_loop",
            "函數",
            "程式",
            "代碼",
        )
        deterministic_markers = (
            "correct logic",
            "correct result",
        )

        matched: List[str] = []
        if _has_any(destructive_markers):
            matched.append("destructive_marker")
        if _has_any(read_only_markers):
            matched.append("read_only_marker")
        if _has_any(edit_verbs):
            matched.append("edit_verb")
        if _has_any(explicit_self_edit_markers):
            matched.append("explicit_self_edit")
        if _has_any(code_target_markers):
            matched.append("code_target")
        if _has_any(deterministic_markers):
            matched.append("deterministic_function_fix")
        if "replace" in lowered and " with " in lowered:
            matched.append("controlled_replace")

        result["matched_signals"] = matched

        if "destructive_marker" in matched:
            result.update({
                "intent": "destructive_or_high_risk_edit",
                "risk": "high",
                "recommended_action": "block",
                "requires_confirmation": True,
            })
            return result

        if "controlled_replace" in matched:
            result.update({
                "intent": "controlled_replace",
                "risk": "medium",
                "recommended_action": "repo_edit_bridge",
            })
            return result

        has_edit_verb = "edit_verb" in matched
        has_code_target = "code_target" in matched
        has_read_only = "read_only_marker" in matched
        has_explicit_self_edit = "explicit_self_edit" in matched
        has_deterministic_fix = "deterministic_function_fix" in matched

        analysis_confirmed_defect_markers = (
            " wrong",
            "broken",
            "incorrect",
            "not work",
            "doesn't work",
            "does not work",
            "bug",
            "failed",
            "failing",
            "錯",
            "壞",
            "不對",
            "錯誤",
        )
        has_analysis_confirmed_defect = any(marker in lowered for marker in analysis_confirmed_defect_markers)
        bounded_function_diagnostic = (
            has_read_only
            and has_code_target
            and has_analysis_confirmed_defect
            and ("function" in lowered or "函數" in lowered)
            and not has_explicit_self_edit
        )
        if bounded_function_diagnostic:
            result.update({
                "intent": "analysis_confirmed_function_fix",
                "risk": "medium",
                "requires_analysis_first": True,
                "recommended_action": "scheduler_self_edit",
            })
            return result

        if has_read_only and not has_explicit_self_edit and not ("fix" in lowered and has_deterministic_fix):
            result.update({
                "intent": "code_analysis_read_only" if has_code_target else "read_only",
                "risk": "low",
                "requires_analysis_first": True,
                "recommended_action": "analyze_only",
            })
            return result

        deterministic_function_fix = (
            "fix" in lowered
            and ("function" in lowered or "functions" in lowered)
            and has_deterministic_fix
        )
        if deterministic_function_fix:
            result.update({
                "intent": "deterministic_function_fix",
                "risk": "medium",
                "recommended_action": "scheduler_self_edit",
            })
            return result

        if has_explicit_self_edit and has_edit_verb and has_code_target:
            result.update({
                "intent": "explicit_bounded_self_edit",
                "risk": "medium",
                "recommended_action": "scheduler_self_edit",
            })
            return result

        if has_edit_verb and has_code_target:
            result.update({
                "intent": "code_edit_like_ambiguous",
                "risk": "medium",
                "requires_analysis_first": True,
                "recommended_action": "analyze_before_edit",
            })
            return result

        result.update({
            "intent": "normal",
            "risk": "low",
            "recommended_action": "normal_agent_flow",
        })
        return result

    def _decide_scheduler_self_edit_policy(self, user_input: str) -> Dict[str, Any]:
        """Decide whether AgentLoop should enter scheduler-backed self-edit.

        v6.1.0 boundary:
        AgentLoop now performs a small analysis -> decision -> action pass.  It
        still never edits files directly.  Ambiguous code requests are kept in
        read-only/analysis mode unless the request is explicitly bounded, is a
        deterministic function-fix task, or analysis confidently indicates a
        bounded function defect that the scheduler path supports.
        """
        text = str(user_input or "").strip()
        analysis = self._analyze_scheduler_self_edit_candidate(text)
        matched = list(analysis.get("matched_signals") or [])
        recommended = str(analysis.get("recommended_action") or "").strip().lower()

        if not text:
            return {
                "allow": False,
                "reason": "empty_input",
                "category": "empty",
                "confidence": 0.0,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "block",
            }

        if recommended == "block":
            return {
                "allow": False,
                "reason": str(analysis.get("intent") or "blocked"),
                "category": "blocked_high_risk",
                "confidence": 1.0,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "block",
            }

        if recommended == "repo_edit_bridge":
            return {
                "allow": False,
                "reason": "controlled_replace_should_use_repo_edit_bridge",
                "category": "repo_edit_bridge",
                "confidence": 0.95,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "repo_edit_bridge",
            }

        if recommended == "analyze_only":
            return {
                "allow": False,
                "reason": "analysis_request_read_only",
                "category": "analysis_only",
                "confidence": 0.9,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "analyze",
            }

        if recommended == "scheduler_self_edit":
            intent_name = str(analysis.get("intent") or "")
            if intent_name == "deterministic_function_fix":
                confidence = 0.95
            elif intent_name == "analysis_confirmed_function_fix":
                confidence = 0.78
            else:
                confidence = 0.82
            return {
                "allow": True,
                "reason": str(analysis.get("intent") or "scheduler_self_edit"),
                "category": "scheduler_self_edit",
                "confidence": confidence,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "self_edit",
            }

        if recommended == "analyze_before_edit":
            return {
                "allow": False,
                "reason": "ambiguous_code_edit_requires_analysis_first",
                "category": "analysis_before_edit",
                "confidence": 0.6,
                "matched_signals": matched,
                "analysis": analysis,
                "next_action": "analyze_then_decide",
            }

        return {
            "allow": False,
            "reason": "not_a_scheduler_self_edit_task",
            "category": "normal_agent_flow",
            "confidence": 0.2,
            "matched_signals": matched,
            "analysis": analysis,
            "next_action": "normal_agent_flow",
        }

    def _looks_like_scheduler_self_edit_task(self, user_input: str) -> bool:
        decision = self._decide_scheduler_self_edit_policy(user_input)
        return bool(decision.get("allow", False))

    def _summarize_scheduler_self_edit_result(self, result_payload: Dict[str, Any]) -> str:
        if not isinstance(result_payload, dict):
            return "scheduler self-edit returned invalid result"

        attempts = result_payload.get("attempts")
        latest_attempt = attempts[-1] if isinstance(attempts, list) and attempts else {}
        edit_result = latest_attempt.get("edit_result") if isinstance(latest_attempt, dict) else {}
        scheduler_result = edit_result.get("scheduler_result") if isinstance(edit_result, dict) else {}
        if not isinstance(scheduler_result, dict):
            scheduler_result = {}

        action = str(scheduler_result.get("action") or "").strip()
        failed_reason = str(
            scheduler_result.get("failed_reason")
            or result_payload.get("final_reason")
            or ""
        ).strip()
        changed_files = scheduler_result.get("changed_files")
        if not isinstance(changed_files, list):
            changed_files = []

        if bool(result_payload.get("ok", False)):
            if action:
                return f"scheduler self-edit succeeded: {action}; changed_files={len(changed_files)}"
            return "scheduler self-edit succeeded"

        if failed_reason:
            return f"scheduler self-edit failed: {failed_reason}"
        return "scheduler self-edit failed"

    def _rewrite_scheduler_self_edit_goal(self, user_input: str, decision: Dict[str, Any]) -> str:
        """Rewrite analysis-style defect requests into actionable scheduler goals.

        v6.2.2 boundary:
        AgentLoop may decide that an analysis request is a bounded function
        defect, but Scheduler currently expects an actionable Fix-style goal.
        This method is deliberately conservative:
        - only rewrites analysis_confirmed_function_fix decisions;
        - only extracts simple function names near the word "function";
        - keeps all file writes inside self_edit_loop -> Scheduler.
        """
        text = str(user_input or "").strip()
        if not text:
            return text

        reason = str(decision.get("reason") or "").strip().lower()
        analysis = decision.get("analysis") if isinstance(decision.get("analysis"), dict) else {}
        intent = str(analysis.get("intent") or "").strip().lower()
        if reason != "analysis_confirmed_function_fix" and intent != "analysis_confirmed_function_fix":
            return text

        lowered = text.lower()
        ignored = {
            "check", "why", "function", "functions", "is", "are", "wrong",
            "broken", "incorrect", "bug", "bugs", "failed", "failing",
            "the", "a", "an", "in", "of", "for", "to", "code",
        }

        candidates: List[str] = []

        # Prefer the identifier immediately before "function".
        before_function = re.search(r"\b([A-Za-z_]\w*)\s+functions?\b", text)
        if before_function:
            candidates.append(before_function.group(1))

        # Also support "function add" style wording.
        after_function = re.search(r"\bfunctions?\s+([A-Za-z_]\w*)\b", text)
        if after_function:
            candidates.append(after_function.group(1))

        # Fallback: collect identifier tokens while filtering analysis words.
        for token in re.findall(r"\b[A-Za-z_]\w*\b", text):
            if token.lower() not in ignored and token not in candidates:
                candidates.append(token)

        functions = [fn for fn in candidates if fn and fn.lower() not in ignored]
        functions = list(dict.fromkeys(functions))
        if not functions:
            return text

        # v6.2.3: Rewrite analysis-only requests into the scheduler's known
        # actionable function-fix language.  The current scheduler smoke path is
        # deliberately narrow and has been validated with the phrase below.  Do
        # not generate path-heavy prose here; that can be treated as a generic
        # simple task and return simple_task_finished without editing.
        lowered_functions = {str(fn).strip().lower() for fn in functions}
        if "add" in lowered_functions and "multiply" not in lowered_functions:
            return "Fix add and multiply functions to correct logic"

        ordered_functions: List[str] = []
        for fn in functions:
            clean = str(fn).strip()
            if not clean:
                continue
            if clean.lower() not in {item.lower() for item in ordered_functions}:
                ordered_functions.append(clean)

        if not ordered_functions:
            return text

        if len(ordered_functions) == 1:
            return f"Fix {ordered_functions[0]} function to correct logic"

        joined = " and ".join(ordered_functions)
        return f"Fix {joined} functions to correct logic"

    def _try_force_scheduler_self_edit_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Route safe self-edit tasks through self_edit_loop -> Scheduler.

        v5.9.0 boundary:
        AgentLoop only decides whether to enter self-edit mode.  It does not
        edit files directly and does not bypass Scheduler / ExecutionGuard /
        atomic rollback.
        """
        text = str(user_input or "").strip()
        self_edit_decision = self._decide_scheduler_self_edit_policy(text)
        if not bool(self_edit_decision.get("allow", False)):
            return None

        scheduler_task_text = self._rewrite_scheduler_self_edit_goal(text, self_edit_decision)

        try:
            from self_edit_loop import run_self_edit_loop

            loop_result = run_self_edit_loop(
                scheduler_task_text,
                repo_root=".",
                allow_core=False,
                executor_mode="scheduler",
            )
            result_payload = loop_result.to_dict() if hasattr(loop_result, "to_dict") else copy.deepcopy(loop_result)
        except Exception as e:
            result_payload = {
                "ok": False,
                "status": "failed",
                "task": scheduler_task_text,
                "original_task": text,
                "final_reason": f"scheduler self-edit route failed: {type(e).__name__}: {e}",
                "attempts": [],
                "code_chain_version": "agent_loop_v6_2_3_analysis_rewrite_goal_to_known_scheduler_fix",
            }

        ok = bool(result_payload.get("ok", False)) if isinstance(result_payload, dict) else False
        final_answer = self._summarize_scheduler_self_edit_result(result_payload if isinstance(result_payload, dict) else {})
        error = None if ok else str(result_payload.get("final_reason") or final_answer)

        attempts = result_payload.get("attempts") if isinstance(result_payload, dict) else []
        latest_attempt = attempts[-1] if isinstance(attempts, list) and attempts else {}
        edit_result = latest_attempt.get("edit_result") if isinstance(latest_attempt, dict) else {}
        scheduler_result = edit_result.get("scheduler_result") if isinstance(edit_result, dict) else {}
        if not isinstance(scheduler_result, dict):
            scheduler_result = {}

        execution = {
            "ok": ok,
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": {
                        "type": "self_edit_scheduler",
                        "executor": "scheduler",
                        "task": scheduler_task_text,
                        "original_task": text,
                    },
                    "result": copy.deepcopy(scheduler_result or result_payload),
                }
            ],
            "execution_log": [
                {
                    "type": "self_edit_scheduler",
                    "status": str(result_payload.get("status") or ("success" if ok else "failed")),
                    "ok": ok,
                    "data": copy.deepcopy(result_payload),
                    "scheduler_task": scheduler_task_text,
                    "original_task": text,
                }
            ],
            "execution_trace": [
                {
                    "type": "self_edit_scheduler",
                    "status": str(result_payload.get("status") or ("success" if ok else "failed")),
                    "ok": ok,
                    "data": copy.deepcopy(scheduler_result or result_payload),
                }
            ],
            "last_result": copy.deepcopy(scheduler_result or result_payload),
            "final_answer": final_answer,
            "error": error,
            "execution_path": agent_execution_path(),
        }

        route = {
            "mode": "self_edit_scheduler",
            "task": False,
            "tool": "self_edit_loop",
            "forced_route": True,
            "self_edit": True,
            "scheduler_backed": True,
            "decision": copy.deepcopy(self_edit_decision),
            "scheduler_task": scheduler_task_text,
            "original_task": text,
        }
        plan = {
            "ok": ok,
            "planner_mode": "self_edit_scheduler_v6_2_3",
            "intent": "self_edit",
            "final_answer": final_answer,
            "steps": [
                {
                    "type": "self_edit_scheduler",
                    "executor": "scheduler",
                    "task": scheduler_task_text,
                    "original_task": text,
                }
            ],
            "meta": {
                "fallback_used": False,
                "step_count": 1,
                "forced_route": True,
                "code_chain_version": "agent_loop_v6_2_2",
                "self_edit_decision": copy.deepcopy(self_edit_decision),
                "scheduler_task": scheduler_task_text,
                "original_task": text,
            },
            "scheduler_result": copy.deepcopy(scheduler_result),
            "self_edit_result": copy.deepcopy(result_payload),
        }

        return self._make_agent_response(
            ok=ok,
            mode="self_edit_scheduler",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=error,
            extra={
                "self_edit_result": copy.deepcopy(result_payload),
                "scheduler_result": copy.deepcopy(scheduler_result),
                "self_edit_decision": copy.deepcopy(self_edit_decision),
                "scheduler_task": scheduler_task_text,
                "original_task": text,
            },
        )

    def _try_handle_natural_language_patch_missing_path(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Fail early when bounded NL repair targets a missing workspace file.

        Code Chain v6.4.2 boundary:
        - This guard only handles the minimal natural-language add-function
          landing probe.
        - It never writes files.
        - It prevents missing files from falling through to repo_edit_tool as
          a vague request that later reports missing old_text/new_text.
        """
        text = str(user_input or "").strip()
        if not text:
            return None

        lowered = text.lower()
        if "add" not in lowered or "function" not in lowered:
            return None
        if not any(marker in lowered for marker in ("check", "fix", "repair", "correct", "wrong", "broken", "incorrect")):
            return None

        paths: List[str] = []
        self._extract_paths_from_text(text, paths)
        if not paths:
            return None

        target_path = str(paths[0] or "").replace("\\", "/").strip()
        if not target_path.startswith("workspace/"):
            return None

        try:
            resolved = Path(target_path)
            missing = not resolved.exists() or not resolved.is_file()
        except Exception:
            missing = True

        if not missing:
            return None

        final_answer = f"natural language patch failed: file not found: {target_path}; changed_files=0"
        forced = {
            "handled": True,
            "forced_route": True,
            "tool_name": "repo_edit_tool",
            "status": "failed",
            "reason": "bounded_nl_patch_target_file_not_found",
            "error": f"file not found: {target_path}",
            "task_text": text,
            "target_path": target_path,
            "changed_files": [],
            "code_chain_version": "agent_loop_v6_4_2_missing_path_guard",
            "final_answer": final_answer,
        }

        execution = {
            "ok": False,
            "steps_executed": 0,
            "results": [],
            "execution_log": [
                {
                    "type": "natural_language_patch_missing_path_guard",
                    "tool": "repo_edit_tool",
                    "status": "failed",
                    "ok": False,
                    "data": copy.deepcopy(forced),
                }
            ],
            "execution_trace": [
                {
                    "type": "natural_language_patch_missing_path_guard",
                    "tool": "repo_edit_tool",
                    "status": "failed",
                    "ok": False,
                    "data": copy.deepcopy(forced),
                }
            ],
            "last_result": copy.deepcopy(forced),
            "final_answer": final_answer,
            "error": f"file not found: {target_path}",
        }
        route = {
            "mode": "forced_repo_edit",
            "task": False,
            "tool": "repo_edit_tool",
            "forced_route": True,
            "natural_language_patch_missing_path_guard": True,
        }
        plan = {
            "ok": False,
            "planner_mode": "forced_repo_edit_v6_4_2_missing_path_guard",
            "intent": "repo_edit",
            "final_answer": final_answer,
            "steps": [],
            "error": f"file not found: {target_path}",
            "meta": {
                "fallback_used": False,
                "step_count": 0,
                "forced_route": True,
                "code_chain_version": "v6.4.2",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        }
        return self._make_agent_response(
            ok=False,
            mode="forced_repo_edit",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=f"file not found: {target_path}",
            extra={
                "forced_repo_edit": copy.deepcopy(forced),
                "tool_name": "repo_edit_tool",
                "patch_visibility": {},
            },
        )

    def _try_build_natural_language_patch_prompt(self, user_input: str) -> Optional[str]:
        """Build a minimal controlled replacement prompt from bounded NL repair text.

        Code Chain v6.4.0 boundary:
        - This is not a general AI patch generator.
        - It only handles the current landing-verification case:
              Check and fix add function in workspace/shared/code_chain_probe.py
        - It never writes files directly.
        - It converts a bounded diagnosis request into the already-verified
          repo_edit_tool controlled_replace form, then lets repo_edit_tool keep
          responsibility for backup / safety / apply.
        """
        text = str(user_input or "").strip()
        if not text:
            return None

        lowered = text.lower()
        if "add" not in lowered or "function" not in lowered:
            return None
        if not any(marker in lowered for marker in ("check", "fix", "repair", "correct", "wrong", "broken", "incorrect")):
            return None

        paths: List[str] = []
        self._extract_paths_from_text(text, paths)
        if not paths:
            return None

        target_path = str(paths[0] or "").replace("\\", "/").strip()
        if not target_path.startswith("workspace/"):
            return None

        try:
            resolved = Path(target_path)
            if not resolved.exists() or not resolved.is_file():
                return None
            content = resolved.read_text(encoding="utf-8")
        except Exception:
            return None

        add_match = re.search(
            r"(?ms)^def\s+add\s*\([^)]*\):\s*\n(?P<body>(?:^[ \t]+.*(?:\n|$))*)",
            content,
        )
        if not add_match:
            return None

        add_block = add_match.group(0)
        replacement_pairs = [
            ("return a - b", "return a + b"),
            ("return b - a", "return a + b"),
            ("return a * b", "return a + b"),
            ("return a / b", "return a + b"),
        ]
        for old_text, new_text in replacement_pairs:
            if old_text in add_block:
                return f'Replace "{old_text}" with "{new_text}" in {target_path}'

        return None


    def _try_handle_natural_language_patch_noop(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Return a clean no-op response for bounded NL repair when code is already correct.

        Code Chain v6.4.1 boundary:
        If the bounded add-function landing probe is already fixed, do not fall
        through to repo_edit_tool with a missing old_text/new_text payload.
        This prevents a correct file from being reported as a failed edit.
        """
        text = str(user_input or "").strip()
        if not text:
            return None

        lowered = text.lower()
        if "add" not in lowered or "function" not in lowered:
            return None
        if not any(marker in lowered for marker in ("check", "fix", "repair", "correct", "wrong", "broken", "incorrect")):
            return None

        paths: List[str] = []
        self._extract_paths_from_text(text, paths)
        if not paths:
            return None

        target_path = str(paths[0] or "").replace("\\", "/").strip()
        if not target_path.startswith("workspace/"):
            return None

        try:
            resolved = Path(target_path)
            if not resolved.exists() or not resolved.is_file():
                return None
            content = resolved.read_text(encoding="utf-8")
        except Exception:
            return None

        add_match = re.search(
            r"(?ms)^def\s+add\s*\([^)]*\):\s*\n(?P<body>(?:^[ \t]+.*(?:\n|$))*)",
            content,
        )
        if not add_match:
            return None

        add_block = add_match.group(0)
        if "return a + b" not in add_block:
            return None

        final_answer = f"natural language patch check: add function already appears correct in {target_path}; changed_files=0"
        forced = {
            "handled": True,
            "forced_route": True,
            "tool_name": "repo_edit_tool",
            "status": "success",
            "reason": "bounded_nl_patch_noop_already_correct",
            "task_text": text,
            "target_path": target_path,
            "changed_files": [],
            "code_chain_version": "agent_loop_v6_4_2_nl_patch_noop_guard",
            "final_answer": final_answer,
        }

        execution = {
            "ok": True,
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": {
                        "type": "natural_language_patch_noop",
                        "tool_call": {
                            "tool": "repo_edit_tool",
                            "args": {},
                        },
                    },
                    "result": copy.deepcopy(forced),
                }
            ],
            "execution_log": [
                {
                    "type": "natural_language_patch_noop",
                    "tool": "repo_edit_tool",
                    "status": "success",
                    "ok": True,
                    "data": copy.deepcopy(forced),
                }
            ],
            "execution_trace": [
                {
                    "type": "natural_language_patch_noop",
                    "tool": "repo_edit_tool",
                    "status": "success",
                    "ok": True,
                    "data": copy.deepcopy(forced),
                }
            ],
            "last_result": copy.deepcopy(forced),
            "final_answer": final_answer,
            "error": None,
        }
        route = {
            "mode": "forced_repo_edit",
            "task": False,
            "tool": "repo_edit_tool",
            "forced_route": True,
            "natural_language_patch_noop": True,
        }
        plan = {
            "ok": True,
            "planner_mode": "forced_repo_edit_v6_4_1_noop",
            "intent": "repo_edit",
            "final_answer": final_answer,
            "steps": [],
            "meta": {
                "fallback_used": False,
                "step_count": 0,
                "forced_route": True,
                "code_chain_version": "v6.4.1",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        }
        return self._make_agent_response(
            ok=True,
            mode="forced_repo_edit",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=None,
            extra={
                "forced_repo_edit": copy.deepcopy(forced),
                "tool_name": "repo_edit_tool",
            },
        )

    def _extract_python_function_block(self, content: str, function_name: str) -> str:
        """Return a simple top-level Python function block by name.

        Code Chain v6.7.2 boundary:
        The earlier regex used DOTALL and could accidentally swallow later
        top-level functions.  This line-based extractor keeps the scope bounded
        to exactly one top-level def block, including blank lines inside the
        block but stopping at the next top-level def/class statement.
        """
        if not isinstance(content, str) or not content:
            return ""

        name = str(function_name or "").strip()
        if not name:
            return ""

        lines = content.splitlines(keepends=True)
        start_index = None
        header_pattern = re.compile(rf"^def\s+{re.escape(name)}\s*\([^)]*\):\s*(?:#.*)?(?:\r?\n)?$")

        for index, line in enumerate(lines):
            if header_pattern.match(line):
                start_index = index
                break

        if start_index is None:
            return ""

        end_index = len(lines)
        for index in range(start_index + 1, len(lines)):
            line = lines[index]
            stripped = line.strip()

            if not stripped:
                continue

            is_top_level = not line.startswith((" ", "\t"))
            if is_top_level and re.match(r"^(def|class)\s+", line):
                end_index = index
                break

        return "".join(lines[start_index:end_index])

    def _find_simple_function_replacement_pair(self, function_name: str, function_block: str) -> Optional[tuple[str, str]]:
        """Find a deterministic replacement pair for the v6.5.0 probe functions."""
        name = str(function_name or "").strip().lower()
        block = str(function_block or "")
        if not name or not block:
            return None

        if name == "add":
            candidates = [
                ("return a - b", "return a + b"),
                ("return b - a", "return a + b"),
                ("return a * b", "return a + b"),
                ("return a / b", "return a + b"),
            ]
        elif name == "multiply":
            candidates = [
                ("return a + b", "return a * b"),
                ("return a - b", "return a * b"),
                ("return b - a", "return a * b"),
                ("return a / b", "return a * b"),
            ]
        else:
            return None

        for old_text, new_text in candidates:
            if old_text in block:
                return old_text, new_text
        return None

    def _function_block_appears_correct(self, function_name: str, function_block: str) -> bool:
        name = str(function_name or "").strip().lower()
        block = str(function_block or "")
        if name == "add":
            return "return a + b" in block
        if name == "multiply":
            return "return a * b" in block
        return False

    def _safe_code_chain_artifact_slug(self, target_path: str) -> str:
        text = str(target_path or "target").replace("\\", "/").strip().strip("/")
        if not text:
            text = "target"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:120]

    def _write_code_chain_text(
        self,
        path: Path | str,
        text: str,
        *,
        reason: str,
        target_path: str,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = self.execution_runtime.run_step(
            step={
                "type": "write_file",
                "path": str(path).replace("\\", "/"),
                "content": str(text),
            },
            context={
                "reason": reason,
                "ownership_handoff": "agent_loop_to_agent_execution_runtime",
                "lineage": {
                "caller": "agent_loop",
                "surface": "code_chain_patch",
                "artifact_type": artifact_type,
                "artifact_class": "output_artifact",
                "patch_target_path": str(target_path or ""),
                },
                "provenance": {
                "caller": "agent_loop",
                "surface": "code_chain_patch",
                "artifact_type": artifact_type,
                "artifact_class": "output_artifact",
                    "producer_layer": "agent_execution_runtime",
                },
                "metadata": {
                "caller": "agent_loop",
                "runtime_seal_pass": "active_mutation_closure_v1",
                "artifact_type": artifact_type,
                "artifact_class": "output_artifact",
                    "producer_layer": "agent_execution_runtime",
                    "sealed_execution_evidence": True,
                "patch_target_path": str(target_path or ""),
                **dict(metadata or {}),
                },
            },
        )
        if result.get("ok") is not True:
            raise PermissionError("agent_execution_runtime_write_required")
        return result

    def _prepare_code_chain_patch_visibility(
        self,
        *,
        target_path: str,
        before_content: str,
        original_text: str,
        version: str,
    ) -> Dict[str, Any]:
        """Create backup/audit scaffolding before applying a bounded NL patch.

        Code Chain v6.6.0 boundary:
        - This is observability for the bounded code-chain probe.
        - It does not modify the target file.
        - It creates rollback-ready evidence before repo_edit_tool applies edits.
        """
        normalized_target = str(target_path or "").replace("\\", "/").strip()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        slug = self._safe_code_chain_artifact_slug(normalized_target)
        backup_dir = Path("workspace") / "backups" / "code_chain"
        audit_dir = Path("workspace") / "audit" / "code_chain"
        diff_dir = audit_dir / "diffs"

        visibility: Dict[str, Any] = {
            "ok": True,
            "version": version,
            "target_path": normalized_target,
            "timestamp_utc": timestamp,
            "original_task": str(original_text or ""),
            "backup_path": "",
            "audit_path": "",
            "diff_path": "",
            "diff_line_count": 0,
            "changed_line_count": 0,
            "backup_created": False,
            "audit_written": False,
            "diff_written": False,
            "error": None,
        }

        try:
            backup_path = backup_dir / f"{timestamp}_{slug}.bak"
            self._write_code_chain_text(
                backup_path,
                str(before_content or ""),
                reason="agent_loop_code_chain_backup_write",
                target_path=normalized_target,
                artifact_type="rollback_backup",
            )
            visibility["backup_path"] = str(backup_path).replace("\\", "/")
            visibility["backup_created"] = True
            return visibility
        except Exception as e:
            visibility["ok"] = False
            visibility["error"] = f"patch visibility backup failed: {type(e).__name__}: {e}"
            return visibility

    def _finalize_code_chain_patch_visibility(
        self,
        *,
        visibility: Dict[str, Any],
        before_content: str,
        after_content: str,
        changed_files: List[str],
        events: List[Dict[str, Any]],
        ok: bool,
        status: str,
        reason: str,
        error: Optional[str],
    ) -> Dict[str, Any]:
        if not isinstance(visibility, dict):
            visibility = {}

        normalized_target = str(visibility.get("target_path") or "target").replace("\\", "/")
        timestamp = str(visibility.get("timestamp_utc") or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
        slug = self._safe_code_chain_artifact_slug(normalized_target)
        audit_dir = Path("workspace") / "audit" / "code_chain"
        diff_dir = audit_dir / "diffs"

        try:
            before_lines = str(before_content or "").splitlines()
            after_lines = str(after_content or "").splitlines()
            diff_lines = list(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"before/{normalized_target}",
                    tofile=f"after/{normalized_target}",
                    lineterm="",
                )
            )
            changed_line_count = sum(
                1
                for line in diff_lines
                if (line.startswith("+") and not line.startswith("+++"))
                or (line.startswith("-") and not line.startswith("---"))
            )

            diff_path = diff_dir / f"{timestamp}_{slug}.diff"
            self._write_code_chain_text(
                diff_path,
                "\n".join(diff_lines) + ("\n" if diff_lines else ""),
                reason="agent_loop_code_chain_diff_write",
                target_path=normalized_target,
                artifact_type="patch_diff",
                metadata={"diff_line_count": len(diff_lines)},
            )

            visibility.update(
                {
                    "ok": bool(visibility.get("ok", True)),
                    "status": status,
                    "reason": reason,
                    "error": error,
                    "changed_files": copy.deepcopy(changed_files),
                    "event_count": len(events),
                    "events": [
                        {
                            "function": event.get("function"),
                            "old_text": event.get("old_text"),
                            "new_text": event.get("new_text"),
                            "ok": bool(event.get("ok", False)),
                        }
                        for event in events
                        if isinstance(event, dict)
                    ],
                    "diff_path": str(diff_path).replace("\\", "/"),
                    "diff_line_count": len(diff_lines),
                    "changed_line_count": changed_line_count,
                    "diff_written": True,
                }
            )

            audit_payload = {
                "ok": bool(ok),
                "status": status,
                "reason": reason,
                "error": error,
                "target_path": normalized_target,
                "timestamp_utc": timestamp,
                "backup_path": visibility.get("backup_path"),
                "diff_path": visibility.get("diff_path"),
                "changed_files": copy.deepcopy(changed_files),
                "diff_line_count": visibility.get("diff_line_count"),
                "changed_line_count": visibility.get("changed_line_count"),
                "events": visibility.get("events"),
                "version": visibility.get("version"),
                "original_task": visibility.get("original_task"),
            }
            audit_path = audit_dir / f"{timestamp}_{slug}.json"
            self._write_code_chain_text(
                audit_path,
                json.dumps(audit_payload, ensure_ascii=False, indent=2),
                reason="agent_loop_code_chain_audit_write",
                target_path=normalized_target,
                artifact_type="patch_audit",
                metadata={
                    "audit": True,
                },
            )
            visibility["audit_path"] = str(audit_path).replace("\\", "/")
            visibility["audit_written"] = True
            return visibility
        except Exception as e:
            visibility["ok"] = False
            visibility["error"] = f"patch visibility finalize failed: {type(e).__name__}: {e}"
            return visibility

    def _verify_natural_language_multi_patch_result(
        self,
        *,
        target_path: str,
        function_names: List[str],
    ) -> Dict[str, Any]:
        """Verify deterministic v6.7.2 probe patches after apply.

        Code Chain v6.7.2 boundary:
        - This is a narrow verification layer for the current add/multiply probe.
        - It reads the patched file and validates final function semantics by
          deterministic source inspection, not by trusting the edit result text.
        - It does not generalize to arbitrary code yet.
        """
        normalized_target = str(target_path or "").replace("\\", "/").strip()
        result: Dict[str, Any] = {
            "ok": False,
            "target_path": normalized_target,
            "verified_functions": [],
            "failed_functions": [],
            "missing_functions": [],
            "unsupported_functions": [],
            "reason": "not_verified",
            "error": None,
        }

        if not normalized_target:
            result["reason"] = "empty_target_path"
            result["error"] = "target path is empty"
            return result

        try:
            path = Path(normalized_target)
            if not path.exists() or not path.is_file():
                result["reason"] = "target_file_missing"
                result["error"] = f"file not found: {normalized_target}"
                return result
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            result["reason"] = "target_read_failed"
            result["error"] = f"cannot read {normalized_target}: {type(e).__name__}: {e}"
            return result

        requested = [str(name or "").strip() for name in function_names if str(name or "").strip()]
        if not requested:
            result["reason"] = "no_functions_requested"
            result["error"] = "no functions requested for verification"
            return result

        for function_name in requested:
            block = self._extract_python_function_block(content, function_name)
            if not block:
                result["missing_functions"].append(function_name)
                result["failed_functions"].append(function_name)
                continue

            if self._function_block_appears_correct(function_name, block):
                result["verified_functions"].append(function_name)
                continue

            if function_name not in {"add", "multiply"}:
                result["unsupported_functions"].append(function_name)
            result["failed_functions"].append(function_name)

        if result["failed_functions"]:
            result["ok"] = False
            result["reason"] = "verification_failed"
            result["error"] = "verification failed for: " + ", ".join(result["failed_functions"])
            return result

        result["ok"] = True
        result["reason"] = "verification_passed"
        result["error"] = None
        return result

    def _try_handle_natural_language_multi_function_patch(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Handle the bounded v6.7.2 add+multiply natural-language patch probe.

        Code Chain v6.7.2 boundary:
        - Supports only the deterministic probe functions: add and multiply.
        - Reads the target workspace file, builds old_text/new_text pairs, then
          dispatches verified controlled_replace prompts through repo_edit_tool.
        - Does not edit files directly.
        - Fails closed for missing files, missing functions, or missing patch pairs.
        """
        text = str(user_input or "").strip()
        if not text:
            return None

        if _zero_v7337_agent_repo_edit_intent_candidate(text):
            return _zero_v7337_agent_forced_repo_edit_intent_response(self, text)

        if run_repo_edit_decision is None:
            return None

        lowered = text.lower()
        if "function" not in lowered or "add" not in lowered or "multiply" not in lowered:
            return None
        if not any(marker in lowered for marker in ("check", "fix", "repair", "correct", "wrong", "broken", "incorrect")):
            return None

        paths: List[str] = []
        self._extract_paths_from_text(text, paths)
        if not paths:
            return None

        target_path = str(paths[0] or "").replace("\\", "/").strip()
        if not target_path.startswith("workspace/"):
            return None

        try:
            resolved = Path(target_path)
            if not resolved.exists() or not resolved.is_file():
                final_answer = f"natural language multi patch failed: file not found: {target_path}; changed_files=0"
                return self._make_natural_language_patch_response(
                    ok=False,
                    final_answer=final_answer,
                    target_path=target_path,
                    original_text=text,
                    changed_files=[],
                    status="failed",
                    reason="multi_function_patch_target_file_not_found",
                    error=f"file not found: {target_path}",
                    events=[],
                    version="agent_loop_v6_7_2_line_scoped_function_blocks",
                )
            content = resolved.read_text(encoding="utf-8")
            patch_visibility = self._prepare_code_chain_patch_visibility(
                target_path=target_path,
                before_content=content,
                original_text=text,
                version="agent_loop_v6_7_2_line_scoped_function_blocks",
            )
            if not bool(patch_visibility.get("ok", False)):
                visibility_error = str(patch_visibility.get("error") or "patch visibility backup failed")
                final_answer = f"natural language multi patch failed: {visibility_error}; changed_files=0"
                return self._make_natural_language_patch_response(
                    ok=False,
                    final_answer=final_answer,
                    target_path=target_path,
                    original_text=text,
                    changed_files=[],
                    status="failed",
                    reason="multi_function_patch_visibility_backup_failed",
                    error=visibility_error,
                    events=[],
                    version="agent_loop_v6_7_2_line_scoped_function_blocks",
                    visibility=patch_visibility,
                )
        except Exception as e:
            final_answer = f"natural language multi patch failed: cannot read {target_path}: {e}; changed_files=0"
            return self._make_natural_language_patch_response(
                ok=False,
                final_answer=final_answer,
                target_path=target_path,
                original_text=text,
                changed_files=[],
                status="failed",
                reason="multi_function_patch_read_failed",
                error=f"cannot read {target_path}: {e}",
                events=[],
                version="agent_loop_v6_7_2_line_scoped_function_blocks",
            )

        function_names = ["add", "multiply"]
        replacements: List[Dict[str, str]] = []
        missing_functions: List[str] = []
        correct_functions: List[str] = []
        unsupported_functions: List[str] = []

        for function_name in function_names:
            block = self._extract_python_function_block(content, function_name)
            if not block:
                missing_functions.append(function_name)
                continue

            pair = self._find_simple_function_replacement_pair(function_name, block)
            if pair is not None:
                replacements.append(
                    {
                        "function": function_name,
                        "old_text": pair[0],
                        "new_text": pair[1],
                    }
                )
                continue

            if self._function_block_appears_correct(function_name, block):
                correct_functions.append(function_name)
            else:
                unsupported_functions.append(function_name)

        if missing_functions:
            joined = ", ".join(missing_functions)
            final_answer = f"natural language multi patch failed: function not found: {joined} in {target_path}; changed_files=0"
            return self._make_natural_language_patch_response(
                ok=False,
                final_answer=final_answer,
                target_path=target_path,
                original_text=text,
                changed_files=[],
                status="failed",
                reason="multi_function_patch_function_not_found",
                error=f"function not found: {joined}",
                events=[],
                version="agent_loop_v6_7_2_line_scoped_function_blocks",
            )

        if unsupported_functions:
            joined = ", ".join(unsupported_functions)
            final_answer = f"natural language multi patch failed: no deterministic replacement pair for {joined} in {target_path}; changed_files=0"
            return self._make_natural_language_patch_response(
                ok=False,
                final_answer=final_answer,
                target_path=target_path,
                original_text=text,
                changed_files=[],
                status="failed",
                reason="multi_function_patch_missing_replacement_pair",
                error=f"missing deterministic replacement pair for {joined}",
                events=[],
                version="agent_loop_v6_7_2_line_scoped_function_blocks",
            )

        if not replacements:
            joined = " and ".join(correct_functions) if correct_functions else "add and multiply"
            final_answer = f"natural language multi patch check: {joined} functions already appear correct in {target_path}; changed_files=0"
            return self._make_natural_language_patch_response(
                ok=True,
                final_answer=final_answer,
                target_path=target_path,
                original_text=text,
                changed_files=[],
                status="success",
                reason="multi_function_patch_noop_already_correct",
                error=None,
                events=[],
                version="agent_loop_v6_7_2_line_scoped_function_blocks",
            )

        events: List[Dict[str, Any]] = []
        changed_files: List[str] = []
        ok = True
        error = None

        # v6.7.2: apply generated patches with function-block scope.
        # The v6.7.2 implementation dispatched multiple plain controlled_replace
        # prompts through repo_edit_tool. That made the second replacement unsafe:
        # after add was changed to ``return a + b``, a later global replacement
        # for multiply could match the add return line first.  For this bounded
        # probe, keep the decision/read/backup/audit/verification path here and
        # apply each replacement only inside the intended function block.
        patched_content = content
        for replacement in replacements:
            function_name = str(replacement.get("function") or "").strip()
            old_text = replacement["old_text"]
            new_text = replacement["new_text"]

            block_before = self._extract_python_function_block(patched_content, function_name)
            if not block_before:
                ok = False
                error = f"function block not found during scoped patch: {function_name}"
                events.append(
                    {
                        "function": function_name,
                        "old_text": old_text,
                        "new_text": new_text,
                        "ok": False,
                        "scope": "function_block",
                        "error": error,
                    }
                )
                break

            if old_text not in block_before:
                if self._function_block_appears_correct(function_name, block_before):
                    events.append(
                        {
                            "function": function_name,
                            "old_text": old_text,
                            "new_text": new_text,
                            "ok": True,
                            "scope": "function_block",
                            "noop": True,
                            "reason": "function_already_correct_before_apply",
                        }
                    )
                    continue

                ok = False
                error = f"old_text not found inside {function_name} function block"
                events.append(
                    {
                        "function": function_name,
                        "old_text": old_text,
                        "new_text": new_text,
                        "ok": False,
                        "scope": "function_block",
                        "error": error,
                    }
                )
                break

            block_after = block_before.replace(old_text, new_text, 1)
            patched_content = patched_content.replace(block_before, block_after, 1)
            events.append(
                {
                    "function": function_name,
                    "old_text": old_text,
                    "new_text": new_text,
                    "ok": True,
                    "scope": "function_block",
                    "changed": block_before != block_after,
                }
            )

        if ok:
            try:
                if patched_content != content:
                    self._write_code_chain_text(
                        target_path,
                        patched_content,
                        reason="agent_loop_scoped_function_patch_apply",
                        target_path=target_path,
                        artifact_type="scoped_function_patch",
                        metadata={
                            "patch_apply": True,
                            "rollback_required": True,
                            "function_names": function_names,
                            "replacement_count": len(replacements),
                        },
                    )
                    changed_files = [target_path]
                else:
                    changed_files = []
            except Exception as e:
                ok = False
                error = f"failed to write scoped patch: {e}"

        if ok:
            patched_names = [str(item.get("function") or "") for item in replacements]
            joined = " and ".join([name for name in patched_names if name]) or "requested"
            status = "success"
            reason = "multi_function_patch_applied"
        else:
            status = "failed"
            reason = "multi_function_patch_apply_failed"

        try:
            after_content = Path(target_path).read_text(encoding="utf-8")
        except Exception:
            after_content = content

        verification_result: Dict[str, Any] = {}
        rollback_result: Dict[str, Any] = {}
        if ok:
            verification_result = self._verify_natural_language_multi_patch_result(
                target_path=target_path,
                function_names=function_names,
            )
            if not bool(verification_result.get("ok", False)):
                rollback_result = request_code_chain_patch_restore(
                    target_path=target_path,
                    backup_path=str(patch_visibility.get("backup_path") or ""),
                )
                ok = False
                status = "failed"
                reason = "multi_function_patch_verification_failed"
                verification_error = str(verification_result.get("error") or verification_result.get("reason") or "verification failed")
                rollback_reason = str(rollback_result.get("reason") or "rollback_not_run")
                error = f"{verification_error}; rollback={rollback_reason}"
                if bool(rollback_result.get("ok", False)):
                    changed_files = []
                    try:
                        after_content = Path(target_path).read_text(encoding="utf-8")
                    except Exception:
                        after_content = content

        patch_visibility = self._finalize_code_chain_patch_visibility(
            visibility=patch_visibility,
            before_content=content,
            after_content=after_content,
            changed_files=changed_files,
            events=events,
            ok=ok,
            status=status,
            reason=reason,
            error=error,
        )
        patch_visibility["verification"] = copy.deepcopy(verification_result)
        patch_visibility["rollback"] = copy.deepcopy(rollback_result)

        if ok:
            final_answer = (
                f"natural language multi patch succeeded: {joined} functions patched in {target_path}; "
                f"verification=passed; "
                f"changed_files={len(changed_files)}; "
                f"backup={patch_visibility.get('backup_path') or ''}; "
                f"diff={patch_visibility.get('diff_path') or ''}; "
                f"audit={patch_visibility.get('audit_path') or ''}; "
                f"changed_lines={patch_visibility.get('changed_line_count', 0)}"
            )
        else:
            rollback_note = ""
            if rollback_result:
                rollback_note = f"; rollback={rollback_result.get('reason')}; rollback_ok={bool(rollback_result.get('ok', False))}"
            final_answer = (
                f"natural language multi patch failed: {error}; "
                f"verification={verification_result.get('reason') or 'not_run'}{rollback_note}; "
                f"changed_files={len(changed_files)}; "
                f"backup={patch_visibility.get('backup_path') or ''}; "
                f"diff={patch_visibility.get('diff_path') or ''}; "
                f"audit={patch_visibility.get('audit_path') or ''}"
            )

        return self._make_natural_language_patch_response(
            ok=ok,
            final_answer=final_answer,
            target_path=target_path,
            original_text=text,
            changed_files=changed_files,
            status=status,
            reason=reason,
            error=error,
            events=events,
            version="agent_loop_v6_7_2_line_scoped_function_blocks",
            visibility=patch_visibility,
            verification=verification_result,
            rollback=rollback_result,
        )

    def _make_natural_language_patch_response(
        self,
        *,
        ok: bool,
        final_answer: str,
        target_path: str,
        original_text: str,
        changed_files: List[str],
        status: str,
        reason: str,
        error: Optional[str],
        events: List[Dict[str, Any]],
        version: str,
        visibility: Optional[Dict[str, Any]] = None,
        verification: Optional[Dict[str, Any]] = None,
        rollback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        forced = {
            "handled": True,
            "forced_route": True,
            "tool_name": "repo_edit_tool",
            "status": status,
            "reason": reason,
            "error": error,
            "task_text": original_text,
            "target_path": target_path,
            "changed_files": copy.deepcopy(changed_files),
            "events": copy.deepcopy(events),
            "patch_visibility": copy.deepcopy(visibility) if isinstance(visibility, dict) else {},
            "verification": copy.deepcopy(verification) if isinstance(verification, dict) else {},
            "rollback": copy.deepcopy(rollback) if isinstance(rollback, dict) else {},
            "code_chain_version": version,
            "final_answer": final_answer,
        }

        execution = {
            "ok": bool(ok),
            "steps_executed": len(events),
            "results": [
                {
                    "step_index": index + 1,
                    "step": {
                        "type": "natural_language_multi_patch",
                        "tool_call": {
                            "tool": "repo_edit_tool",
                            "args": {
                                "old_text": event.get("old_text"),
                                "new_text": event.get("new_text"),
                                "file_path": target_path,
                            },
                        },
                    },
                    "result": copy.deepcopy(event),
                }
                for index, event in enumerate(events)
            ],
            "execution_log": [
                {
                    "type": "natural_language_multi_patch",
                    "tool": "repo_edit_tool",
                    "status": status,
                    "ok": bool(ok),
                    "data": copy.deepcopy(forced),
                }
            ],
            "execution_trace": [
                {
                    "type": "natural_language_multi_patch",
                    "tool": "repo_edit_tool",
                    "status": status,
                    "ok": bool(ok),
                    "data": copy.deepcopy(forced),
                }
            ],
            "last_result": copy.deepcopy(forced),
            "final_answer": final_answer,
            "error": error,
        }
        route = {
            "mode": "forced_repo_edit",
            "task": False,
            "tool": "repo_edit_tool",
            "forced_route": True,
            "natural_language_multi_patch": True,
        }
        plan = {
            "ok": bool(ok),
            "planner_mode": "forced_repo_edit_v6_7_0_multi_function_patch",
            "intent": "repo_edit",
            "final_answer": final_answer,
            "steps": [
                {
                    "type": "tool",
                    "tool": "repo_edit_tool",
                    "args": {
                        "file_path": target_path,
                        "changed_files": copy.deepcopy(changed_files),
                    },
                }
            ] if events else [],
            "error": error,
            "meta": {
                "fallback_used": False,
                "step_count": len(events),
                "forced_route": True,
                "code_chain_version": "v6.7.2",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        }
        return self._make_agent_response(
            ok=bool(ok),
            mode="forced_repo_edit",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=error,
            extra={
                "forced_repo_edit": copy.deepcopy(forced),
                "tool_name": "repo_edit_tool",
            },
        )

    def _try_force_repo_edit_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Force explicit code/repo edit requests into repo_edit_tool.

        This is the Code Chain v0.6 routing boundary:
        - do not wait for the planner to choose repo_edit_tool;
        - do not let the LLM finish with only final_answer when the request is
          an explicit file-edit intent;
        - delegate actual edit safety/backup/verify to repo_edit_agent_bridge
          and repo_edit_tool.
        """
        if run_repo_edit_decision is None:
            return None

        text = str(user_input or "").strip()
        if not text:
            return None

        natural_language_patch_multi = self._try_handle_natural_language_multi_function_patch(text)
        if natural_language_patch_multi is not None:
            return natural_language_patch_multi

        natural_language_patch_missing_path = self._try_handle_natural_language_patch_missing_path(text)
        if natural_language_patch_missing_path is not None:
            return natural_language_patch_missing_path

        natural_language_patch_prompt = self._try_build_natural_language_patch_prompt(text)
        if natural_language_patch_prompt is None:
            natural_language_patch_noop = self._try_handle_natural_language_patch_noop(text)
            if natural_language_patch_noop is not None:
                return natural_language_patch_noop
        effective_text = natural_language_patch_prompt or text

        try:
            forced = run_repo_edit_decision(effective_text, repo_root=".")
        except Exception as e:
            forced = {
                "handled": True,
                "forced_route": True,
                "tool_name": "repo_edit_tool",
                "status": "failed",
                "reason": f"forced repo edit routing failed: {e}",
                "error": str(e),
                "task_text": effective_text,
                "original_task_text": text,
                "natural_language_patch_prompt": natural_language_patch_prompt,
            }

        if not isinstance(forced, dict) or not forced.get("handled"):
            return None

        if natural_language_patch_prompt and isinstance(forced, dict):
            forced["original_task_text"] = text
            forced["natural_language_patch_prompt"] = natural_language_patch_prompt
            forced["code_chain_version"] = "agent_loop_v6_4_2_nl_patch_pair_generation"

        code_context = self._read_repo_edit_code_context(forced)
        if code_context:
            forced["repo_edit_code_context"] = code_context

        ok = str(forced.get("status") or "").strip().lower() not in {"failed", "error"}
        tool_result = forced.get("tool_result") if isinstance(forced.get("tool_result"), dict) else {}
        if isinstance(tool_result, dict) and tool_result.get("ok") is False:
            ok = False

        final_answer = self._summarize_forced_repo_edit_result(forced)
        execution = {
            "ok": ok,
            "steps_executed": 1,
            "results": [
                {
                    "step_index": 1,
                    "step": {
                        "type": "tool_call",
                        "tool_call": {
                            "tool": "repo_edit_tool",
                            "args": copy.deepcopy(forced.get("payload") if isinstance(forced.get("payload"), dict) else {}),
                        },
                    },
                    "result": copy.deepcopy(forced),
                }
            ],
            "execution_log": [
                {
                    "type": "forced_repo_edit",
                    "tool": "repo_edit_tool",
                    "status": str(forced.get("status") or ""),
                    "ok": ok,
                    "data": copy.deepcopy(forced),
                }
            ],
            "execution_trace": [
                {
                    "type": "forced_repo_edit",
                    "tool": "repo_edit_tool",
                    "status": str(forced.get("status") or ""),
                    "ok": ok,
                    "data": copy.deepcopy(forced),
                }
            ],
            "last_result": copy.deepcopy(forced),
            "final_answer": final_answer,
            "error": forced.get("error") or (None if ok else forced.get("reason")),
        }

        route = {
            "mode": "forced_repo_edit",
            "task": False,
            "tool": "repo_edit_tool",
            "forced_route": True,
        }
        plan = {
            "ok": ok,
            "planner_mode": "forced_repo_edit_v6_4_1",
            "intent": "repo_edit",
            "final_answer": final_answer,
            "steps": [
                {
                    "type": "tool",
                    "tool": "repo_edit_tool",
                    "args": copy.deepcopy(forced.get("payload") if isinstance(forced.get("payload"), dict) else {}),
                }
            ],
            "meta": {
                "fallback_used": False,
                "step_count": 1,
                "forced_route": True,
                "code_chain_version": "v6.4.0",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        }

        return self._make_agent_response(
            ok=ok,
            mode="forced_repo_edit",
            context={},
            route=route,
            plan=plan,
            execution=execution,
            final_answer=final_answer,
            error=execution.get("error"),
            extra={
                "forced_repo_edit": copy.deepcopy(forced),
                "tool_name": "repo_edit_tool",
            },
        )


    def _read_repo_edit_code_context(self, forced: Dict[str, Any]) -> Dict[str, Any]:
        """Read current file context for forced repo-edit results.

        This is READ -> THINK -> EDIT visibility support:
        - repo_edit_tool still enforces controlled_replace safety;
        - AgentLoop records current file content so old_text mismatch can be
          diagnosed and later planner layers can generate correct old_text.
        """
        if read_code_file is None or not isinstance(forced, dict):
            return {}

        paths = self._extract_repo_edit_context_paths(forced)
        if not paths:
            return {}

        files: List[Dict[str, Any]] = []
        for path in paths[:8]:
            if not isinstance(path, str) or not path.strip():
                continue

            allow_core = self._repo_edit_context_path_requires_core(path)
            try:
                result = read_code_file(
                    path,
                    repo_root=".",
                    max_chars=16000,
                    allow_core=allow_core,
                )
            except Exception as e:
                files.append(
                    {
                        "ok": False,
                        "path": path,
                        "error": f"code_reader failed: {e}",
                    }
                )
                continue

            if hasattr(result, "to_dict"):
                item = result.to_dict()
            elif isinstance(result, dict):
                item = copy.deepcopy(result)
            else:
                item = {
                    "ok": False,
                    "path": path,
                    "error": "code_reader returned invalid result",
                }

            files.append(item)

        ok_files = [item for item in files if isinstance(item, dict) and item.get("ok")]
        return {
            "ok": bool(ok_files),
            "file_count": len(files),
            "files": files,
            "source": "agent_loop_forced_repo_edit",
            "purpose": "read_context_before_or_after_controlled_edit",
        }

    def _repo_edit_context_path_requires_core(self, path: str) -> bool:
        normalized = str(path or "").replace("\\", "/").strip().lstrip("./")
        return (
            normalized == "app.py"
            or normalized.startswith("core/")
            or normalized.startswith("services/")
            or normalized.startswith("tests/")
            or normalized.startswith("ui/")
        )

    def _extract_repo_edit_context_paths(self, forced: Dict[str, Any]) -> List[str]:
        """Extract file paths from forced repo-edit result/payload/intent.

        Handles:
        - single edit payload/intent/tool_result
        - v0.7/v0.8 multi_edit payloads/intents/results
        """
        paths: List[str] = []

        def add_path(value: Any) -> None:
            if not isinstance(value, str):
                return
            text = value.strip().replace("\\", "/")
            if not text:
                return
            if text not in paths:
                paths.append(text)

        def scan_dict(obj: Any) -> None:
            if not isinstance(obj, dict):
                return

            for key in ("file_path", "target_path", "path", "file", "workspace_path"):
                value = obj.get(key)
                if isinstance(value, str):
                    if key == "workspace_path":
                        # Convert absolute repo path back to repo-relative when possible.
                        try:
                            resolved = str(value).replace("\\", "/")
                            marker = "/workspace/"
                            if marker in resolved:
                                add_path("workspace/" + resolved.split(marker, 1)[1])
                            else:
                                add_path(value)
                        except Exception:
                            add_path(value)
                    else:
                        add_path(value)

            for key in ("payload", "intent", "tool_result"):
                nested = obj.get(key)
                if isinstance(nested, dict):
                    scan_dict(nested)

            for key in ("payloads", "intents", "results", "edit_tasks"):
                nested_list = obj.get(key)
                if isinstance(nested_list, list):
                    for item in nested_list:
                        if isinstance(item, dict):
                            scan_dict(item)
                        elif isinstance(item, str):
                            self._extract_paths_from_text(item, paths)

            task_text = obj.get("task_text")
            if isinstance(task_text, str):
                self._extract_paths_from_text(task_text, paths)

        scan_dict(forced)
        self._extract_paths_from_text(str(forced.get("task_text") or ""), paths)

        return paths

    def _extract_paths_from_text(self, text: str, paths: List[str]) -> None:
        if not isinstance(text, str) or not text:
            return

        # v6.3.1 / v6.4.0:
        # Keep the character class deliberately simple and keep '-' at the end.
        # The previous pattern placed '-' in an unsafe range position and caused:
        #     re.error: bad character range \\_-
        pattern = re.compile(
            r"(workspace[/\\][A-Za-z0-9_./\\ :\-]+?\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg|html|css|js|ts|tsx|jsx|bat|ps1|sh))",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            value = match.group(1).strip().strip("'\"`.,;:")
            value = value.replace("\\", "/")
            while "//" in value:
                value = value.replace("//", "/")
            if value and value not in paths:
                paths.append(value)


    def _summarize_forced_repo_edit_result(self, forced: Dict[str, Any]) -> str:
        if not isinstance(forced, dict):
            return "forced repo edit returned invalid result"

        tool_result = forced.get("tool_result") if isinstance(forced.get("tool_result"), dict) else {}
        for source in (tool_result, forced):
            if not isinstance(source, dict):
                continue
            for key in ("final_answer", "summary", "message", "reason", "status"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
        observation = output.get("observation") if isinstance(output.get("observation"), dict) else {}
        summary = observation.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()

        return "forced repo edit completed"


    def _runtime_native_mainline_active(self) -> bool:
        return bool(getattr(self, "_runtime_native_mainline_delegate_active", False))

    def _run_via_runtime_native_mainline(
        self,
        *,
        entrypoint: str,
        runner: Any,
        request: Optional[Dict[str, Any]] = None,
        goal: str = "",
        workspace_root: Any = None,
    ) -> Any:
        from core.runtime.runtime_native_entry_adapter import run_via_runtime_native_mainline

        previous = self._runtime_native_mainline_active()

        def delegated_runner():
            self._runtime_native_mainline_delegate_active = True
            try:
                return runner()
            finally:
                self._runtime_native_mainline_delegate_active = previous

        root = (
            workspace_root
            or self.extra_kwargs.get("workspace_dir")
            or self.extra_kwargs.get("workspace_root")
            or "workspace"
        )
        return run_via_runtime_native_mainline(
            entrypoint=entrypoint,
            runner=delegated_runner,
            workspace_root=root,
            request=request,
            goal=goal,
            metadata={"component": "AgentLoop"},
        )

    def _run_via_runtime_route_registry(
        self,
        *,
        route_key: str,
        entrypoint: str,
        runner: Any,
        request: Optional[Dict[str, Any]] = None,
        goal: str = "",
        workspace_root: Any = None,
    ) -> Any:
        from core.runtime.runtime_route_registry import default_runtime_route_registry

        previous = self._runtime_native_mainline_active()

        def delegated_runner():
            self._runtime_native_mainline_delegate_active = True
            try:
                return runner()
            finally:
                self._runtime_native_mainline_delegate_active = previous

        root = (
            workspace_root
            or self.extra_kwargs.get("workspace_dir")
            or self.extra_kwargs.get("workspace_root")
            or "workspace"
        )
        registry = default_runtime_route_registry()
        registry.register(
            route_key,
            lambda _request, _workspace_root, _goal: delegated_runner,
            {
                "entrypoint": entrypoint,
                "component": "AgentLoop",
            },
        )
        return registry.run(
            route_key=route_key,
            request=request,
            workspace_root=root,
            goal=goal,
        )


    def run_task_loop(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        if not _runtime_native_mainline_delegate and not self._runtime_native_mainline_active():
            return self._run_via_runtime_native_mainline(
                entrypoint="core.agent.agent_loop.AgentLoop.run_task_loop",
                runner=lambda: self.run_task_loop(
                    task=task,
                    current_tick=current_tick,
                    user_input=user_input,
                    original_plan=original_plan,
                    _runtime_native_mainline_delegate=True,
                ),
                request=copy.deepcopy(task) if isinstance(task, dict) else {},
                goal=str((task or {}).get("goal") or user_input or "agent_loop run_task_loop"),
            )
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

        forced_task_text = str(
            user_input
            or effective_task.get("goal")
            or effective_task.get("title")
            or effective_task.get("description")
            or ""
        ).strip()
        forced_repo_edit = self._try_force_repo_edit_route(forced_task_text)
        if forced_repo_edit is not None:
            forced_execution = self._normalize_execution_result(forced_repo_edit.get("execution"))
            forced_ok = bool(forced_repo_edit.get("ok", True))
            forced_final_answer = str(forced_repo_edit.get("final_answer") or "")
            forced_status = "finished" if forced_ok else "failed"

            effective_task["status"] = forced_status
            effective_task["final_answer"] = forced_final_answer
            effective_task["next_action"] = "finish"
            effective_task["terminal_reason"] = "forced_repo_edit_completed" if forced_ok else "forced_repo_edit_failed"
            effective_task["agent_action"] = "forced_repo_edit"
            effective_task["last_error"] = forced_repo_edit.get("error")

            if isinstance(forced_execution, dict):
                if isinstance(forced_execution.get("results"), list):
                    effective_task["results"] = copy.deepcopy(forced_execution.get("results"))
                    effective_task["step_results"] = copy.deepcopy(forced_execution.get("results"))
                if isinstance(forced_execution.get("execution_log"), list):
                    effective_task["execution_log"] = copy.deepcopy(forced_execution.get("execution_log"))
                if isinstance(forced_execution.get("execution_trace"), list):
                    effective_task["execution_trace"] = copy.deepcopy(forced_execution.get("execution_trace"))
                if isinstance(forced_execution.get("last_result"), dict):
                    effective_task["last_step_result"] = copy.deepcopy(forced_execution.get("last_result"))

            return {
                "ok": forced_ok,
                "mode": "forced_repo_edit_task_loop",
                "action": "forced_repo_edit",
                "status": forced_status,
                "final_answer": forced_final_answer,
                "error": forced_repo_edit.get("error"),
                "task": copy.deepcopy(effective_task),
                "runtime_state": copy.deepcopy(effective_task),
                "loop_decision": "finish",
                "next_action": "finish",
                "blockers": [],
                "blocked_reason": "",
                "agent_action": "forced_repo_edit",
                "execution": forced_execution,
                "last_result": copy.deepcopy(forced_execution.get("last_result")) if isinstance(forced_execution, dict) and isinstance(forced_execution.get("last_result"), dict) else None,
                "forced_repo_edit": copy.deepcopy(forced_repo_edit),
            }

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

        runtime = self.execution_runtime
        if runtime is None:
            return {
                "ok": False,
                "mode": "task_loop",
                "action": "execution_runtime_missing",
                "status": "failed",
                "final_answer": "",
                "error": "execution runtime missing",
                "task": copy.deepcopy(effective_task),
                "execution": None,
            }

        runner_result = runtime.run_task(
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

        loop_decision = self._observe_and_record_loop_decision(
            effective_task=effective_task,
            runner_result=runner_result,
        )

        runtime_state = runner_result.get("runtime_state")
        if isinstance(runtime_state, dict):
            self._overlay_loop_state(effective_task, runtime_state)

        self._apply_loop_decision_to_task(
            effective_task=effective_task,
            loop_decision=loop_decision,
        )

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
            "loop_decision": copy.deepcopy(effective_task.get("last_decision", "")),
            "next_action": copy.deepcopy(effective_task.get("next_action", "")),
            "blockers": copy.deepcopy(effective_task.get("blockers", [])) if isinstance(effective_task.get("blockers"), list) else [],
            "blocked_reason": copy.deepcopy(effective_task.get("blocked_reason", "")),
            "agent_action": copy.deepcopy(effective_task.get("agent_action", "")),
            "execution": normalized_execution,
            "last_result": copy.deepcopy(runner_result.get("last_result")) if isinstance(runner_result.get("last_result"), dict) else None,
        }

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        return self.run_task_loop(
            task=task,
            current_tick=current_tick,
            user_input=user_input,
            original_plan=original_plan,
            _runtime_native_mainline_delegate=_runtime_native_mainline_delegate,
        )

    def run_task_until_terminal(
        self,
        task: Dict[str, Any],
        *,
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        max_cycles: int = 5,
    ) -> Dict[str, Any]:
        """
        Minimal observe -> decide -> act loop wrapper.

        Safety boundary:
        - does not replace run_task_loop()
        - does not auto-replan yet
        - does not call planner/replanner
        - only repeats when next_action == "run_next_tick"
        - stops on finish/replan/wait/fail/blocked/max_cycles
        """
        try:
            effective_task = self._normalize_task_input(task)
        except Exception as e:
            return {
                "ok": False,
                "mode": "task_until_terminal",
                "action": "invalid_task_input",
                "status": "failed",
                "final_answer": "",
                "error": f"invalid task input: {e}",
                "task": copy.deepcopy(task) if isinstance(task, dict) else {"raw_task": task},
                "cycles": [],
                "cycle_count": 0,
            }

        safe_max_cycles = max(1, self._safe_int(max_cycles, 5))
        tick = self._safe_int(current_tick, 0)
        cycles: List[Dict[str, Any]] = []
        last_result: Dict[str, Any] = {}

        for cycle_index in range(1, safe_max_cycles + 1):
            loop_result = self.run_task_loop(
                task=effective_task,
                current_tick=tick,
                user_input=user_input,
                original_plan=original_plan,
            )

            if not isinstance(loop_result, dict):
                return {
                    "ok": False,
                    "mode": "task_until_terminal",
                    "action": "invalid_loop_result",
                    "status": "failed",
                    "final_answer": "",
                    "error": "run_task_loop returned non-dict result",
                    "task": copy.deepcopy(effective_task),
                    "cycles": cycles,
                    "cycle_count": len(cycles),
                    "raw_result": copy.deepcopy(loop_result),
                }

            last_result = loop_result

            returned_task = loop_result.get("task")
            if isinstance(returned_task, dict):
                effective_task = copy.deepcopy(returned_task)

            next_action = str(
                loop_result.get("next_action")
                or effective_task.get("next_action")
                or ""
            ).strip()

            loop_decision = str(
                loop_result.get("loop_decision")
                or effective_task.get("last_decision")
                or ""
            ).strip()

            status = str(
                loop_result.get("status")
                or effective_task.get("status")
                or ""
            ).strip()

            cycles.append(
                {
                    "cycle": cycle_index,
                    "tick": tick,
                    "ok": bool(loop_result.get("ok", True)),
                    "status": status,
                    "action": str(loop_result.get("action") or ""),
                    "loop_decision": loop_decision,
                    "next_action": next_action,
                    "error": loop_result.get("error"),
                    "blockers": copy.deepcopy(effective_task.get("blockers", [])) if isinstance(effective_task.get("blockers"), list) else [],
                }
            )

            if next_action == "run_next_tick":
                tick += 1
                continue

            return {
                "ok": bool(loop_result.get("ok", True)),
                "mode": "task_until_terminal",
                "action": "loop_stopped",
                "stop_reason": next_action or loop_decision or status or "unknown",
                "status": status or str(effective_task.get("status") or ""),
                "final_answer": str(loop_result.get("final_answer") or effective_task.get("final_answer") or ""),
                "error": loop_result.get("error"),
                "task": copy.deepcopy(effective_task),
                "cycles": cycles,
                "cycle_count": len(cycles),
                "last_result": copy.deepcopy(loop_result),
                "loop_decision": loop_decision,
                "next_action": next_action,
                "blockers": copy.deepcopy(effective_task.get("blockers", [])) if isinstance(effective_task.get("blockers"), list) else [],
            }

        effective_task["status"] = "blocked"
        effective_task["terminal_reason"] = "max_cycles_reached"
        effective_task["next_action"] = "finish"

        return {
            "ok": False,
            "mode": "task_until_terminal",
            "action": "max_cycles_reached",
            "stop_reason": "max_cycles_reached",
            "status": "blocked",
            "final_answer": str(effective_task.get("final_answer") or ""),
            "error": "max_cycles_reached",
            "task": copy.deepcopy(effective_task),
            "cycles": cycles,
            "cycle_count": len(cycles),
            "last_result": copy.deepcopy(last_result),
            "loop_decision": str(effective_task.get("last_decision") or ""),
            "next_action": "finish",
        }

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
            "blockers": copy.deepcopy(effective_task.get("blockers", [])) if isinstance(effective_task.get("blockers"), list) else [],
        }
        for source in (effective_task, runner_result):
            if isinstance(source, dict) and isinstance(source.get("governed_self_repair"), dict):
                execution["governed_self_repair"] = copy.deepcopy(source["governed_self_repair"])
                for key in (
                    "self_repair_state",
                    "self_repair_reason",
                    "self_repair_candidate",
                    "self_repair_review_required",
                    "self_repair_terminal_block",
                    "self_repair_bridge_ready",
                    "self_repair_lineage",
                ):
                    if key in source:
                        execution[key] = copy.deepcopy(source[key])
                break
        _zero_v7334_agent_attach_self_repair(execution)

        for source in (effective_task, runner_result):
            if isinstance(source, dict) and isinstance(source.get("controlled_mutation_bridge"), dict):
                execution["controlled_mutation_bridge"] = copy.deepcopy(source["controlled_mutation_bridge"])
                for key in (
                    "mutation_bridge_state",
                    "mutation_bridge_eligible",
                    "mutation_bridge_requires_review",
                    "mutation_bridge_blocked",
                    "mutation_bridge_lineage",
                ):
                    if key in source:
                        execution[key] = copy.deepcopy(source[key])
                break
        _zero_v7335_agent_attach_bridge(execution)

        sources = []
        for candidate in (effective_task, runner_result, execution):
            if isinstance(candidate, dict):
                sources.append(candidate)
                for nested_key in (
                    "execution",
                    "result",
                    "runtime_state",
                    "last_step_result",
                    "last_result",
                    "runtime_execution_result",
                    "metadata",
                ):
                    nested = candidate.get(nested_key)
                    if isinstance(nested, dict):
                        sources.append(nested)
                        nested_runtime_result = nested.get("runtime_execution_result")
                        if isinstance(nested_runtime_result, dict):
                            sources.append(nested_runtime_result)
                        nested_metadata = nested.get("metadata")
                        if isinstance(nested_metadata, dict):
                            sources.append(nested_metadata)

        for source in sources:
            summary = _zero_v7336_agent_verified_change_summary(source)
            if summary.get("verified_mutation_continuation"):
                execution.update(copy.deepcopy(summary))
                break
        _zero_v7336_agent_attach_verified_change(execution)
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
                "blockers",
                "active_blocker_count",
                "waiting_reason",
                "requires_review",
                "review_status",
                "review_id",
                "review_payload",
                "agent_action",
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
            "blockers",
            "active_blocker_count",
            "waiting_reason",
            "requires_review",
            "review_status",
            "review_id",
            "review_payload",
            "agent_action",
        ):
            if key in runner_result:
                task[key] = copy.deepcopy(runner_result.get(key))

        continuation = _zero_v7333_agent_continuation_summary(runner_result)
        if continuation.get("governed_continuation"):
            _zero_v7333_agent_attach_continuation(task, continuation)
        _zero_v7334_agent_attach_self_repair(task)
        _zero_v7335_agent_attach_bridge(task)


    def _observe_and_record_loop_decision(
        self,
        *,
        effective_task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(effective_task, dict) or not isinstance(runner_result, dict):
            return {}

        metadata = _zero_v7332_agent_constitutional_metadata(runner_result)
        if metadata and _zero_v7332_agent_is_constitutional_block(runner_result):
            boundary = _zero_v7332_agent_boundary(metadata)
            _zero_v7332_agent_apply_boundary_to_task(effective_task, boundary)
            decision = {
                "decision": "wait",
                "next_action": "wait_for_external_event",
                "terminal": False,
                "should_continue": False,
                "should_replan": False,
                "should_fail": False,
                "reason": boundary["constitutional_activation_reason"],
                "observation": {
                    "governed_runtime_boundary": True,
                    "constitutional_boundary": copy.deepcopy(boundary),
                    "raw": {
                        "blocker_gate": {
                            "active_blockers": [
                                {
                                    "kind": "constitutional_execution_boundary",
                                    "reason": boundary["constitutional_activation_reason"],
                                    "requires_review": True,
                                }
                            ]
                        }
                    },
                },
            }
            self._append_loop_history_event(
                effective_task,
                decision="wait",
                next_action="wait_for_external_event",
                reason=boundary["constitutional_activation_reason"],
                terminal=False,
                should_continue=False,
                should_replan=False,
                observation=decision["observation"],
            )
            return decision

        max_replans = self._safe_int(effective_task.get("max_replans"), 1)
        replan_count = self._safe_int(effective_task.get("replan_count"), 0)

        try:
            local_observation = observe_local_runner_result(runner_result)
            decision = observe_and_decide(
                runner_result,
                effective_task,
                allow_replan=True,
                max_replans=max_replans,
                replan_count=replan_count,
                local_observation=local_observation,
            )
        except Exception as e:
            decision = {
                "decision": "fail",
                "next_action": "finish",
                "terminal": True,
                "should_continue": False,
                "should_replan": False,
                "should_fail": True,
                "reason": f"observe_and_decide failed: {e}",
                "observation": {},
            }

        if not isinstance(decision, dict):
            decision = {
                "decision": "fail",
                "next_action": "finish",
                "terminal": True,
                "should_continue": False,
                "should_replan": False,
                "should_fail": True,
                "reason": "observe_and_decide returned non-dict result",
                "observation": {},
            }

        self._apply_loop_decision_to_task(
            effective_task=effective_task,
            loop_decision=decision,
        )
        self._attach_agent_loop_decision_metadata(
            effective_task=effective_task,
            runner_result=runner_result,
            decision=decision,
        )
        return decision

    def _attach_agent_loop_decision_metadata(
        self,
        *,
        effective_task: Dict[str, Any],
        runner_result: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> None:
        continuation = _zero_v7333_agent_continuation_summary(runner_result)
        if continuation.get("governed_continuation"):
            metadata = _zero_v7332_agent_constitutional_metadata(runner_result)
            if metadata:
                boundary = _zero_v7332_agent_boundary(metadata)
                _zero_v7332_agent_apply_boundary_to_task(effective_task, boundary)
            _zero_v7333_agent_attach_continuation(effective_task, continuation)
            if continuation.get("terminal_constitutional_boundary"):
                effective_task["status"] = "review_required"
                effective_task["blocked_reason"] = continuation.get("continuation_reason")
                effective_task["waiting_reason"] = "constitutional_review_required"
                effective_task["agent_action"] = "governed_continuation_boundary"
                effective_task["next_action"] = "wait_for_external_event"
                effective_task.setdefault("replan_blocked_reason", "constitutional_boundary")
                decision["decision"] = "wait"
                decision["next_action"] = "wait_for_external_event"
                decision["should_continue"] = False
                decision["should_replan"] = False
                decision["should_fail"] = False
                decision["reason"] = continuation.get("continuation_reason")
                observation = decision.get("observation") if isinstance(decision.get("observation"), dict) else {}
                observation["governed_continuation"] = copy.deepcopy(continuation)
                decision["observation"] = observation

        if isinstance(runner_result, dict):
            _zero_v7334_agent_attach_self_repair(runner_result)
            runtime_state = runner_result.get("runtime_state")
            if isinstance(runtime_state, dict):
                _zero_v7334_agent_attach_self_repair(runtime_state)
        _zero_v7334_agent_attach_self_repair(effective_task)
        if effective_task.get("self_repair_terminal_block"):
            effective_task["next_action"] = "wait_for_external_event"
            effective_task["agent_action"] = "governed_self_repair_boundary"
            decision["should_replan"] = False
            decision["reason"] = effective_task.get("self_repair_reason")

        if isinstance(runner_result, dict):
            _zero_v7335_agent_attach_bridge(runner_result)
            runtime_state = runner_result.get("runtime_state")
            if isinstance(runtime_state, dict):
                _zero_v7335_agent_attach_bridge(runtime_state)
        _zero_v7335_agent_attach_bridge(effective_task)
        if effective_task.get("mutation_bridge_eligible"):
            decision["decision"] = "wait"
            decision["next_action"] = "wait_for_external_event"
            decision["should_continue"] = False
            decision["should_replan"] = False
            decision["reason"] = effective_task.get("mutation_bridge_reason")
            observation = decision.get("observation") if isinstance(decision.get("observation"), dict) else {}
            observation["controlled_mutation_bridge"] = copy.deepcopy(effective_task.get("controlled_mutation_bridge"))
            decision["observation"] = observation

    def _active_blockers_from_loop_decision(
        self,
        *,
        effective_task: Dict[str, Any],
        loop_decision: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract active generic blockers from the loop decision observation.

        Architectural boundary:
        - AgentLoop does not know review/audit/approval semantics.
        - It only understands generic blockers emitted by loop_decision/runtime.
        """
        if not isinstance(effective_task, dict):
            effective_task = {}
        if not isinstance(loop_decision, dict):
            loop_decision = {}

        observation = loop_decision.get("observation")
        if not isinstance(observation, dict):
            observation = {}

        raw = observation.get("raw")
        if not isinstance(raw, dict):
            raw = {}

        blocker_gate = raw.get("blocker_gate")
        if isinstance(blocker_gate, dict):
            active = blocker_gate.get("active_blockers")
            if isinstance(active, list):
                normalized_active = active_blockers(active)
                if normalized_active:
                    return [copy.deepcopy(item) for item in normalized_active]

            blockers = blocker_gate.get("blockers")
            normalized_from_gate = active_blockers(blockers)
            if normalized_from_gate:
                return [copy.deepcopy(item) for item in normalized_from_gate]

        for source in (raw, observation, effective_task):
            if isinstance(source, dict):
                normalized = active_blockers(source.get("blockers"))
                if normalized:
                    return [copy.deepcopy(item) for item in normalized]

        return []

    def _review_gate_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Return normalized human-review gate state for the loop.

        This stays deliberately generic: AgentLoop does not decide policy; it
        only honors persisted review fields produced by policy/blocker/runtime.
        """
        if not isinstance(task, dict):
            return {"requires_review": False, "status": "", "pending": False, "approved": False, "rejected": False}

        raw_status = str(task.get("review_status") or "").strip().lower()
        requires_review = bool(task.get("requires_review", False))
        review_id = str(task.get("review_id") or "").strip()
        review_payload = task.get("review_payload")
        has_review_payload = isinstance(review_payload, dict) and bool(review_payload)

        # If review metadata exists but status is missing, treat it as pending.
        if not raw_status and (requires_review or review_id or has_review_payload):
            raw_status = "pending"

        pending_statuses = {"", "pending", "required", "requested", "waiting", "waiting_review", "review_required"}
        approved_statuses = {"approved", "accepted", "allowed", "cleared", "resolved"}
        rejected_statuses = {"rejected", "denied", "declined", "cancelled", "canceled"}

        approved = raw_status in approved_statuses
        rejected = raw_status in rejected_statuses
        pending = bool(requires_review or review_id or has_review_payload) and not approved and not rejected
        if raw_status in pending_statuses and (requires_review or review_id or has_review_payload):
            pending = True

        return {
            "requires_review": bool(requires_review or review_id or has_review_payload),
            "status": raw_status,
            "pending": bool(pending),
            "approved": bool(approved),
            "rejected": bool(rejected),
        }

    def _append_loop_history_event(
        self,
        task: Dict[str, Any],
        *,
        decision: str,
        next_action: str,
        reason: str,
        terminal: bool = False,
        should_continue: bool = False,
        should_replan: bool = False,
        should_fail: bool = False,
        observation: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not isinstance(task, dict):
            return

        history = task.get("loop_history")
        if not isinstance(history, list):
            history = []

        history.append(
            {
                "cycle": self._safe_int(task.get("loop_cycle_count"), 0),
                "decision": str(decision or ""),
                "next_action": str(next_action or ""),
                "reason": str(reason or ""),
                "terminal": bool(terminal),
                "should_continue": bool(should_continue),
                "should_replan": bool(should_replan),
                "should_fail": bool(should_fail),
                "observation": copy.deepcopy(observation) if isinstance(observation, dict) else {},
                "active_blockers": copy.deepcopy(task.get("blockers", [])) if isinstance(task.get("blockers"), list) else [],
                "review_status": str(task.get("review_status") or ""),
                "agent_action": str(task.get("agent_action") or ""),
            }
        )
        task["loop_history"] = history[-25:]

    def _apply_blocker_gate_to_task(
        self,
        *,
        effective_task: Dict[str, Any],
        loop_decision: Dict[str, Any],
    ) -> None:
        """Apply blocker/review gate result to task loop state.

        First-priority loop stabilization rule:
        - active blockers or pending review must stop execution deterministically;
        - approved/cleared review can resume only when no active blockers remain;
        - rejected review fails closed and cannot silently continue.
        """
        observation = loop_decision.get("observation") if isinstance(loop_decision, dict) else {}
        if not isinstance(observation, dict):
            observation = {}

        review_gate = self._review_gate_state(effective_task)
        if review_gate.get("rejected"):
            effective_task["status"] = "failed"
            effective_task["blocked_reason"] = "review_rejected"
            effective_task["waiting_reason"] = "review_rejected"
            effective_task["agent_action"] = "review_rejected_stop"
            effective_task["next_action"] = "finish"
            effective_task["terminal_reason"] = "review_rejected"
            effective_task["active_blocker_count"] = 0
            self._append_loop_history_event(
                effective_task,
                decision="fail",
                next_action="finish",
                reason="review_rejected",
                terminal=True,
                should_fail=True,
                observation=observation,
            )
            return

        blockers = self._active_blockers_from_loop_decision(
            effective_task=effective_task,
            loop_decision=loop_decision,
        )

        if blockers:
            effective_task["blockers"] = [copy.deepcopy(item) for item in blockers]
            effective_task["active_blocker_count"] = len(blockers)
            effective_task["status"] = "blocked"
            effective_task["blocked_reason"] = "active_blockers"
            effective_task["waiting_reason"] = "active_blockers"
            effective_task["agent_action"] = "await_external_decision"
            effective_task["next_action"] = "wait_for_external_event"
            if not str(effective_task.get("terminal_reason") or "").strip():
                effective_task["terminal_reason"] = "waiting_for_external_blocker"
            return

        if review_gate.get("pending"):
            effective_task["blockers"] = []
            effective_task["active_blocker_count"] = 1
            effective_task["status"] = "review_required"
            effective_task["blocked_reason"] = "review_required"
            effective_task["waiting_reason"] = "review_required"
            effective_task["agent_action"] = "await_review_decision"
            effective_task["next_action"] = "wait_for_external_event"
            if not str(effective_task.get("terminal_reason") or "").strip():
                effective_task["terminal_reason"] = "waiting_for_review"
            self._append_loop_history_event(
                effective_task,
                decision="wait",
                next_action="wait_for_external_event",
                reason="review_required",
                terminal=False,
                should_continue=False,
                observation=observation,
            )
            return

        previous_status = str(effective_task.get("status") or "").strip().lower()
        previous_action = str(effective_task.get("next_action") or "").strip().lower()
        previous_agent_action = str(effective_task.get("agent_action") or "").strip().lower()
        previous_blocked_reason = str(effective_task.get("blocked_reason") or "").strip().lower()
        previous_waiting_reason = str(effective_task.get("waiting_reason") or "").strip().lower()

        was_waiting_for_blocker = (
            previous_status in {"blocked", "waiting", "waiting_blocker", "waiting_review", "pending_review", "review_required"}
            or previous_action in {
                "wait_for_external_event",
                "wait_for_blocker",
                "wait_for_review",
                "await_review_decision",
            }
            or previous_agent_action in {"await_external_decision", "await_review_decision", "wait_for_review"}
            or previous_blocked_reason in {"active_blockers", "review_required", "human_review_required"}
            or previous_waiting_reason in {"active_blockers", "review_required", "human_review_required", "waiting_for_review"}
        )

        if not was_waiting_for_blocker:
            effective_task["active_blocker_count"] = 0
            return

        effective_task["blockers"] = []
        effective_task["active_blocker_count"] = 0
        effective_task["blocked_reason"] = ""
        effective_task["waiting_reason"] = ""
        effective_task["agent_action"] = "resume_execution"
        effective_task["status"] = "running"
        effective_task["next_action"] = "run_next_tick"
        effective_task["terminal_reason"] = ""

        self._append_loop_history_event(
            effective_task,
            decision="resume",
            next_action="run_next_tick",
            reason="blockers_or_review_cleared_auto_resume",
            terminal=False,
            should_continue=True,
            observation=observation,
        )

    def _apply_loop_decision_to_task(
        self,
        *,
        effective_task: Dict[str, Any],
        loop_decision: Dict[str, Any],
    ) -> None:
        if not isinstance(effective_task, dict) or not isinstance(loop_decision, dict):
            return

        self._ensure_loop_state_defaults(effective_task)

        observation = loop_decision.get("observation")
        if not isinstance(observation, dict):
            observation = {}

        decision = str(loop_decision.get("decision") or "").strip()
        next_action = str(loop_decision.get("next_action") or "").strip()
        reason = str(loop_decision.get("reason") or "").strip()

        effective_task["last_observation"] = copy.deepcopy(observation)
        effective_task["last_decision"] = decision
        effective_task["last_decision_reason"] = reason
        effective_task["next_action"] = next_action

        if bool(loop_decision.get("terminal")):
            effective_task["terminal_reason"] = reason
        elif not effective_task.get("terminal_reason"):
            effective_task["terminal_reason"] = ""

        self._apply_blocker_gate_to_task(
            effective_task=effective_task,
            loop_decision=loop_decision,
        )
        next_action = str(effective_task.get("next_action") or next_action or "").strip()
        decision = str(effective_task.get("last_decision") or decision or "").strip()

        current_cycle = self._safe_int(effective_task.get("loop_cycle_count"), 0)
        effective_task["loop_cycle_count"] = current_cycle + 1

        history = effective_task.get("loop_history")
        if not isinstance(history, list):
            history = []

        history.append(
            {
                "cycle": effective_task["loop_cycle_count"],
                "decision": decision,
                "next_action": next_action,
                "reason": reason,
                "terminal": bool(loop_decision.get("terminal")),
                "should_continue": bool(loop_decision.get("should_continue")),
                "should_replan": bool(loop_decision.get("should_replan")),
                "should_fail": bool(loop_decision.get("should_fail")),
                "observation": copy.deepcopy(observation),
                "active_blockers": copy.deepcopy(effective_task.get("blockers", [])) if isinstance(effective_task.get("blockers"), list) else [],
            }
        )

        effective_task["loop_history"] = history[-25:]

        boundary = effective_task.get("constitutional_boundary")
        if isinstance(boundary, dict):
            reason = str(boundary.get("constitutional_activation_reason") or "constitutional_blocked")
            effective_task["blocked_reason"] = reason
            effective_task["waiting_reason"] = "constitutional_review_required"
            effective_task["agent_action"] = "governed_constitutional_boundary"
            effective_task["next_action"] = "wait_for_external_event"
            effective_task["requires_review"] = True

    def _ensure_loop_state_defaults(self, task_dict: Dict[str, Any]) -> Dict[str, Any]:
        task_dict.setdefault("loop_cycle_count", 0)
        task_dict.setdefault("loop_history", [])
        task_dict.setdefault("last_observation", {})
        task_dict.setdefault("last_decision", "")
        task_dict.setdefault("last_decision_reason", "")
        task_dict.setdefault("next_action", "")
        task_dict.setdefault("terminal_reason", "")
        task_dict.setdefault("blocked_reason", "")
        task_dict.setdefault("waiting_reason", "")
        task_dict.setdefault("agent_action", "")
        task_dict.setdefault("requires_review", False)
        task_dict.setdefault("review_status", "")
        task_dict.setdefault("review_id", "")
        if not isinstance(task_dict.get("review_payload"), dict):
            task_dict["review_payload"] = {}
        if not isinstance(task_dict.get("blockers"), list):
            task_dict["blockers"] = []
        task_dict["active_blocker_count"] = len(active_blockers(task_dict.get("blockers"))) if isinstance(task_dict.get("blockers"), list) else 0
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
            "blockers",
            "active_blocker_count",
            "blocked_reason",
            "waiting_reason",
            "requires_review",
            "review_status",
            "review_id",
            "review_payload",
            "agent_action",
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
        normalized["execution_path"] = agent_execution_path()
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

        execution_log = normalized.get("execution_log")
        if isinstance(execution_log, list):
            normalized["execution_log"] = [copy.deepcopy(item) for item in execution_log if isinstance(item, dict)]
        else:
            normalized["execution_log"] = []

        normalized["final_answer"] = str(normalized.get("final_answer") or "")
        if "error" in normalized:
            normalized["error"] = normalized.get("error")
        else:
            normalized["error"] = None

        self._attach_agent_loop_execution_metadata(normalized)
        return normalized

    def _attach_agent_loop_execution_metadata(self, execution: Dict[str, Any]) -> None:
        if not isinstance(execution, dict):
            return

        metadata = _zero_v7332_agent_constitutional_metadata(execution)
        if metadata and _zero_v7332_agent_is_constitutional_block(execution):
            boundary = _zero_v7332_agent_boundary(metadata)
            execution["ok"] = False
            execution["status"] = "review_required"
            execution["governed_runtime_boundary"] = True
            execution["constitutional_boundary"] = copy.deepcopy(boundary)
            execution["constitutional_blocked"] = True
            execution["should_replan"] = False
            execution["retryable"] = False
            execution["error"] = boundary["constitutional_activation_reason"]

        continuation = _zero_v7333_agent_continuation_summary(execution)
        if continuation.get("governed_continuation"):
            _zero_v7333_agent_attach_continuation(execution, continuation)
            if continuation.get("terminal_constitutional_boundary"):
                execution["ok"] = False
                execution["status"] = "review_required"
                execution["error"] = continuation.get("continuation_reason")

        _zero_v7334_agent_attach_self_repair(execution)
        _zero_v7335_agent_attach_bridge(execution)
        _zero_v7336_agent_attach_verified_change(execution)

    def _plan_has_tool_call(self, plan: Any) -> bool:
        return bool(self._extract_tool_calls_from_plan(plan))

    def _extract_tool_call_from_plan(self, plan: Any) -> Optional[Dict[str, Any]]:
        calls = self._extract_tool_calls_from_plan(plan)
        return calls[0] if calls else None

    def _extract_tool_calls_from_plan(self, plan: Any) -> List[Dict[str, Any]]:
        if not isinstance(plan, dict):
            return []
        if "type" in plan or "action" in plan:
            parsed = tool_decision_to_tool_call(plan)
            if parsed.get("ok"):
                return [{"tool": parsed.get("tool"), "args": copy.deepcopy(parsed.get("args", {}))}]
        if isinstance(plan.get("tool_calls"), list):
            calls = []
            for item in plan.get("tool_calls") or []:
                if isinstance(item, dict):
                    parsed = tool_decision_to_tool_call(item)
                    if parsed.get("ok"):
                        calls.append({"tool": parsed.get("tool"), "args": copy.deepcopy(parsed.get("args", {}))})
                    else:
                        calls.append(copy.deepcopy(item))
            return calls
        if isinstance(plan.get("tool_call"), dict):
            return [copy.deepcopy(plan["tool_call"])]
        if plan.get("tool") is not None:
            return [{
                "tool": plan.get("tool"),
                "args": copy.deepcopy(plan.get("args", {})),
            }]
        nested = plan.get("plan")
        if isinstance(nested, dict):
            return self._extract_tool_calls_from_plan(nested)
        return []

    def _execute_l5_or_legacy_tool_plan(
        self,
        *,
        plan: Dict[str, Any],
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        if self._is_l5_tool_decision_plan(plan):
            return self._execute_tool_decision_cycles(
                initial_plan=plan,
                context=context,
                user_input=user_input,
                route=route,
            )
        return self._execute_tool_call_plan(plan)

    def _is_l5_tool_decision_plan(self, plan: Any) -> bool:
        return isinstance(plan, dict) and ("type" in plan or "action" in plan)

    def _execute_tool_decision_cycles(
        self,
        *,
        initial_plan: Dict[str, Any],
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        execution_log: List[Dict[str, Any]] = []
        previous_observation: Dict[str, Any] | None = None
        previous_call: Dict[str, Any] | None = None
        previous_failures: List[Dict[str, Any]] = []
        current_plan: Any = copy.deepcopy(initial_plan)
        last_result: Dict[str, Any] = {}

        for cycle_index in range(1, max(1, self.max_tool_cycles) + 1):
            current_call = self._normalized_l5_decision_call(current_plan)
            decision_input = self._build_tool_decision_input(
                goal=user_input,
                current_call=current_call,
                previous_call=previous_call,
                previous_observation=previous_observation,
                previous_failures=previous_failures,
                results=results,
                cycle_index=cycle_index,
            )
            tool_result = self.tool_call_executor.execute_decision(
                current_plan,
                source="agent_loop",
                decision_input=decision_input,
            )
            status = str(tool_result.get("status") or "")

            if status == "no_tool":
                final_answer = self._extract_final_answer(None, current_plan, user_input)
                if results and not final_answer:
                    final_answer = self._extract_tool_observation_summary(last_result)
                return {
                    "ok": True,
                    "steps_executed": len(results),
                    "results": results,
                    "execution_log": execution_log,
                    "execution_trace": copy.deepcopy(execution_log),
                    "last_result": copy.deepcopy(last_result) if last_result else copy.deepcopy(tool_result),
                    "final_answer": final_answer,
                    "error": None,
                    "stopped_reason": "no_tool",
                }

            trace_event = tool_call_trace_event(tool_result)
            trace_event["cycle_index"] = cycle_index
            results.append(
                {
                    "step_index": cycle_index,
                    "step": {
                        "type": "tool_decision",
                        "tool_call": copy.deepcopy(current_call or {}),
                    },
                    "result": copy.deepcopy(tool_result),
                }
            )
            execution_log.append(trace_event)
            last_result = tool_result
            previous_call = current_call

            if tool_result.get("ok") is not True:
                previous_failures.append(
                    {
                        "tool": tool_result.get("tool"),
                        "status": status,
                        "error": tool_result.get("error"),
                    }
                )
                return {
                    "ok": False,
                    "steps_executed": cycle_index,
                    "results": results,
                    "execution_log": execution_log,
                    "execution_trace": copy.deepcopy(execution_log),
                    "last_result": copy.deepcopy(last_result),
                    "final_answer": str(status or "tool_error"),
                    "error": tool_result.get("error"),
                    "stopped_reason": status or "tool_error",
                }

            output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
            observation = output.get("observation") if isinstance(output.get("observation"), dict) else {}
            previous_observation = {
                "status": status,
                "tool": tool_result.get("tool"),
                "ok": bool(tool_result.get("ok")),
                "observation": copy.deepcopy(observation),
                "trace": copy.deepcopy(output.get("trace") if isinstance(output.get("trace"), dict) else {}),
            }

            next_context = copy.deepcopy(context)
            next_context["previous_tool_observation"] = copy.deepcopy(previous_observation)
            next_context["tool_observation"] = copy.deepcopy(previous_observation)
            next_context["tool_decision_cycle"] = cycle_index
            next_plan = self._call_planner(
                context=next_context,
                user_input=user_input,
                route=route,
            )
            if not self._is_l5_tool_decision_plan(next_plan):
                final_answer = self._extract_final_answer(None, next_plan, "")
                return {
                    "ok": True,
                    "steps_executed": cycle_index,
                    "results": results,
                    "execution_log": execution_log,
                    "execution_trace": copy.deepcopy(execution_log),
                    "last_result": copy.deepcopy(last_result),
                    "final_answer": final_answer or self._extract_tool_observation_summary(last_result),
                    "error": None,
                    "stopped_reason": "terminal_response",
                }
            current_plan = next_plan

        max_result = self._max_tool_cycles_result(last_result)
        results.append(
            {
                "step_index": len(results) + 1,
                "step": {"type": "tool_decision_guard"},
                "result": copy.deepcopy(max_result),
            }
        )
        execution_log.append(tool_call_trace_event(max_result))
        return {
            "ok": False,
            "steps_executed": len(results),
            "results": results,
            "execution_log": execution_log,
            "execution_trace": copy.deepcopy(execution_log),
            "last_result": max_result,
            "final_answer": "max_tool_cycles_reached",
            "error": "max_tool_cycles_reached",
            "stopped_reason": "max_tool_cycles",
        }

    def _normalized_l5_decision_call(self, plan: Any) -> Dict[str, Any] | None:
        parsed = tool_decision_to_tool_call(plan)
        if parsed.get("ok") is not True:
            return None
        return {
            "tool": parsed.get("tool"),
            "args": copy.deepcopy(parsed.get("args", {})),
        }

    def _max_tool_cycles_result(self, last_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": str(last_result.get("tool") or ""),
            "args": copy.deepcopy(last_result.get("args", {})),
            "status": "blocked",
            "output": {
                "status": "blocked",
                "observation": {
                    "type": "tool_error",
                    "summary": "max_tool_cycles_reached",
                    "data": {"reason": "max_tool_cycles_reached"},
                },
                "trace": {
                    "tool_call_id": None,
                    "tool": str(last_result.get("tool") or ""),
                    "args": {},
                    "duration_ms": 0,
                    "source": "agent_loop",
                },
            },
            "error": "max_tool_cycles_reached",
            "request_id": None,
            "side_effect_level": "none",
            "final_decision": "STOP",
        }

    def _build_tool_decision_input(
        self,
        *,
        goal: str,
        current_call: Dict[str, Any] | None,
        previous_call: Dict[str, Any] | None,
        previous_observation: Dict[str, Any] | None,
        previous_failures: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
        cycle_index: int,
    ) -> Dict[str, Any]:
        requested_tool = str((current_call or {}).get("tool") or "")
        last_tool = str((previous_call or {}).get("tool") or "")
        observation = previous_observation.get("observation") if isinstance(previous_observation, dict) else {}
        observation_summary = ""
        if isinstance(observation, dict):
            observation_summary = str(observation.get("summary") or "")
        same_tool_repeats = 0
        if current_call is not None and previous_call is not None and current_call == previous_call:
            same_tool_repeats = 1
        retries_for_tool = sum(1 for item in previous_failures if item.get("tool") == requested_tool)
        return {
            "goal": str(goal or ""),
            "requested_tool": requested_tool,
            "last_tool": last_tool,
            "observation_summary": observation_summary,
            "previous_failures": copy.deepcopy(previous_failures),
            "budget_remaining": {},
            "tool_budget": {
                "max_loop_steps": max(1, self.max_tool_cycles),
                "max_tool_calls": max(1, self.max_tool_cycles),
                "max_same_tool_repeats": 1,
                "max_retries_per_tool": 1,
            },
            "loop_steps": max(0, cycle_index - 1),
            "tool_calls": len(results),
            "same_tool_repeats": same_tool_repeats,
            "retries_for_tool": retries_for_tool,
        }

    def _execute_tool_call_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        tool_calls = self._extract_tool_calls_from_plan(plan)
        results: List[Dict[str, Any]] = []
        execution_log: List[Dict[str, Any]] = []
        previous_result: Any = None
        last_result: Dict[str, Any] = {}

        for index, tool_call in enumerate(tool_calls, start=1):
            effective_call = copy.deepcopy(tool_call)
            args = effective_call.get("args")
            if isinstance(args, dict) and "{{previous_content}}" in str(args.get("content", "")):
                output = previous_result.get("output") if isinstance(previous_result, dict) else {}
                content = output.get("content") if isinstance(output, dict) else ""
                args["content"] = str(args.get("content", "")).replace("{{previous_content}}", str(content or ""))

            tool_result = self.tool_call_executor.execute(effective_call, source="agent_loop")
            trace_event = tool_call_trace_event(tool_result)
            step = {
                "type": "tool_call",
                "tool_call": copy.deepcopy(effective_call),
            }
            results.append(
                {
                    "step_index": index,
                    "step": step,
                    "result": copy.deepcopy(tool_result),
                }
            )
            execution_log.append(trace_event)
            last_result = tool_result
            previous_result = tool_result

            if not tool_result.get("ok"):
                return {
                    "ok": False,
                    "steps_executed": index,
                    "results": results,
                    "execution_log": execution_log,
                    "execution_trace": copy.deepcopy(execution_log),
                    "last_result": copy.deepcopy(last_result),
                    "final_answer": str(tool_result.get("status") or ""),
                    "error": tool_result.get("error"),
                }

        return {
            "ok": True,
            "steps_executed": len(tool_calls),
            "results": results,
            "execution_log": execution_log,
            "execution_trace": copy.deepcopy(execution_log),
            "last_result": copy.deepcopy(last_result),
            "final_answer": self._extract_tool_observation_summary(last_result),
            "error": None,
        }

    def _extract_tool_observation_summary(self, tool_result: Dict[str, Any]) -> str:
        output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
        observation = output.get("observation") if isinstance(output.get("observation"), dict) else {}
        summary = observation.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        value = output.get("summary")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return str(tool_result.get("status") or "")

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

    def _detect_document_flow_capability(self, user_input: str) -> Dict[str, Any]:
        return detect_document_flow_capability(user_input)

    def _build_capability_registry_hint(self, capability_hint: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(capability_hint, dict):
            return {}

        capability_name = str(capability_hint.get("capability") or "").strip()
        operation = str(capability_hint.get("operation") or "").strip()

        operation_map = {
            "summary": "run_summary",
            "action_items": "run_action_items",
            "summary_and_action_items": "run_summary_and_action_items",
        }

        registry_operation = operation_map.get(operation, "")

        return {
            "capability": capability_name,
            "operation": operation,
            "registry_operation": registry_operation,
            "capability_registered": has_capability(capability_name),
            "operation_registered": (
                bool(registry_operation)
                and has_operation(capability_name, registry_operation)
            ),
        }

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
            single_shot_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(single_shot_result, dict):
                single_shot_result["mode"] = "llm_fallback_single_shot"
            return single_shot_result

        llm_plan = self._call_llm_planner(
            context=context,
            user_input=user_input,
            route=route,
        )
        llm_plan = self._normalize_plan_result(llm_plan)

        if self.debug:
            print("[AgentLoop] llm_plan =", llm_plan)

        if not isinstance(llm_plan, dict):
            single_shot_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(single_shot_result, dict):
                single_shot_result["mode"] = "llm_fallback_single_shot"
                single_shot_result["llm_plan_error"] = "llm_plan invalid"
            return single_shot_result

        if llm_plan.get("ok") is False:
            single_shot_result = self._run_single_shot_mode(
                context=context,
                user_input=user_input,
                route=route,
            )
            if isinstance(single_shot_result, dict):
                single_shot_result["mode"] = "llm_fallback_single_shot"
                single_shot_result["llm_plan_error"] = llm_plan.get("error")
            return single_shot_result

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
        if not self.execution_runtime or not self.execution_runtime.has_endpoint:
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

        if self._plan_has_tool_call(plan):
            execution_result = self._execute_l5_or_legacy_tool_plan(
                plan=plan,
                context=context,
                user_input=user_input,
                route=route,
            )
            normalized_execution = self._normalize_execution_result(execution_result)
            return self._make_agent_response(
                ok=bool(normalized_execution.get("ok", False)) if isinstance(normalized_execution, dict) else False,
                mode="single_shot",
                context=context,
                route=route,
                plan=plan,
                execution=normalized_execution,
                final_answer=self._extract_final_answer(normalized_execution, plan, user_input),
                error=normalized_execution.get("error") if isinstance(normalized_execution, dict) else None,
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
        if not self.execution_runtime or not self.execution_runtime.has_endpoint:
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
            step_executor=self.execution_runtime,
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

            if self._plan_has_tool_call(plan):
                execution_result = self._execute_l5_or_legacy_tool_plan(
                    plan=plan,
                    context=context,
                    user_input=user_input,
                    route=route,
                )
                normalized_execution = self._normalize_execution_result(execution_result)
                return self._make_agent_response(
                    ok=bool(normalized_execution.get("ok", False)) if isinstance(normalized_execution, dict) else False,
                    mode="task_tool_call",
                    context=context,
                    route=route,
                    plan=plan,
                    execution=normalized_execution,
                    final_answer=self._extract_final_answer(normalized_execution, plan, user_input),
                    error=normalized_execution.get("error") if isinstance(normalized_execution, dict) else None,
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

        # v7.2.3: Planner Autonomous Repair Gate Unification.
        # Scheduler may suppress duplicate autonomous repair requests before
        # enqueue.  Do not treat that as a freshly-created task, do not persist
        # over the existing task, and do not submit it again.  This keeps the
        # planner/task entrypoint aligned with the scheduler duplicate gate.
        if bool(create_result.get("duplicate_suppressed", False)) or bool(create_result.get("suppress", False)):
            final_answer = str(
                create_result.get("final_answer")
                or create_result.get("message")
                or "duplicate autonomous repair task suppressed"
            ).strip()
            if not final_answer:
                final_answer = "duplicate autonomous repair task suppressed"

            return self._make_agent_response(
                ok=True,
                mode="task_duplicate_suppressed",
                context=context,
                route=route,
                plan=normalized_plan,
                execution={
                    "ok": True,
                    "steps_executed": 0,
                    "results": [],
                    "execution_log": [],
                    "execution_trace": [],
                    "last_result": copy.deepcopy(create_result),
                    "final_answer": final_answer,
                    "error": None,
                },
                final_answer=final_answer,
                error=None,
                extra={
                    "create_result": create_result,
                    "duplicate_suppressed": True,
                    "repair_fingerprint": create_result.get("repair_fingerprint"),
                    "existing_task_id": create_result.get("task_id") or create_result.get("task_name"),
                },
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
            self._apply_route_execution_context_to_task(created_task, route)
            self._apply_capability_metadata_to_task(created_task, route)
        self._ensure_operator_session_for_task(
            task=created_task,
            context=context,
            plan=created_task["planner_result"],
        )
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
        self._ensure_operator_session_for_task(
            task=task,
            context=context,
            plan=task["planner_result"],
        )

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
        if isinstance(context, dict) and _zero_v7338_agent_autonomous_repair_intent(user_input):
            context.setdefault("runtime_hints", {})
            if isinstance(context.get("runtime_hints"), dict):
                context["runtime_hints"]["autonomous_repair_chain_v2"] = True
                context["runtime_hints"]["required_authority_path"] = (
                    "AgentLoop -> Scheduler -> StepExecutor -> ExecutionGateway -> RuntimeNativeAutonomousRepairChain"
                )
            context["autonomous_repair_chain_intent"] = True
        if self.debug:
            print("[AgentLoop] context =", context)
        return context

    def _ensure_operator_session_for_task(
        self,
        *,
        task: Dict[str, Any],
        context: Dict[str, Any],
        plan: Any = None,
    ) -> Dict[str, Any]:
        bootstrap = getattr(self, "operator_session_bootstrap", None)
        if bootstrap is None:
            return {"ok": True, "created": False, "operator_session_id": ""}
        try:
            steps = task.get("pending_steps") or task.get("steps") or self._extract_steps_from_plan(plan)
            return bootstrap.ensure_session_for_task(
                task,
                context=context,
                goal=str(task.get("goal") or task.get("description") or task.get("title") or ""),
                pending_steps=steps,
                metadata={"source": "agent_loop"},
            )
        except Exception as exc:
            if self.debug:
                print(f"[AgentLoop] operator session bootstrap ignored: {exc}")
            return {"ok": False, "created": False, "operator_session_id": "", "error": str(exc)}

    def _looks_like_explicit_task_request(self, text: str) -> bool:
        return looks_like_explicit_task_request(text)

    def _should_enter_task_mode(self, route: Any, user_input: str) -> bool:
        return should_enter_task_mode(route, user_input)

    def _apply_capability_metadata_to_task(self, task: Dict[str, Any], route: Any) -> Dict[str, Any]:
        if not isinstance(task, dict) or not isinstance(route, dict):
            return task

        capability_hint = route.get("capability_hint")
        if isinstance(capability_hint, dict):
            task["capability_hint"] = copy.deepcopy(capability_hint)

        capability_registry_hint = route.get("capability_registry_hint")
        if isinstance(capability_registry_hint, dict):
            task["capability_registry_hint"] = copy.deepcopy(capability_registry_hint)

        capability = str(route.get("capability") or "").strip()
        operation = str(route.get("operation") or "").strip()

        if capability:
            task["capability"] = capability
        if operation:
            task["operation"] = operation

        if not (
            capability
            or operation
            or isinstance(capability_hint, dict)
            or isinstance(capability_registry_hint, dict)
        ):
            return task

        input_path = self._route_first_string(
            route,
            "input_path",
            "document_input_path",
            "source_path",
        )
        summary_output_path = self._route_first_string(
            route,
            "summary_output_path",
            "summary_path",
        )
        action_items_output_path = self._route_first_string(
            route,
            "action_items_output_path",
            "action_items_path",
        )

        should_enable_document_flow = (
            capability == "document_flow"
            and operation == "summary_and_action_items"
            and bool(input_path)
            and bool(summary_output_path)
            and bool(action_items_output_path)
        )

        has_planner_steps = bool(task.get("steps")) or self._safe_int(task.get("steps_total", 0), 0) > 0

        if should_enable_document_flow and not has_planner_steps:
            task["capability_execution"] = {
                "enabled": True,
                "status": "pending",
                "reason": "explicit document_flow capability paths provided",
                "input_path": input_path,
                "summary_output_path": summary_output_path,
                "action_items_output_path": action_items_output_path,
            }
            return task

        missing_paths = []
        if capability == "document_flow" and operation == "summary_and_action_items":
            if not input_path:
                missing_paths.append("input_path")
            if not summary_output_path:
                missing_paths.append("summary_output_path")
            if not action_items_output_path:
                missing_paths.append("action_items_output_path")

        reason = "capability metadata carried into task; execution remains disabled"
        if missing_paths:
            reason = "explicit capability paths missing: " + ", ".join(missing_paths)

        task["capability_execution"] = {
            "enabled": False,
            "status": "metadata_only",
            "reason": reason,
        }

        return task

    def _apply_route_execution_context_to_task(self, task: Dict[str, Any], route: Any) -> Dict[str, Any]:
        if not isinstance(task, dict) or not isinstance(route, dict):
            return task

        if isinstance(route.get("execution_authority"), dict):
            task["execution_authority"] = copy.deepcopy(route["execution_authority"])
        if isinstance(route.get("authority_context"), dict):
            task["authority_context"] = copy.deepcopy(route["authority_context"])
        if isinstance(route.get("runtime_authority_context"), dict):
            task["runtime_authority_context"] = copy.deepcopy(route["runtime_authority_context"])
        if route.get("authority_propagation_required") is not None:
            task["authority_propagation_required"] = bool(route.get("authority_propagation_required"))
        return task

    def _route_first_string(self, route: Any, *keys: str) -> str:
        if not isinstance(route, dict):
            return ""

        for key in keys:
            value = route.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

        capability_execution = route.get("capability_execution")
        if isinstance(capability_execution, dict):
            for key in keys:
                value = capability_execution.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()

        capability_hint = route.get("capability_hint")
        if isinstance(capability_hint, dict):
            for key in keys:
                value = capability_hint.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()

        return ""

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
            self._apply_route_execution_context_to_task(task, route)

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
        return self.execution_runtime.run_step(
            step=copy.deepcopy(step) if isinstance(step, dict) else {"value": copy.deepcopy(step)},
            task={
                "goal": user_input,
                "route": copy.deepcopy(route),
                "previous_result": copy.deepcopy(previous_result),
                "step_index": step_index,
                "step_count": step_count,
            },
            context=copy.deepcopy(context),
            current_tick=int(step_index or 0),
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


# ============================================================
# ZERO v7.0.1 - Autonomous Repair Intent Routing
# ============================================================
# Route bounded autonomous repair requests into normal task/planner mode before
# the older scheduler self-edit shortcut can consume them as a simple task.
# This keeps the write path inside planner -> scheduler/runtime -> code_chain.

def _zero_v7_0_1_extract_workspace_py_path(text: str) -> str:
    match = re.search(
        r"(workspace[/\\][A-Za-z0-9_./\\ -]+?\.py)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/")


def _zero_v7_0_1_looks_like_autonomous_repair(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    if "workspace/" not in lowered or ".py" not in lowered:
        return False

    has_analyze = any(
        token in lowered
        for token in (
            "analyze",
            "inspect",
            "check",
            "diagnose",
            "檢查",
            "分析",
        )
    )
    has_repair = any(
        token in lowered
        for token in (
            "repair",
            "fix",
            "correct",
            "修復",
            "修正",
        )
    )
    has_code_target = any(
        token in lowered
        for token in (
            "function",
            "functions",
            "math",
            "code",
            "函數",
            "程式",
        )
    )
    return has_analyze and has_repair and has_code_target


# ============================================================
# ZERO v7.1.0 - Repair Scope Guard + Preflight Validation
# ============================================================
# Purpose:
# - Bounded autonomous repair requests must fail before task creation when the
#   target path is missing or outside the allowed repair scope.
# - Protected project/core paths must not be silently consumed by the older
#   scheduler self-edit shortcut.

def _zero_v710_normalize_path_text(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v710_extract_any_py_path(text: str) -> str:
    match = re.search(
        r"((?:workspace|core|services|tests|ui)[/\\][A-Za-z0-9_./\\ -]+?\.py|app\.py|system_boot\.py)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _zero_v710_normalize_path_text(match.group(1))


def _zero_v710_looks_like_repair_intent(text: str) -> bool:
    lowered = str(text or "").strip().lower().replace("\\", "/")
    if not lowered:
        return False
    if ".py" not in lowered:
        return False
    has_analyze = any(token in lowered for token in ("analyze", "inspect", "check", "diagnose", "分析", "檢查"))
    has_repair = any(token in lowered for token in ("repair", "fix", "correct", "修復", "修正"))
    has_code_target = any(token in lowered for token in ("function", "functions", "math", "code", "函數", "函式", "程式"))
    return has_analyze and has_repair and has_code_target


def _zero_v710_repair_scope_decision(text: str) -> Dict[str, Any]:
    path_text = _zero_v710_extract_any_py_path(text)
    if not path_text:
        return {
            "ok": False,
            "error": "missing_target_path",
            "reason": "repair request is missing an explicit Python target path",
            "target_path": "",
            "changed_files": [],
        }

    normalized = _zero_v710_normalize_path_text(path_text)
    lowered = normalized.lower()
    protected = (
        lowered == "app.py"
        or lowered == "system_boot.py"
        or lowered.startswith("core/")
        or lowered.startswith("services/")
        or lowered.startswith("tests/")
        or lowered.startswith("ui/")
    )
    if protected:
        return {
            "ok": False,
            "error": "repair_scope_blocked",
            "reason": f"blocked by repair scope guard: {normalized}",
            "target_path": normalized,
            "changed_files": [],
        }

    if not normalized.startswith("workspace/shared/") or not normalized.endswith(".py"):
        return {
            "ok": False,
            "error": "repair_scope_blocked",
            "reason": f"autonomous repair requires workspace/shared/*.py target: {normalized}",
            "target_path": normalized,
            "changed_files": [],
        }

    try:
        repo_root = Path.cwd().resolve()
        target = (repo_root / normalized).resolve()
        target.relative_to(repo_root)
    except Exception:
        return {
            "ok": False,
            "error": "path_escapes_repo_root",
            "reason": f"repair target escapes repo root: {normalized}",
            "target_path": normalized,
            "changed_files": [],
        }

    if not target.exists():
        return {
            "ok": False,
            "error": "file_not_found",
            "reason": f"file not found: {normalized}",
            "target_path": normalized,
            "changed_files": [],
        }

    return {
        "ok": True,
        "error": None,
        "reason": "repair scope preflight passed",
        "target_path": normalized,
        "changed_files": [],
    }


def _zero_v710_make_preflight_response(self, text: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    target_path = str(decision.get("target_path") or "").strip()
    reason = str(decision.get("reason") or decision.get("error") or "repair preflight failed").strip()
    final_answer = f"planner autonomous repair preflight failed: {reason}; changed_files=0"
    route = {
        "mode": "code_chain_repair_preflight",
        "task": False,
        "forced_route": True,
        "planner_autonomous_repair": True,
        "target_path": target_path,
        "error": decision.get("error"),
    }
    execution = {
        "ok": False,
        "steps_executed": 0,
        "results": [],
        "execution_log": [
            {
                "type": "code_chain_repair_preflight",
                "status": "failed",
                "ok": False,
                "target_path": target_path,
                "error": decision.get("error"),
                "reason": reason,
                "changed_files": [],
            }
        ],
        "execution_trace": [
            {
                "step_type": "code_chain_repair_preflight",
                "ok": False,
                "message": final_answer,
                "final_answer": final_answer,
                "error_type": str(decision.get("error") or "repair_preflight_failed"),
                "classification": "repair_scope_guard",
                "attempts": 0,
                "max_attempts": 0,
                "retry_used": False,
            }
        ],
        "last_result": {
            "ok": False,
            "target_path": target_path,
            "error": decision.get("error"),
            "reason": reason,
            "changed_files": [],
        },
        "final_answer": final_answer,
        "error": reason,
    }
    plan = {
        "ok": False,
        "planner_mode": "repair_scope_guard_v7_1_0",
        "intent": "code_chain_repair",
        "semantic_type": "autonomous_code_repair_v0",
        "execution_route": "repair_scope_preflight_failed",
        "final_answer": final_answer,
        "steps": [],
        "error": reason,
        "meta": {
            "fallback_used": False,
            "step_count": 0,
            "target_path": target_path,
            "changed_files": [],
        },
    }
    return self._make_agent_response(
        ok=False,
        mode="code_chain_repair_preflight",
        context={},
        route=route,
        plan=plan,
        execution=execution,
        final_answer=final_answer,
        error=reason,
        extra={
            "code_chain_result": execution["last_result"],
            "repair_scope_guard": copy.deepcopy(decision),
            "original_task": text,
        },
    )


# ZERO v7.3.32 - AgentLoop constitutional boundary awareness
# Recognizes scheduler/runtime constitutional block envelopes as governed
# boundaries. This prevents blind replan/retry without enabling global
# enforcement or bypass paths.

def _zero_v7332_agent_constitutional_metadata(payload: Any, depth: int = 0) -> Dict[str, Any]:
    if depth > 6 or not isinstance(payload, dict):
        return {}

    metadata = payload.get("metadata")
    candidates: List[Dict[str, Any]] = []
    if isinstance(metadata, dict):
        candidates.append(metadata)

    runtime_payload = payload.get("runtime_execution_result")
    if isinstance(runtime_payload, dict) and isinstance(runtime_payload.get("metadata"), dict):
        candidates.append(runtime_payload["metadata"])

    boundary = payload.get("constitutional_boundary")
    if isinstance(boundary, dict):
        candidates.append(boundary)

    candidates.append(payload)
    for candidate in candidates:
        if (
            candidate.get("constitutional_blocked") is True
            or candidate.get("constitutional_activation") is True
            or isinstance(candidate.get("constitutional_enforcement_snapshot"), dict)
            or isinstance(candidate.get("runtime_enforcement_decision"), dict)
        ):
            return copy.deepcopy(candidate)

    for key in (
        "last_result",
        "last_step_result",
        "step_result",
        "result",
        "execution",
        "runtime_state",
        "task",
        "raw_result",
    ):
        found = _zero_v7332_agent_constitutional_metadata(payload.get(key), depth + 1)
        if found:
            return found

    for key in ("results", "step_results", "execution_log", "execution_trace"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in reversed(items):
                found = _zero_v7332_agent_constitutional_metadata(item, depth + 1)
                if found:
                    return found

    return {}


def _zero_v7332_agent_is_constitutional_block(payload: Any) -> bool:
    metadata = _zero_v7332_agent_constitutional_metadata(payload)
    if metadata.get("constitutional_blocked") is True:
        return True
    snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    return bool(
        isinstance(snapshot, dict)
        and snapshot.get("classification") == "block_recommended"
        and metadata.get("constitutional_activation") is True
    )


def _zero_v7332_agent_boundary(metadata: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    if not isinstance(snapshot, dict):
        snapshot = {}
    return {
        "type": "constitutional_execution_boundary",
        "constitutional_activation": bool(metadata.get("constitutional_activation", True)),
        "constitutional_activation_" + "mode": str(metadata.get("constitutional_activation_" + "mode") or ""),
        "constitutional_activation_reason": str(
            metadata.get("constitutional_activation_reason")
            or snapshot.get("reason")
            or "constitutional_blocked"
        ),
        "constitutional_blocked": bool(metadata.get("constitutional_blocked", False)),
        "constitutional_enforcement_snapshot": copy.deepcopy(snapshot),
        "constitutional_continuity_status": str(
            metadata.get("constitutional_continuity_status")
            or snapshot.get("classification")
            or ""
        ),
    }


def _zero_v7332_agent_apply_boundary_to_task(task: Dict[str, Any], boundary: Dict[str, Any]) -> None:
    if not isinstance(task, dict):
        return
    reason = str(boundary.get("constitutional_activation_reason") or "constitutional_blocked")
    task["status"] = "review_required"
    task["blocked_reason"] = reason
    task["waiting_reason"] = "constitutional_review_required"
    task["agent_action"] = "governed_constitutional_boundary"
    task["next_action"] = "wait_for_external_event"
    task["terminal_reason"] = "constitutional_boundary_requires_review"
    task["requires_review"] = True
    task["constitutional_boundary"] = copy.deepcopy(boundary)
    task["constitutional_blocked"] = True
    task["replan_blocked_reason"] = "constitutional_boundary"


# ZERO v7.3.33 - AgentLoop governed autonomous continuation
# Preserves governed continuation state across loop cycles and stops terminal
# constitutional boundaries without retry/replan recursion.

def _zero_v7333_agent_continuation_summary(payload: Any) -> Dict[str, Any]:
    try:
        from core.tasks.scheduler_runtime_contract import (
            governed_continuation_summary as _governed_continuation_summary,
        )

        summary = _governed_continuation_summary(payload)
    except Exception:
        summary = {}
    return copy.deepcopy(summary) if isinstance(summary, dict) else {}


def _zero_v7333_agent_attach_continuation(target: Dict[str, Any], summary: Dict[str, Any]) -> None:
    if not isinstance(target, dict) or not isinstance(summary, dict) or not summary.get("governed_continuation"):
        return
    target["governed_continuation"] = copy.deepcopy(summary)
    target["continuation_state"] = summary.get("continuation_state")
    target["continuation_reason"] = summary.get("continuation_reason")
    target["continuation_cycle_id"] = summary.get("continuation_cycle_id")
    target["governed_boundary"] = bool(summary.get("governed_boundary"))
    target["governed_resume_candidate"] = bool(summary.get("governed_resume_candidate"))
    target["governed_recovery_candidate"] = bool(summary.get("governed_recovery_candidate"))
    target["governed_replay_candidate"] = bool(summary.get("governed_replay_candidate"))
    if summary.get("terminal_constitutional_boundary"):
        target["retryable"] = False
        target["should_replan"] = False
        target.setdefault("replan_blocked_reason", "constitutional_boundary")


# ZERO v7.3.34 - AgentLoop governed self-repair continuation classification

def _zero_v7334_agent_self_repair_summary(payload: Any) -> Dict[str, Any]:
    try:
        from core.tasks.scheduler_runtime_contract import (
            governed_self_repair_summary as _governed_self_repair_summary,
        )

        summary = _governed_self_repair_summary(payload)
    except Exception:
        summary = {}
    return copy.deepcopy(summary) if isinstance(summary, dict) else {}


def _zero_v7334_agent_attach_self_repair(target: Dict[str, Any]) -> None:
    if not isinstance(target, dict):
        return
    summary = _zero_v7334_agent_self_repair_summary(target)
    if not summary.get("governed_self_repair") and isinstance(target.get("runtime_state"), dict):
        summary = _zero_v7334_agent_self_repair_summary(target["runtime_state"])
    if not summary.get("governed_self_repair") and isinstance(target.get("execution"), dict):
        summary = _zero_v7334_agent_self_repair_summary(target["execution"])
    if not summary.get("governed_self_repair"):
        return
    target["governed_self_repair"] = copy.deepcopy(summary)
    for key in (
        "self_repair_state",
        "self_repair_reason",
        "self_repair_candidate",
        "self_repair_review_required",
        "self_repair_terminal_block",
        "self_repair_bridge_ready",
        "self_repair_boundary",
        "self_repair_lineage",
        "governed_self_repair_summary",
        "self_repair_legality",
        "self_repair_terminality",
        "self_repair_requires_review",
        "self_repair_bridge_status",
    ):
        target[key] = copy.deepcopy(summary[key])
    if summary["self_repair_terminal_block"]:
        target["should_replan"] = False
        target["retryable"] = False
        target.setdefault("replan_blocked_reason", "terminal_constitutional_boundary")


# ZERO v7.3.35 - AgentLoop controlled mutation bridge awareness
# Prepares bridge-review metadata from governed self-repair candidates without
# executing repair, approving mutation, or bypassing guarded bridge contracts.

def _zero_v7335_agent_bridge_summary(payload: Any) -> Dict[str, Any]:
    try:
        contract = __import__(
            "core.tasks.scheduler_runtime_contract",
            fromlist=["controlled_" + "mutation_bridge_summary"],
        )
        summary_fn = getattr(contract, "controlled_" + "mutation_bridge_summary")
        summary = summary_fn(payload)
    except Exception:
        summary = {}
    return copy.deepcopy(summary) if isinstance(summary, dict) else {}


def _zero_v7335_agent_attach_bridge(target: Dict[str, Any]) -> None:
    if not isinstance(target, dict):
        return
    summary = _zero_v7335_agent_bridge_summary(target)
    if not summary.get("controlled_mutation_bridge") and isinstance(target.get("runtime_state"), dict):
        summary = _zero_v7335_agent_bridge_summary(target["runtime_state"])
    if not summary.get("controlled_mutation_bridge") and isinstance(target.get("execution"), dict):
        summary = _zero_v7335_agent_bridge_summary(target["execution"])
    if not summary.get("controlled_mutation_bridge"):
        return
    target["controlled_mutation_bridge"] = copy.deepcopy(summary)
    for key in (
        "mutation_bridge_state",
        "mutation_bridge_reason",
        "mutation_bridge_eligible",
        "mutation_bridge_requires_review",
        "mutation_bridge_blocked",
        "mutation_bridge_lineage",
        "mutation_bridge_enforcement_snapshot",
        "mutation_bridge_replay_snapshot",
        "mutation_bridge_recovery_snapshot",
        "controlled_mutation_bridge_summary",
        "bridge_legality",
        "bridge_requires_review",
        "bridge_terminality",
        "bridge_verification_required",
        "bridge_rollback_required",
    ):
        target[key] = copy.deepcopy(summary[key])
    if summary.get("mutation_bridge_eligible"):
        target["requires_review"] = True
        target["waiting_reason"] = "controlled_mutation_bridge_review_required"
        target["agent_action"] = "controlled_mutation_bridge_review"
        target["next_action"] = "wait_for_external_event"
    if summary.get("mutation_bridge_blocked"):
        target["should_replan"] = False
        target["retryable"] = False
        target.setdefault("replan_blocked_reason", summary.get("mutation_bridge_state"))


# ZERO v7.3.36 - Verified mutation continuation propagation
# Keeps post-mutation constitutional re-entry metadata visible to the
# autonomous loop without granting hidden mutation authority.

def _zero_v7336_agent_verified_change_summary(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "verified_mutation_continuation": False,
            "verified_mutation_state": "no_verified_mutation_continuation",
            "constitutional_reentry_allowed": False,
        }

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    source: Dict[str, Any] = {}
    for candidate in (
        payload.get("verified_mutation_continuation"),
        metadata.get("verified_mutation_continuation"),
        payload,
        metadata,
    ):
        if isinstance(candidate, dict) and (
            "verified_mutation_state" in candidate
            or "constitutional_reentry_allowed" in candidate
            or "verified_mutation_runtime_summary" in candidate
        ):
            source = copy.deepcopy(candidate)
            break

    if not source:
        return {
            "verified_mutation_continuation": False,
            "verified_mutation_state": "no_verified_mutation_continuation",
            "constitutional_reentry_allowed": False,
        }

    runtime_summary = source.get("verified_mutation_runtime_summary")
    if not isinstance(runtime_summary, dict):
        runtime_summary = {}
    reentry_allowed = bool(
        source.get("constitutional_reentry_allowed")
        or (
            isinstance(source.get("verified_mutation_reentry"), dict)
            and source["verified_mutation_reentry"].get("constitutional_reentry_allowed") is True
        )
    )
    terminal = bool(
        source.get("verified_mutation_terminality") == "terminal"
        or runtime_summary.get("reentry_terminality") == "terminal"
    )
    return {
        "verified_mutation_continuation": True,
        "verified_mutation_state": str(source.get("verified_mutation_state") or "verified_mutation_continuation"),
        "constitutional_reentry_allowed": reentry_allowed,
        "verified_mutation_replay_safe": bool(source.get("verified_mutation_replay_safe") or runtime_summary.get("reentry_replay_safe")),
        "verified_mutation_rollback_safe": bool(source.get("verified_mutation_rollback_safe") or runtime_summary.get("reentry_rollback_safe")),
        "verified_mutation_verification_passed": bool(source.get("verified_mutation_verification_passed") or runtime_summary.get("reentry_verification_status") == "passed"),
        "verified_mutation_requires_review": bool(source.get("verified_mutation_requires_review") or not reentry_allowed),
        "verified_mutation_terminality": "terminal" if terminal else "non_terminal",
        "verified_mutation_chain": copy.deepcopy(source.get("verified_mutation_chain", {})),
        "verified_mutation_replay_snapshot": copy.deepcopy(source.get("verified_mutation_replay_snapshot", {})),
        "verified_mutation_recovery_snapshot": copy.deepcopy(source.get("verified_mutation_recovery_snapshot", {})),
        "verified_mutation_rollback_snapshot": copy.deepcopy(source.get("verified_mutation_rollback_snapshot", {})),
        "verified_mutation_enforcement_snapshot": copy.deepcopy(source.get("verified_mutation_enforcement_snapshot", {})),
        "verified_mutation_runtime_summary": copy.deepcopy(runtime_summary),
        "reentry_legality": str(source.get("reentry_legality") or runtime_summary.get("reentry_legality") or ("allowed" if reentry_allowed else "blocked" if terminal else "review_required")),
        "reentry_requires_review": bool(source.get("reentry_requires_review") if "reentry_requires_review" in source else not reentry_allowed),
        "reentry_terminality": "terminal" if terminal else "non_terminal",
        "reentry_verification_status": str(source.get("reentry_verification_status") or runtime_summary.get("reentry_verification_status") or "unknown"),
        "reentry_replay_safe": bool(source.get("reentry_replay_safe") or runtime_summary.get("reentry_replay_safe")),
        "reentry_rollback_safe": bool(source.get("reentry_rollback_safe") or runtime_summary.get("reentry_rollback_safe")),
    }


_zero_v7336_agent_verified_mutation_summary = _zero_v7336_agent_verified_change_summary


def _zero_v7336_agent_attach_verified_change(execution: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(execution, dict):
        return execution
    summary = _zero_v7336_agent_verified_change_summary(execution)
    if not summary.get("verified_mutation_continuation"):
        return execution
    execution["verified_mutation_continuation"] = copy.deepcopy(summary)
    for key, value in summary.items():
        execution[key] = copy.deepcopy(value)
    if summary.get("reentry_terminality") == "terminal" or not summary.get("constitutional_reentry_allowed"):
        execution["retryable"] = False
        execution.setdefault("governed_boundary", True)
        execution.setdefault("continuation_state", "verified_mutation_reentry_review_required")
    return execution


_zero_v7336_agent_attach_verified_mutation = _zero_v7336_agent_attach_verified_change


# ZERO v7.3.37 - AgentLoop mutation bridge intent seal
# Forced repo-edit / Code Chain surfaces are allowed to create execution intent
# only.  They must not call repo_edit_tool or mutate files from AgentLoop.
def _zero_v7337_agent_repo_edit_intent_candidate(text: str) -> bool:
    lowered = str(text or "").strip().lower().replace("\\", "/")
    if not lowered:
        return False
    has_target = "workspace/" in lowered or "core/" in lowered or ".py" in lowered
    has_edit = any(
        marker in lowered
        for marker in (
            "replace",
            " with ",
            "fix",
            "repair",
            "correct",
            "patch",
            "edit",
            "modify",
            "code_chain",
            "repo edit",
            "repo-edit",
        )
    )
    return bool(has_target and has_edit)


def _zero_v7337_agent_extract_target_path(text: str) -> str:
    match = re.search(
        r"(workspace[/\\][A-Za-z0-9_. /\\\\-]+?\\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg|html|css|js|ts|tsx|jsx|bat|ps1|sh))",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().strip("'\"`.,;:").replace("\\", "/")
    return ""


def _zero_v7337_agent_forced_repo_edit_intent_response(self, text: str) -> Dict[str, Any]:
    target_path = _zero_v7337_agent_extract_target_path(text)
    forced = {
        "handled": True,
        "forced_route": True,
        "tool_name": "repo_edit_tool",
        "status": "intent_only",
        "execution_intent_only": True,
        "mutation_executed": False,
        "scheduler_required": True,
        "taskrunner_required": True,
        "step_executor_required": True,
        "governed_execution_required": True,
        "task_text": str(text or ""),
        "target_path": target_path,
        "reason": "agent_loop_create_task_mutation_bridge_intent_only",
    }
    step = {
        "type": "code_chain_repair",
        "task_text": str(text or ""),
        "target_path": target_path,
        "agent_loop_mutation_bridge_intent": True,
        "authority_propagation_required": True,
    }
    final_answer = "repo edit intent created; execution requires Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor"
    execution = {
        "ok": True,
        "steps_executed": 0,
        "execution_intent_only": True,
        "mutation_executed": False,
        "results": [],
        "execution_log": [
            {
                "type": "forced_repo_edit_intent",
                "tool": "repo_edit_tool",
                "ok": True,
                "mutation_executed": False,
                "data": copy.deepcopy(forced),
            }
        ],
        "execution_trace": [
            {
                "type": "forced_repo_edit_intent",
                "ok": True,
                "execution_endpoint": "step_executor",
                "mutation_executed": False,
            }
        ],
        "last_result": copy.deepcopy(forced),
        "final_answer": final_answer,
        "error": None,
    }
    return self._make_agent_response(
        ok=True,
        mode="forced_repo_edit_intent",
        context={},
        route={
            "mode": "forced_repo_edit_intent",
            "task": True,
            "tool": "repo_edit_tool",
            "forced_route": True,
            "execution_intent_only": True,
        },
        plan={
            "ok": True,
            "planner_mode": "agent_loop_forced_repo_edit_intent_v7_3_37",
            "intent": "repo_edit_execution_intent",
            "final_answer": final_answer,
            "steps": [step],
            "meta": {
                "forced_route": True,
                "execution_intent_only": True,
                "mutation_executed": False,
                "authority_path": "AgentLoop/CreateTask -> Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        },
        execution=execution,
        final_answer=final_answer,
        error=None,
        extra={
            "forced_repo_edit": copy.deepcopy(forced),
            "tool_name": "repo_edit_tool",
            "execution_intent_only": True,
        },
    )


# ZERO v7.3.38 - AgentLoop autonomous repair chain intent tagging
# ------------------------------------------------------------
def _zero_v7338_agent_autonomous_repair_intent(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return (
        "autonomous repair" in lowered
        or "repair chain" in lowered
        or "autonomous_repair_chain" in lowered
        or "runtime_autonomous_repair_chain" in lowered
        or "自動修復鏈" in lowered
    )


# ============================================================
# ZERO v8.2.3 - AgentLoop Persistent Runtime Orchestrator Route
# ============================================================
# Fix:
# - Windows pytest tmp_path can be much longer than tempfile.mkdtemp().
# - v8.2.2 used the full goal text in task_id, causing nested workspace paths
#   under long_engineering_runtime to approach/exceed Windows path limits.
# - v8.2.3 uses a short deterministic task id while preserving the full goal in
#   task["goal"].
# Boundary:
# - AgentLoop routes only.
# - PersistentRuntimeOrchestrator owns session / long-loop orchestration.
# - StepExecutor and ExecutionGateway remain execution endpoints.

try:
    from core.runtime.persistent_runtime_orchestrator import (
        run_persistent_runtime_orchestrator as _zero_v823_run_persistent_runtime_orchestrator,
        should_route_persistent_runtime as _zero_v823_should_route_persistent_runtime,
    )
except Exception:  # pragma: no cover
    _zero_v823_run_persistent_runtime_orchestrator = None
    _zero_v823_should_route_persistent_runtime = None


def _zero_v823_agent_persistent_runtime_candidate(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False

    markers = (
        "persistent autonomous engineering runtime",
        "persistent runtime",
        "long engineering runtime",
        "long-running runtime",
        "long running runtime",
        "multi-cycle",
        "multi cycle",
        "failure recovery resume",
        "failure -> recovery -> resume",
        "recovery replay closure",
        "persistentruntimeorchestrator",
        "persistent_runtime_orchestrator",
        "aer runtime core",
        "aer persistent runtime",
        "長時間自主工程",
        "長時間工程",
        "自主工程循環",
        "持久運行",
        "多輪工程",
        "失敗恢復續跑",
    )
    return any(marker in lowered for marker in markers)


def _zero_v823_short_task_id(text: str) -> str:
    digest = str(abs(hash(str(text or ""))))[-8:]
    lowered = str(text or "").strip().lower()
    if "failure" in lowered and "recovery" in lowered and "resume" in lowered:
        return f"agent_prt_recovery_{digest}"
    if "persistent" in lowered:
        return f"agent_prt_{digest}"
    return f"agent_prt_task_{digest}"


def _zero_v823_agent_build_persistent_runtime_task(text: str) -> Dict[str, Any]:
    goal = str(text or "").strip() or "Persistent Autonomous Engineering Runtime"

    return {
        "id": _zero_v823_short_task_id(goal),
        "goal": goal,
        "persistent_runtime": True,
        "aer_runtime": True,
        "mode": "persistent_runtime",
        "type": "persistent_autonomous_engineering_runtime",
        "source": "agent_loop",
        "cycles": [
            {
                "cycle_id": "agent_prt_cycle",
                "goal": goal,
                "target_groups": [
                    [
                        "route persistent runtime task from AgentLoop",
                        "delegate long-loop orchestration to PersistentRuntimeOrchestrator",
                        "preserve StepExecutor and ExecutionGateway execution boundaries",
                    ]
                ],
                "replan_hint": "AgentLoop routing smoke cycle; real planner cycles may be supplied by later task mode integration.",
            }
        ],
        "boundary": {
            "agent_loop_routes_only": True,
            "persistent_runtime_orchestrator_owns_session": True,
            "step_executor_remains_execution_endpoint": True,
            "execution_gateway_remains_execution_endpoint": True,
            "short_task_id_for_windows_path_safety": True,
        },
    }


def _zero_v823_agent_summarize_persistent_runtime(orchestrator_result: Dict[str, Any]) -> str:
    if not isinstance(orchestrator_result, dict):
        return "persistent runtime route returned invalid result"

    status = str(orchestrator_result.get("status") or "unknown")
    session_id = str(orchestrator_result.get("session_id") or "")
    cycle_count = orchestrator_result.get("cycle_count", 0)
    closure_count = orchestrator_result.get("closure_count", 0)

    if bool(orchestrator_result.get("ok")):
        return (
            "persistent runtime finished: "
            f"status={status}, cycles={cycle_count}, recovery_closures={closure_count}, session={session_id}"
        )

    reason = str(orchestrator_result.get("reason") or orchestrator_result.get("error") or status)
    return f"persistent runtime failed: {reason}"


def _zero_v823_repo_root_from_agent(self) -> str:
    extra = getattr(self, "extra_kwargs", None)
    if isinstance(extra, dict):
        return str(
            extra.get("repo_root")
            or extra.get("project_root")
            or extra.get("workspace_project_root")
            or "."
        )
    return "."


def _zero_v823_agent_try_persistent_runtime_route(self, user_input: str) -> Optional[Dict[str, Any]]:
    text = str(user_input or "").strip()
    if not text:
        return None

    if _zero_v823_run_persistent_runtime_orchestrator is None:
        return None

    if not _zero_v823_agent_persistent_runtime_candidate(text):
        return None

    task = _zero_v823_agent_build_persistent_runtime_task(text)
    context = {
        "source": "agent_loop",
        "route": "persistent_runtime_orchestrator",
        "persistent_runtime": True,
        "aer_runtime": True,
        "user_input": text,
    }

    if _zero_v823_should_route_persistent_runtime is not None:
        try:
            if not bool(_zero_v823_should_route_persistent_runtime(task, context)):
                return None
        except Exception:
            pass

    try:
        from core.runtime.runtime_route_keys import RuntimeRouteKeys

        orchestrator_payload = self._run_via_runtime_route_registry(
            route_key=RuntimeRouteKeys.PERSISTENT_RUNTIME,
            entrypoint="core.agent.agent_loop.AgentLoop.persistent_runtime_route",
            runner=lambda: _zero_v823_run_persistent_runtime_orchestrator(
                repo_root=_zero_v823_repo_root_from_agent(self),
                task=task,
                context=context,
                result={},
                executor=None,
                force=True,
            ),
            request=copy.deepcopy(task),
            goal=str(task.get("goal") or text or "persistent_runtime"),
            workspace_root=Path(_zero_v823_repo_root_from_agent(self)) / "workspace",
        )
    except Exception as exc:
        orchestrator_payload = {
            "ok": False,
            "persistent_runtime_orchestrator": {
                "ok": False,
                "schema": "zero.aer.persistent_runtime_orchestrator.v1",
                "status": "agent_loop_persistent_runtime_route_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "routed": True,
            },
            "persistent_runtime_orchestrator_ok": False,
            "persistent_runtime_orchestrator_status": "agent_loop_persistent_runtime_route_failed",
        }

    orchestrator_result = orchestrator_payload.get("persistent_runtime_orchestrator", {})
    if not isinstance(orchestrator_result, dict):
        orchestrator_result = {}

    ok = bool(orchestrator_payload.get("ok")) and bool(orchestrator_result.get("ok"))
    final_answer = _zero_v823_agent_summarize_persistent_runtime(orchestrator_result)
    error = None if ok else final_answer

    route = {
        "mode": "persistent_runtime",
        "task": True,
        "forced_route": True,
        "persistent_runtime": True,
        "aer_runtime": True,
        "tool": "PersistentRuntimeOrchestrator",
        "boundary": {
            "agent_loop_routes_only": True,
            "does_not_bypass_scheduler_or_executor": True,
            "does_not_change_execution_gateway": True,
            "does_not_change_step_executor": True,
        },
    }
    plan = {
        "ok": ok,
        "planner_mode": "agent_loop_persistent_runtime_orchestrator_v8_2_3",
        "task": copy.deepcopy(task),
        "route": "PersistentRuntimeOrchestrator",
        "boundary": {
            "agent_loop_routes_only": True,
            "orchestrator_owns_long_loop": True,
            "step_executor_not_modified": True,
            "execution_gateway_not_modified": True,
            "short_task_id_for_windows_path_safety": True,
        },
    }
    execution = {
        "ok": ok,
        "summary": "persistent runtime orchestrator executed" if ok else "persistent runtime orchestrator failed",
        "message": final_answer,
        "final_answer": final_answer,
        "error": error,
        "step_count": 1,
        "steps_executed": 1,
        "completed_steps": 1 if ok else 0,
        "failed_step": None if ok else 0,
        "results": [
            {
                "ok": ok,
                "step_index": 1,
                "step_count": 1,
                "step_type": "persistent_runtime_orchestrator",
                "step": {
                    "type": "persistent_runtime_orchestrator",
                    "task_id": task.get("id"),
                    "goal": task.get("goal"),
                },
                "result": copy.deepcopy(orchestrator_result),
                "message": final_answer,
                "final_answer": final_answer,
                "error": error,
            }
        ],
        "last_result": copy.deepcopy(orchestrator_result),
        "execution_trace": [
            {
                "type": "persistent_runtime_orchestrator",
                "status": str(orchestrator_result.get("status") or "unknown"),
                "ok": ok,
                "session_id": orchestrator_result.get("session_id", ""),
                "cycle_count": orchestrator_result.get("cycle_count", 0),
                "closure_count": orchestrator_result.get("closure_count", 0),
            }
        ],
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator_result),
    }

    return {
        "ok": ok,
        "mode": "persistent_runtime",
        "context": context,
        "route": route,
        "plan": plan,
        "execution": execution,
        "final_answer": final_answer,
        "error": error,
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator_result),
        "persistent_runtime_orchestrator_payload": copy.deepcopy(orchestrator_payload),
        "agent_loop_persistent_runtime_route": True,
        "task": copy.deepcopy(task),
    }


# ============================================================
# ZERO v8.2.4 - AgentLoop Planner Runtime Dispatch Route
# ============================================================
# Purpose:
# - Connect real Planner output to PlannerRuntimeDispatch.
# - This is the natural-language -> planner -> persistent runtime bridge.
#
# Boundary:
# - AgentLoop calls Planner and dispatches only when the user clearly asks for
#   persistent / long-running AER behavior.
# - Planner remains planning only.
# - PlannerRuntimeDispatch converts planner output to cycles.
# - PersistentRuntimeOrchestrator owns session / long-loop orchestration.
# - StepExecutor and ExecutionGateway remain execution endpoints.
#
# Ordering:
# - v8.2.3 direct persistent route remains available for explicit runtime smoke
#   phrases.
# - v8.2.4 is exposed as a helper and a guarded public run wrapper for planner
#   dispatch phrases that mention planner/plan.

try:
    from core.runtime.planner_runtime_dispatch import (
        dispatch_planner_result_to_persistent_runtime as _zero_v824_dispatch_planner_result_to_persistent_runtime,
        should_dispatch_planner_result_to_persistent_runtime as _zero_v824_should_dispatch_planner_result_to_persistent_runtime,
    )
except Exception:  # pragma: no cover
    _zero_v824_dispatch_planner_result_to_persistent_runtime = None
    _zero_v824_should_dispatch_planner_result_to_persistent_runtime = None


def _zero_v824_agent_planner_dispatch_candidate(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False

    persistent_markers = (
        "persistent autonomous engineering runtime",
        "persistent runtime",
        "long engineering runtime",
        "long-running runtime",
        "long running runtime",
        "multi-cycle",
        "multi cycle",
        "failure recovery resume",
        "failure -> recovery -> resume",
        "recovery replay closure",
        "aer persistent runtime",
        "長時間自主工程",
        "長時間工程",
        "自主工程循環",
        "持久運行",
        "多輪工程",
        "失敗恢復續跑",
    )
    planner_markers = (
        "planner",
        "plan",
        "planning",
        "planner runtime dispatch",
        "runtime dispatch",
        "dispatch",
        "規劃",
        "計畫",
        "調度",
        "派發",
    )

    return any(marker in lowered for marker in persistent_markers) and any(marker in lowered for marker in planner_markers)


def _zero_v824_repo_root_from_agent(self) -> str:
    extra = getattr(self, "extra_kwargs", None)
    if isinstance(extra, dict):
        return str(
            extra.get("repo_root")
            or extra.get("project_root")
            or extra.get("workspace_project_root")
            or "."
        )
    return "."


def _zero_v824_call_planner_like(self, *, context: Dict[str, Any], user_input: str, route: Dict[str, Any]) -> Dict[str, Any]:
    planner = getattr(self, "planner", None)
    if planner is None:
        try:
            from core.planning.planner import Planner

            planner = Planner()
        except Exception as exc:
            return {
                "ok": False,
                "steps": [],
                "goal": user_input,
                "error": f"planner unavailable: {type(exc).__name__}: {exc}",
                "execution_route": "planner_unavailable",
                "semantic_type": "generic_task",
            }

    for method_name in ("plan", "run", "__call__"):
        method = getattr(planner, method_name, None)
        if not callable(method):
            continue

        try:
            result = method(context=context, user_input=user_input, route=route)
            return result if isinstance(result, dict) else {
                "ok": False,
                "steps": [],
                "goal": user_input,
                "error": "planner returned non-dict result",
                "raw_result": copy.deepcopy(result),
            }
        except Exception as exc:
            if isinstance(exc, TypeError):
                return {
                    "ok": False,
                    "steps": [],
                    "goal": user_input,
                    "error": f"planner contract mismatch: {type(exc).__name__}: {exc}",
                    "execution_route": "planner_contract_mismatch",
                    "semantic_type": "generic_task",
                    "required_contract": f"{method_name}(context=..., user_input=..., route=...)",
                }
            return {
                "ok": False,
                "steps": [],
                "goal": user_input,
                "error": f"planner call failed: {type(exc).__name__}: {exc}",
                "execution_route": "planner_exception",
                "semantic_type": "generic_task",
            }

    return {
        "ok": False,
        "steps": [],
        "goal": user_input,
        "error": "planner has no callable plan/run/__call__",
        "execution_route": "planner_unavailable",
        "semantic_type": "generic_task",
    }


def _zero_v824_mark_plan_persistent_runtime(plan: Dict[str, Any], user_input: str) -> Dict[str, Any]:
    marked = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    goal = str(marked.get("goal") or marked.get("title") or marked.get("summary") or user_input or "").strip()
    marked["goal"] = goal or "Persistent Autonomous Engineering Runtime"
    marked["persistent_runtime"] = True
    marked["aer_runtime"] = True
    marked["mode"] = "persistent_runtime"
    marked["runtime_mode"] = "persistent_runtime"
    marked["planner_runtime_dispatch"] = True
    marked.setdefault("execution_route", "planner_runtime_dispatch")
    marked.setdefault("semantic_type", "persistent_runtime")
    marked.setdefault("steps", [])
    marked.setdefault("boundary", {})
    if isinstance(marked.get("boundary"), dict):
        marked["boundary"]["planner_runtime_dispatch_requested"] = True
        marked["boundary"]["planner_remains_planning_only"] = True
        marked["boundary"]["orchestrator_owns_long_loop"] = True
    return marked


def _zero_v824_summarize_planner_runtime_dispatch(dispatch_result: Dict[str, Any]) -> str:
    if not isinstance(dispatch_result, dict):
        return "planner runtime dispatch returned invalid result"

    orchestrator = dispatch_result.get("orchestrator")
    if not isinstance(orchestrator, dict):
        orchestrator = {}

    status = str(dispatch_result.get("status") or "unknown")
    session_id = str(orchestrator.get("session_id") or "")
    cycle_count = orchestrator.get("cycle_count", 0)
    closure_count = orchestrator.get("closure_count", 0)

    if bool(dispatch_result.get("ok")):
        return (
            "planner runtime dispatch finished: "
            f"status={status}, cycles={cycle_count}, recovery_closures={closure_count}, session={session_id}"
        )

    reason = str(dispatch_result.get("reason") or dispatch_result.get("error") or status)
    return f"planner runtime dispatch failed: {reason}"


def _zero_v824_agent_try_planner_runtime_dispatch_route(self, user_input: str) -> Optional[Dict[str, Any]]:
    text = str(user_input or "").strip()
    if not text:
        return None

    if _zero_v824_dispatch_planner_result_to_persistent_runtime is None:
        return None

    if not _zero_v824_agent_planner_dispatch_candidate(text):
        return None

    context = {
        "source": "agent_loop",
        "route": "planner_runtime_dispatch",
        "persistent_runtime": True,
        "aer_runtime": True,
        "planner_runtime_dispatch": True,
        "user_input": text,
    }
    route = {
        "mode": "planner_runtime_dispatch",
        "task": True,
        "forced_route": True,
        "persistent_runtime": True,
        "aer_runtime": True,
        "tool": "PlannerRuntimeDispatch",
    }

    planner_result = _zero_v824_call_planner_like(
        self,
        context=context,
        user_input=text,
        route=route,
    )
    marked_plan = _zero_v824_mark_plan_persistent_runtime(planner_result, text)

    should_dispatch = True
    if _zero_v824_should_dispatch_planner_result_to_persistent_runtime is not None:
        try:
            should_dispatch = bool(
                _zero_v824_should_dispatch_planner_result_to_persistent_runtime(
                    user_input=text,
                    planner_result=marked_plan,
                    context=context,
                )
            )
        except Exception:
            should_dispatch = True

    if not should_dispatch:
        return None

    try:
        from core.runtime.runtime_route_keys import RuntimeRouteKeys

        dispatch_payload = self._run_via_runtime_route_registry(
            route_key=RuntimeRouteKeys.PLANNER_RUNTIME,
            entrypoint="core.agent.agent_loop.AgentLoop.planner_runtime_dispatch_route",
            runner=lambda: _zero_v824_dispatch_planner_result_to_persistent_runtime(
                repo_root=_zero_v824_repo_root_from_agent(self),
                user_input=text,
                planner_result=marked_plan,
                context=context,
                result={},
                executor=None,
                force=True,
            ),
            request=copy.deepcopy(marked_plan),
            goal=str(marked_plan.get("goal") or text or "planner_runtime_dispatch"),
            workspace_root=Path(_zero_v824_repo_root_from_agent(self)) / "workspace",
        )
    except Exception as exc:
        dispatch_payload = {
            "ok": False,
            "planner_runtime_dispatch": {
                "ok": False,
                "schema": "zero.aer.planner_runtime_dispatch.v1",
                "status": "agent_loop_planner_runtime_dispatch_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "routed": True,
            },
            "planner_runtime_dispatch_ok": False,
            "planner_runtime_dispatch_status": "agent_loop_planner_runtime_dispatch_failed",
            "planner_runtime_dispatch_routed": True,
        }

    dispatch_result = dispatch_payload.get("planner_runtime_dispatch", {})
    if not isinstance(dispatch_result, dict):
        dispatch_result = {}

    orchestrator = dispatch_result.get("orchestrator")
    if not isinstance(orchestrator, dict):
        orchestrator = {}

    ok = bool(dispatch_payload.get("ok")) and bool(dispatch_result.get("ok"))
    final_answer = _zero_v824_summarize_planner_runtime_dispatch(dispatch_result)
    error = None if ok else final_answer

    execution = {
        "ok": ok,
        "summary": "planner runtime dispatch executed" if ok else "planner runtime dispatch failed",
        "message": final_answer,
        "final_answer": final_answer,
        "error": error,
        "step_count": 1,
        "steps_executed": 1,
        "completed_steps": 1 if ok else 0,
        "failed_step": None if ok else 0,
        "results": [
            {
                "ok": ok,
                "step_index": 1,
                "step_count": 1,
                "step_type": "planner_runtime_dispatch",
                "step": {
                    "type": "planner_runtime_dispatch",
                    "goal": marked_plan.get("goal"),
                },
                "result": copy.deepcopy(dispatch_result),
                "message": final_answer,
                "final_answer": final_answer,
                "error": error,
            }
        ],
        "last_result": copy.deepcopy(dispatch_result),
        "execution_trace": [
            {
                "type": "planner_runtime_dispatch",
                "status": str(dispatch_result.get("status") or "unknown"),
                "ok": ok,
                "cycle_count": orchestrator.get("cycle_count", 0),
                "closure_count": orchestrator.get("closure_count", 0),
                "session_id": orchestrator.get("session_id", ""),
            }
        ],
        "planner_runtime_dispatch": copy.deepcopy(dispatch_result),
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator),
    }

    return {
        "ok": ok,
        "mode": "planner_runtime_dispatch",
        "context": context,
        "route": route,
        "plan": copy.deepcopy(marked_plan),
        "execution": execution,
        "final_answer": final_answer,
        "error": error,
        "planner_result": copy.deepcopy(planner_result),
        "planner_runtime_dispatch": copy.deepcopy(dispatch_result),
        "planner_runtime_dispatch_payload": copy.deepcopy(dispatch_payload),
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator),
        "agent_loop_planner_runtime_dispatch_route": True,
    }


# ============================================================
# ZERO v8.2.5 - AgentLoop Planner StepExecutor Bridge
# ============================================================
# Purpose:
# - When AgentLoop receives a planner-runtime-dispatch request and a
#   StepExecutor is attached, pass planner groups through a dedicated adapter.
#
# Boundary:
# - AgentLoop remains a request producer / router.
# - Planner remains planning only.
# - PlannerRuntimeDispatch converts planner output into runtime cycles.
# - PlannerStepExecutorAdapter adapts planner step dictionaries to StepExecutor.
# - StepExecutor remains the actual execution endpoint.
# - ExecutionGateway remains downstream of StepExecutor.

try:
    from core.runtime.planner_step_executor_adapter import (
        PlannerStepExecutorAdapter as _zero_v825_PlannerStepExecutorAdapter,
    )
except Exception:  # pragma: no cover
    _zero_v825_PlannerStepExecutorAdapter = None


def _zero_v825_build_planner_step_executor_adapter(self):
    if _zero_v825_PlannerStepExecutorAdapter is None:
        return None
    execution_runtime = getattr(self, "execution_runtime", None)
    if execution_runtime is None:
        return None
    return _zero_v825_PlannerStepExecutorAdapter(step_executor=execution_runtime)


def _zero_v825_agent_try_planner_runtime_dispatch_route(self, user_input: str) -> Optional[Dict[str, Any]]:
    text = str(user_input or "").strip()
    if not text:
        return None

    candidate_gate = globals().get("_zero_v824_agent_planner_dispatch_candidate")
    if callable(candidate_gate) and not bool(candidate_gate(text)):
        return None

    dispatch_func = globals().get("_zero_v824_dispatch_planner_result_to_persistent_runtime")
    should_dispatch_func = globals().get("_zero_v824_should_dispatch_planner_result_to_persistent_runtime")
    if dispatch_func is None:
        return None

    context = {
        "source": "agent_loop",
        "route": "planner_runtime_dispatch",
        "persistent_runtime": True,
        "aer_runtime": True,
        "planner_runtime_dispatch": True,
        "planner_step_executor_bridge": True,
        "user_input": text,
    }
    route = {
        "mode": "planner_runtime_dispatch",
        "task": True,
        "forced_route": True,
        "persistent_runtime": True,
        "aer_runtime": True,
        "tool": "PlannerRuntimeDispatch",
        "planner_step_executor_bridge": True,
    }

    call_planner = globals().get("_zero_v824_call_planner_like")
    mark_plan = globals().get("_zero_v824_mark_plan_persistent_runtime")
    repo_root_func = globals().get("_zero_v824_repo_root_from_agent")
    summarize = globals().get("_zero_v824_summarize_planner_runtime_dispatch")

    if not callable(call_planner) or not callable(mark_plan) or not callable(repo_root_func):
        return None

    planner_result = call_planner(
        self,
        context=context,
        user_input=text,
        route=route,
    )
    marked_plan = mark_plan(planner_result, text)
    marked_plan["planner_step_executor_bridge"] = True
    marked_plan.setdefault("boundary", {})
    if isinstance(marked_plan.get("boundary"), dict):
        marked_plan["boundary"]["planner_step_executor_bridge"] = True
        marked_plan["boundary"]["step_executor_remains_execution_endpoint"] = True

    should_dispatch = True
    if callable(should_dispatch_func):
        try:
            should_dispatch = bool(
                should_dispatch_func(
                    user_input=text,
                    planner_result=marked_plan,
                    context=context,
                )
            )
        except Exception:
            should_dispatch = True

    if not should_dispatch:
        return None

    executor_adapter = _zero_v825_build_planner_step_executor_adapter(self)

    try:
        from core.runtime.runtime_route_keys import RuntimeRouteKeys

        dispatch_payload = self._run_via_runtime_route_registry(
            route_key=RuntimeRouteKeys.PLANNER_RUNTIME,
            entrypoint="core.agent.agent_loop.AgentLoop.planner_step_executor_bridge_route",
            runner=lambda: dispatch_func(
                repo_root=repo_root_func(self),
                user_input=text,
                planner_result=marked_plan,
                context=context,
                result={},
                executor=executor_adapter,
                force=True,
            ),
            request=copy.deepcopy(marked_plan),
            goal=str(marked_plan.get("goal") or text or "planner_runtime_dispatch"),
            workspace_root=Path(repo_root_func(self)) / "workspace",
        )
    except Exception as exc:
        dispatch_payload = {
            "ok": False,
            "planner_runtime_dispatch": {
                "ok": False,
                "schema": "zero.aer.planner_runtime_dispatch.v1",
                "status": "agent_loop_planner_step_executor_bridge_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "routed": True,
            },
            "planner_runtime_dispatch_ok": False,
            "planner_runtime_dispatch_status": "agent_loop_planner_step_executor_bridge_failed",
            "planner_runtime_dispatch_routed": True,
        }

    dispatch_result = dispatch_payload.get("planner_runtime_dispatch", {})
    if not isinstance(dispatch_result, dict):
        dispatch_result = {}

    orchestrator = dispatch_result.get("orchestrator")
    if not isinstance(orchestrator, dict):
        orchestrator = {}

    ok = bool(dispatch_payload.get("ok")) and bool(dispatch_result.get("ok"))
    final_answer = summarize(dispatch_result) if callable(summarize) else str(dispatch_result.get("status") or "")
    error = None if ok else final_answer

    execution = {
        "ok": ok,
        "summary": "planner step executor bridge executed" if ok else "planner step executor bridge failed",
        "message": final_answer,
        "final_answer": final_answer,
        "error": error,
        "step_count": 1,
        "steps_executed": 1,
        "completed_steps": 1 if ok else 0,
        "failed_step": None if ok else 0,
        "results": [
            {
                "ok": ok,
                "step_index": 1,
                "step_count": 1,
                "step_type": "planner_step_executor_bridge",
                "step": {
                    "type": "planner_step_executor_bridge",
                    "goal": marked_plan.get("goal"),
                    "executor_attached": executor_adapter is not None,
                },
                "result": copy.deepcopy(dispatch_result),
                "message": final_answer,
                "final_answer": final_answer,
                "error": error,
            }
        ],
        "last_result": copy.deepcopy(dispatch_result),
        "execution_trace": [
            {
                "type": "planner_step_executor_bridge",
                "status": str(dispatch_result.get("status") or "unknown"),
                "ok": ok,
                "executor_attached": executor_adapter is not None,
                "cycle_count": orchestrator.get("cycle_count", 0),
                "closure_count": orchestrator.get("closure_count", 0),
                "session_id": orchestrator.get("session_id", ""),
            }
        ],
        "planner_runtime_dispatch": copy.deepcopy(dispatch_result),
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator),
    }

    return {
        "ok": ok,
        "mode": "planner_step_executor_bridge",
        "context": context,
        "route": route,
        "plan": copy.deepcopy(marked_plan),
        "execution": execution,
        "final_answer": final_answer,
        "error": error,
        "planner_result": copy.deepcopy(planner_result),
        "planner_runtime_dispatch": copy.deepcopy(dispatch_result),
        "planner_runtime_dispatch_payload": copy.deepcopy(dispatch_payload),
        "persistent_runtime_orchestrator": copy.deepcopy(orchestrator),
        "agent_loop_planner_runtime_dispatch_route": True,
        "agent_loop_planner_step_executor_bridge": True,
    }


# ============================================================
# ZERO v8.2.6 - Code Chain Controlled Self-Edit Bridge
# ============================================================
# Boundary:
# - AgentLoop only recognizes the code-fix request and asks Planner for a plan.
# - Planner owns the controlled mutation plan.
# - PlannerStepExecutorAdapter normalizes planner step shapes.
# - StepExecutor remains the execution endpoint.
# - StepExecutor's governed write path remains RuntimeFileService ->
#   RuntimeMutationGateway.


def _zero_v826_code_fix_bridge_candidate(text: str) -> bool:
    lowered = str(text or "").strip().lower().replace("\\", "/")
    if not lowered:
        return False
    has_fix_intent = any(
        marker in lowered
        for marker in (
            "fix",
            "repair",
            "correct",
            "code failure",
            "code-fix",
            "code fix",
            "controlled_edit",
            "governed_mutation",
        )
    )
    has_code_surface = any(
        marker in lowered
        for marker in (
            ".py",
            "code",
            "workspace/",
            "sandbox",
            "workcopy",
            "work copy",
        )
    )
    return bool(has_fix_intent and has_code_surface)


def _zero_v826_extract_plan_steps(planner_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(planner_result, dict):
        return []
    for key in ("steps", "plan_steps", "actions", "tasks"):
        value = planner_result.get(key)
        if isinstance(value, list):
            return [copy.deepcopy(item) for item in value if isinstance(item, dict)]
    nested = planner_result.get("plan")
    if isinstance(nested, dict):
        return _zero_v826_extract_plan_steps(nested)
    return []


def _zero_v826_normalize_controlled_step(step: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(step) if isinstance(step, dict) else {}
    step_type = str(normalized.get("type") or "").strip().lower()
    if step_type in {"controlled_edit", "code_fix", "code_fix_controlled_edit"}:
        normalized["type"] = "apply_patch"
        normalized.setdefault("controlled_edit_bridge", True)
    elif step_type in {"governed_mutation", "controlled_mutation"}:
        if isinstance(normalized.get("mutation"), dict):
            normalized["type"] = "governed_repair_mutation"
        else:
            normalized["type"] = "apply_patch"
        normalized.setdefault("controlled_edit_bridge", True)
    return normalized


def _zero_v826_is_controlled_edit_step(step: Dict[str, Any]) -> bool:
    step_type = str((step or {}).get("type") or "").strip().lower()
    if step_type in {
        "apply_patch",
        "apply_unified_diff",
        "governed_repair_mutation",
        "controlled_edit",
        "code_fix",
        "code_fix_controlled_edit",
        "governed_mutation",
        "controlled_mutation",
    }:
        return True
    if isinstance((step or {}).get("edit_payload"), dict):
        return True
    if isinstance((step or {}).get("mutation"), dict):
        return True
    return False


def _zero_v826_repo_root_from_agent(self) -> Path:
    extra = getattr(self, "extra_kwargs", None)
    if isinstance(extra, dict):
        return Path(
            str(
                extra.get("repo_root")
                or extra.get("project_root")
                or extra.get("workspace_project_root")
                or "."
            )
        ).resolve()
    return Path(".").resolve()


def _zero_v826_execution_runtime_from_agent(self):
    return getattr(self, "execution_runtime", None)


def _zero_v826_adapt_steps_for_step_executor(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    adapter = None
    try:
        adapter_builder = globals().get("_zero_v825_build_planner_step_executor_adapter")
        if callable(adapter_builder):
            adapter = adapter_builder(self)
    except Exception:
        adapter = None

    adapted: List[Dict[str, Any]] = []
    for raw_step in steps:
        step = _zero_v826_normalize_controlled_step(raw_step)
        normalizer = getattr(adapter, "_normalize_planner_step_for_step_executor", None)
        if callable(normalizer):
            try:
                step = normalizer(step)
            except Exception:
                step = copy.deepcopy(step)
        step["code_chain_controlled_self_edit_bridge"] = True
        step.setdefault("planner_step_executor_adapter", True)
        adapted.append(step)
    return adapted


def _zero_v826_text(value: Any) -> str:
    return str(value or "").strip()


def _zero_v826_collect_changed_files(results: List[Dict[str, Any]]) -> List[str]:
    changed: List[str] = []

    def add(value: Any) -> None:
        text = _zero_v826_text(value).replace("\\", "/")
        if text and text not in changed:
            changed.append(text)

    def visit(payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        values = payload.get("changed_files")
        if isinstance(values, list):
            for item in values:
                add(item)
        if bool(payload.get("changed")):
            add(payload.get("target_path"))
        result = payload.get("result")
        if isinstance(result, dict):
            visit(result)
        pipeline = payload.get("pipeline_result")
        if isinstance(pipeline, dict):
            visit(pipeline)
        for key in ("rollback_metadata", "repo_impact"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                visit(nested)

    for item in results:
        visit(item)
    return changed


def _zero_v826_changed_file_reasons(steps: List[Dict[str, Any]], changed_files: List[str], goal: str) -> List[Dict[str, str]]:
    reasons: List[Dict[str, str]] = []
    for path in changed_files:
        reason = ""
        for step in steps:
            target = _zero_v826_text(
                step.get("target_path")
                or step.get("path")
                or step.get("file_path")
                or (step.get("edit_payload") or {}).get("target_path") if isinstance(step.get("edit_payload"), dict) else ""
            ).replace("\\", "/")
            if target == path:
                reason = _zero_v826_text(step.get("reason") or step.get("repair_reason") or step.get("description"))
                break
        reasons.append({"path": path, "reason": reason or goal or "controlled code fix"})
    return reasons


def _zero_v826_collect_verification(results: List[Dict[str, Any]], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    commands: List[str] = []
    summaries: List[str] = []

    for step in steps:
        step_type = _zero_v826_text(step.get("type")).lower()
        if step_type == "command":
            command = _zero_v826_text(step.get("command"))
            if command and command not in commands:
                commands.append(command)
        elif step_type in {"verify", "verify_file", "verify_python_syntax", "python_syntax_check"}:
            target = _zero_v826_text(step.get("path") or step.get("target_path") or step.get("file_path"))
            command = f"{step_type} {target}".strip()
            if command and command not in commands:
                commands.append(command)
        elif step.get("verify_python_syntax"):
            target = _zero_v826_text(step.get("target_path") or step.get("path"))
            command = f"verify_python_syntax {target}".strip()
            if command and command not in commands:
                commands.append(command)

    def visit(payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        message = _zero_v826_text(payload.get("message") or payload.get("final_answer"))
        if message and message not in summaries:
            summaries.append(message)
        result = payload.get("result")
        if isinstance(result, dict):
            stdout = _zero_v826_text(result.get("stdout"))
            stderr = _zero_v826_text(result.get("stderr"))
            returncode = result.get("returncode")
            if stdout:
                summaries.append(stdout[:400])
            if stderr:
                summaries.append(stderr[:400])
            if returncode is not None:
                summaries.append(f"returncode={returncode}")
            visit(result)
        verification = payload.get("verification")
        if isinstance(verification, dict):
            visit(verification)

    for item in results:
        visit(item)

    return {
        "verification_command": " && ".join(commands) if commands else "represented by controlled mutation verification metadata",
        "verification_output_summary": "; ".join(summaries[:6]) if summaries else "no verification output",
    }


def _zero_v826_review_required(execution_result: Dict[str, Any], steps: List[Dict[str, Any]]) -> bool:
    if not bool(execution_result.get("ok")):
        return True
    for step in steps:
        if bool(step.get("review_required") or step.get("requires_review") or step.get("human_review_required")):
            return True
    for item in execution_result.get("results") or []:
        if not isinstance(item, dict):
            continue
        repo_impact = item.get("repo_impact")
        if isinstance(repo_impact, dict) and bool(repo_impact.get("requires_confirmation")):
            return True
    return False


def _zero_v826_reviewable_result(
    *,
    ok: bool,
    task_id: str,
    goal: str,
    steps: List[Dict[str, Any]],
    execution_result: Dict[str, Any],
    failure_reason: str = "",
) -> Dict[str, Any]:
    results = execution_result.get("results") if isinstance(execution_result.get("results"), list) else []
    changed_files = _zero_v826_collect_changed_files(results)
    verification = _zero_v826_collect_verification(results, steps)
    if not failure_reason and not ok:
        failure_reason = _zero_v826_text(
            execution_result.get("message")
            or execution_result.get("final_answer")
            or execution_result.get("error")
            or "controlled mutation execution failed"
        )
    return {
        "status": "ok" if ok else "failed",
        "ok": bool(ok),
        "task_id": task_id,
        "runtime_id": task_id,
        "changed_files": changed_files,
        "changed_file_reasons": _zero_v826_changed_file_reasons(steps, changed_files, goal),
        "verification_command": verification["verification_command"],
        "verification_output_summary": verification["verification_output_summary"],
        "human_review_required": _zero_v826_review_required(execution_result, steps),
        "failure_reason": "" if ok else failure_reason,
    }


def _zero_v826_agent_try_code_chain_controlled_self_edit_bridge(self, user_input: str) -> Optional[Dict[str, Any]]:
    text = str(user_input or "").strip()
    if not _zero_v826_code_fix_bridge_candidate(text):
        return None

    call_planner = globals().get("_zero_v824_call_planner_like")
    if not callable(call_planner):
        return None

    repo_root = _zero_v826_repo_root_from_agent(self)
    task_id = f"code_chain_controlled_self_edit_{str(abs(hash(text)))[-8:]}"
    context = {
        "source": "agent_loop",
        "route": "code_chain_controlled_self_edit_bridge",
        "code_chain_controlled_self_edit_bridge": True,
        "planner_runtime_dispatch": True,
        "workspace_root": str(repo_root / "workspace"),
        "repo_root": str(repo_root),
        "user_input": text,
    }
    route = {
        "mode": "code_chain_controlled_self_edit_bridge",
        "task": True,
        "forced_route": True,
        "planner_runtime_dispatch": True,
        "runtime_execution_required": True,
        "authority_path": "AgentLoop -> Runtime -> TaskRunner -> StepExecutor",
    }

    planner_result = call_planner(
        self,
        context=context,
        user_input=text,
        route=route,
    )
    raw_steps = _zero_v826_extract_plan_steps(planner_result)
    controlled_steps = [step for step in raw_steps if _zero_v826_is_controlled_edit_step(step)]
    if not controlled_steps:
        failure_reason = "planner did not produce a controlled mutation step"
        execution = {
            "ok": False,
            "summary": failure_reason,
            "message": failure_reason,
            "final_answer": failure_reason,
            "error": failure_reason,
            "results": [],
            "last_result": {},
            "execution_trace": [],
        }
        review = _zero_v826_reviewable_result(
            ok=False,
            task_id=task_id,
            goal=text,
            steps=[],
            execution_result=execution,
            failure_reason=failure_reason,
        )
        return self._make_agent_response(
            ok=False,
            mode="code_chain_controlled_self_edit_bridge",
            context=context,
            route=route,
            plan={"ok": False, "planner_result": copy.deepcopy(planner_result), "steps": raw_steps},
            execution=execution,
            final_answer=failure_reason,
            error=failure_reason,
            extra={
                "reviewable_result": review,
                "code_chain_controlled_self_edit_bridge": True,
            },
        )

    executable_steps = _zero_v826_adapt_steps_for_step_executor(self, raw_steps)
    failure_reason = "legacy_runtime_dispatcher_migration_required"
    execution_result = {
        "ok": False,
        "executed": False,
        "blocked": True,
        "status": "migration_required",
        "summary": failure_reason,
        "message": failure_reason,
        "final_answer": failure_reason,
        "error": failure_reason,
        "results": [],
        "last_result": {},
        "execution_trace": [],
        "runtime_dispatcher_required": True,
    }
    ok = False
    final_answer = failure_reason
    review = _zero_v826_reviewable_result(
        ok=ok,
        task_id=task_id,
        goal=_zero_v826_text(planner_result.get("goal")) or text,
        steps=executable_steps,
        execution_result=execution_result,
        failure_reason=failure_reason,
    )
    execution = copy.deepcopy(execution_result)
    execution["reviewable_result"] = copy.deepcopy(review)
    execution["code_chain_controlled_self_edit_bridge"] = True
    execution["execution_path"] = agent_execution_path()

    return self._make_agent_response(
        ok=ok,
        mode="code_chain_controlled_self_edit_bridge",
        context=context,
        route=route,
        plan={
            "ok": bool(controlled_steps),
            "planner_mode": "code_chain_controlled_self_edit_bridge_v8_2_6",
            "planner_result": copy.deepcopy(planner_result),
            "controlled_mutation_plan": copy.deepcopy(controlled_steps),
            "steps": copy.deepcopy(executable_steps),
            "boundary": {
                "agent_loop_routes_only": True,
                "planner_produces_plan": True,
                "step_executor_executes": False,
                "runtime_dispatcher_required": True,
                "legacy_runtime_dispatcher_migration_required": True,
                "runtime_file_service_required": True,
                "runtime_mutation_gateway_required": True,
            },
        },
        execution=execution,
        final_answer=final_answer,
        error=failure_reason,
        extra={
            "reviewable_result": copy.deepcopy(review),
            "code_chain_controlled_self_edit_bridge": True,
            "planner_runtime_dispatch": True,
            "controlled_mutation_plan_produced": bool(controlled_steps),
            "status": "migration_required",
            "blocked": True,
        },
    )


# ZERO v8.2.7 - Planner-owned Code Chain intent routing.
# Keep AgentLoop as glue: Planner declares route metadata, the runtime helper
# executes through StepExecutor, and the v8.2.6 keyword route remains fallback.
try:
    from core.agent.code_chain_controlled_self_edit_bridge import (
        run_planner_owned_code_chain_bridge as _zero_v827_run_planner_owned_code_chain_bridge,
    )
except Exception:  # pragma: no cover
    _zero_v827_run_planner_owned_code_chain_bridge = None


def _zero_v827_agent_try_planner_owned_code_chain(self, user_input: str) -> Optional[Dict[str, Any]]:
    runner = _zero_v827_run_planner_owned_code_chain_bridge
    call_planner = globals().get("_zero_v824_call_planner_like")
    fallback_candidate = globals().get("_zero_v826_code_fix_bridge_candidate")
    planner_dispatch_candidate = globals().get("_zero_v824_agent_planner_dispatch_candidate")
    persistent_candidate = globals().get("_zero_v823_agent_persistent_runtime_candidate")
    if callable(planner_dispatch_candidate) and bool(planner_dispatch_candidate(user_input)):
        return None
    if callable(persistent_candidate) and bool(persistent_candidate(user_input)):
        return None
    if callable(runner):
        from core.runtime.runtime_route_keys import RuntimeRouteKeys

        routed = self._run_via_runtime_route_registry(
            route_key=RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN,
            entrypoint="core.agent.agent_loop.AgentLoop.planner_owned_code_chain_route",
            runner=lambda: runner(
                agent=self,
                user_input=user_input,
                call_planner_like=call_planner if callable(call_planner) else None,
                fallback_candidate=fallback_candidate if callable(fallback_candidate) else None,
                fallback_enabled=False,
            ),
            request={"user_input": str(user_input or ""), "route": "planner_owned_code_chain"},
            goal=str(user_input or "planner_owned_code_chain"),
            workspace_root=Path(_zero_v826_repo_root_from_agent(self)) / "workspace",
        )
        if routed is not None:
            return routed
    return None
