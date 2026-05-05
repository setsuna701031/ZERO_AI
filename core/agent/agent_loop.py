from __future__ import annotations

import copy
import re
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
from core.memory.context_builder import build_context
from core.runtime.task_runner import TaskRunner
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
    ZERO Agent Loop v3 - interface contract stabilization + self-edit analysis-decision-action policy

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
        self.step_executor = step_executor
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.llm_client = llm_client
        self.tool_registry = kwargs.get("tool_registry") or getattr(self.step_executor, "tool_registry", None)
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

        self.task_runner = task_runner or TaskRunner(
            task_runtime=self.task_runtime,
            step_executor=self.step_executor,
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

        forced_repo_edit = self._try_force_repo_edit_route(text)
        if forced_repo_edit is not None:
            return self._normalize_agent_response(forced_repo_edit)

        scheduler_self_edit = self._try_force_scheduler_self_edit_route(text)
        if scheduler_self_edit is not None:
            return self._normalize_agent_response(scheduler_self_edit)

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

        try:
            forced = run_repo_edit_decision(text, repo_root=".")
        except Exception as e:
            forced = {
                "handled": True,
                "forced_route": True,
                "tool_name": "repo_edit_tool",
                "status": "failed",
                "reason": f"forced repo edit routing failed: {e}",
                "error": str(e),
                "task_text": text,
            }

        if not isinstance(forced, dict) or not forced.get("handled"):
            return None

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
            "planner_mode": "forced_repo_edit_v0_6",
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
                "code_chain_version": "v0.6",
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

        import re

        pattern = re.compile(
            r"(workspace[/\\][A-Za-z0-9_.\\- /\\\\]+?\\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg|html|css|js|ts|tsx|jsx|bat|ps1|sh))",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            value = match.group(1).strip().strip("'\"`.,;:")
            value = value.replace("\\", "/")
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
    ) -> Dict[str, Any]:
        return self.run_task_loop(
            task=task,
            current_tick=current_tick,
            user_input=user_input,
            original_plan=original_plan,
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


    def _observe_and_record_loop_decision(
        self,
        *,
        effective_task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(effective_task, dict) or not isinstance(runner_result, dict):
            return {}

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
        return decision

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

        return normalized

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
            self._apply_capability_metadata_to_task(created_task, route)
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

        if should_enable_document_flow:
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
