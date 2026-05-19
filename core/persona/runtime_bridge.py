from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.persona.display_state_contract import ensure_display_state_contract
from core.persona.policy_layer import evaluate_persona_runtime_policy, policy_decision_trace
from core.persona.runtime_state import PersonaRuntimeState, create_persona_runtime_state
from core.runtime.execution_gateway import safe_subprocess_run
from core.tools.tool_audit import build_l5_audit_records
from core.tools.tool_call import ToolCallExecutor, tool_call_trace_event
from core.tools.tool_registry import ToolRegistry


RUNTIME_STATUSES = {"planning", "executing", "blocked", "done", "failed"}


@dataclass
class PersonaRuntimeRecord:
    goal: str
    run_id: str = field(default_factory=lambda: f"persona_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}")
    policy_decision: Dict[str, Any] = field(default_factory=dict)
    plan: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)


class PersonaRuntimeBridge:
    """
    Adapter between Persona UI commands and ZERO runtime execution.

    Persona remains an outer shell here: this bridge translates UI input into a
    normal AgentLoop tool_call task, then translates runtime trace/result data
    back into compact display payloads.
    """

    def __init__(
        self,
        *,
        workspace_dir: str | Path | None = None,
        tool_registry: Any | None = None,
    ) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.workspace_dir = Path(workspace_dir or self.repo_root).resolve(strict=False)
        self.tool_registry = tool_registry or ToolRegistry(workspace_dir=str(self.workspace_dir))
        self.tool_call_executor = ToolCallExecutor(self.tool_registry)
        self._last_record: PersonaRuntimeRecord | None = None
        self.runtime_state: PersonaRuntimeState = create_persona_runtime_state()

    def submit_ui_task(self, user_input: str) -> Dict[str, Any]:
        goal = _ui_input_to_goal(user_input)
        self.runtime_state.set_task_goal(goal)
        policy_decision = evaluate_persona_runtime_policy(goal)
        self.runtime_state.update_policy_decision(policy_decision)
        planner = _PersonaRuntimeDemoPlanner()
        planning_event = _timeline_event(
            step=1,
            phase="planning",
            label="Step 1: planning",
            status="success",
            detail=goal,
        )
        if not policy_decision.get("allowed", True):
            blocked_reason = str(policy_decision.get("blocked_reason") or "policy blocked task")
            response = {
                "ok": False,
                "plan": {
                    "ok": False,
                    "intent": "policy_blocked",
                    "tool_calls": [],
                    "error": blocked_reason,
                },
                "execution": {
                    "ok": False,
                    "execution_log": [],
                    "execution_trace": [],
                    "last_result": {
                        "ok": False,
                        "status": "blocked",
                        "error": blocked_reason,
                    },
                    "final_answer": blocked_reason,
                    "error": blocked_reason,
                },
                "final_answer": blocked_reason,
                "error": blocked_reason,
            }
            record = PersonaRuntimeRecord(
                goal=goal,
                policy_decision=copy.deepcopy(policy_decision),
                plan=copy.deepcopy(response["plan"]),
                execution=copy.deepcopy(response["execution"]),
                response=copy.deepcopy(response),
                timeline=[],
            )
            record.timeline = _build_timeline(record, planning_event=planning_event)
            self._last_record = record
            return self.get_display_state()

        loop = AgentLoop(
            planner=planner,
            tool_registry=self.tool_registry,
            workspace_dir=str(self.workspace_dir),
        )

        try:
            self._ensure_standard_demo_inputs()
            response = loop.run("persona runtime bridge task")
            response = self._append_github_commit(response)
        except Exception as exc:
            response = {
                "ok": False,
                "plan": planner.plan(),
                "execution": {
                    "ok": False,
                    "execution_log": [],
                    "execution_trace": [],
                    "last_result": {
                        "ok": False,
                        "status": "failed",
                        "error": str(exc),
                    },
                    "error": str(exc),
                },
                "error": str(exc),
            }

        record = PersonaRuntimeRecord(
            goal=goal,
            policy_decision=copy.deepcopy(policy_decision),
            plan=copy.deepcopy(response.get("plan")) if isinstance(response.get("plan"), dict) else planner.plan(),
            execution=copy.deepcopy(response.get("execution")) if isinstance(response.get("execution"), dict) else {},
            response=copy.deepcopy(response) if isinstance(response, dict) else {"ok": False, "error": str(response)},
            timeline=[],
        )
        record.timeline = _build_timeline(record, planning_event=planning_event)
        self._last_record = record
        return self.get_display_state()

    def replay_last_task(self) -> Dict[str, Any]:
        display = self.get_display_state()
        display["replay"] = True
        display["replay_summary"] = "replaying last recorded runtime trace without re-running tools"
        return display

    def submit_search_demo(self, query: str = "local AI agent trace replay") -> Dict[str, Any]:
        goal = f"Search the web for: {query}"
        planner = _PersonaSearchDemoPlanner(query=query)
        planning_event = _timeline_event(
            step=1,
            phase="planning",
            label="Step 1: planning",
            status="success",
            detail=goal,
        )
        loop = AgentLoop(
            planner=planner,
            tool_registry=self.tool_registry,
            workspace_dir=str(self.workspace_dir),
        )

        try:
            response = loop.run("persona web search demo")
        except Exception as exc:
            response = {
                "ok": False,
                "plan": planner.plan(),
                "execution": {
                    "ok": False,
                    "execution_log": [],
                    "execution_trace": [],
                    "last_result": {
                        "ok": False,
                        "status": "failed",
                        "error": str(exc),
                    },
                    "error": str(exc),
                },
                "error": str(exc),
            }

        record = PersonaRuntimeRecord(
            goal=goal,
            plan=copy.deepcopy(response.get("plan")) if isinstance(response.get("plan"), dict) else planner.plan(),
            execution=copy.deepcopy(response.get("execution")) if isinstance(response.get("execution"), dict) else {},
            response=copy.deepcopy(response) if isinstance(response, dict) else {"ok": False, "error": str(response)},
            timeline=[],
        )
        record.timeline = _build_timeline(record, planning_event=planning_event)
        self._last_record = record
        return self.get_display_state()

    def submit_hybrid_demo(self, query: str = "local AI agent trace replay") -> Dict[str, Any]:
        query = str(query or "").strip() or "local AI agent trace replay"
        goal = f"Search the web, write a summary, then commit it locally: {query}"
        plan = {
            "ok": True,
            "flow": "hybrid_demo",
            "intent": "tool_call",
            "tool_calls": [
                {
                    "tool": "web_search",
                    "args": {
                        "query": query,
                        "limit": 3,
                    },
                },
                {
                    "tool": "file_write",
                    "args": {
                        "path": "workspace/shared/search_summary.txt",
                        "content": "",
                    },
                },
                {
                    "tool": "github_commit",
                    "args": {
                        "repo_path": str(self.workspace_dir / "workspace" / "hybrid_demo_repo"),
                        "message": "demo: commit hybrid search summary",
                        "files": [],
                    },
                },
            ],
        }
        planning_event = _timeline_event(
            step=1,
            phase="planning",
            label="Step 1: planning",
            status="success",
            detail=goal,
        )

        execution: Dict[str, Any] = {
            "ok": True,
            "results": [],
            "execution_log": [],
            "execution_trace": [],
            "last_result": {},
            "final_answer": "",
            "error": None,
        }

        try:
            search_call = copy.deepcopy(plan["tool_calls"][0])
            search_result = self.tool_call_executor.execute(search_call, source="persona_hybrid_demo")
            self._append_tool_execution(execution, search_call, search_result)
            if not search_result.get("ok"):
                raise RuntimeError(str(search_result.get("error") or "web_search failed"))

            search_output = search_result.get("output") if isinstance(search_result.get("output"), dict) else {}
            summary_text = _build_search_results_summary(search_output)
            if not summary_text.strip():
                raise RuntimeError("web_search returned no summary")

            file_write_call = copy.deepcopy(plan["tool_calls"][1])
            file_write_call["args"]["content"] = summary_text
            plan["tool_calls"][1] = copy.deepcopy(file_write_call)
            file_write_result = self.tool_call_executor.execute(file_write_call, source="persona_hybrid_demo")
            self._append_tool_execution(execution, file_write_call, file_write_result)
            if not file_write_result.get("ok"):
                raise RuntimeError(str(file_write_result.get("error") or "file_write failed"))

            demo_repo = self._ensure_hybrid_demo_repo()
            committed_summary = (
                f"{summary_text.rstrip()}\n\n"
                f"Committed by persona hybrid demo at {datetime.now(timezone.utc).isoformat()}\n"
            )
            commit_call = copy.deepcopy(plan["tool_calls"][2])
            commit_call["args"] = {
                "repo_path": str(demo_repo),
                "message": "demo: commit hybrid search summary",
                "files": [
                    {
                        "path": "search_summary.txt",
                        "content": committed_summary,
                    }
                ],
            }
            plan["tool_calls"][2] = copy.deepcopy(commit_call)
            commit_result = self.tool_call_executor.execute(commit_call, source="persona_hybrid_demo")
            self._append_tool_execution(execution, commit_call, commit_result)
            if not commit_result.get("ok"):
                raise RuntimeError(str(commit_result.get("error") or "github_commit failed"))

            execution["final_answer"] = (
                f"{summary_text.rstrip()}\n\n"
                f"Commit: {_extract_tool_result_summary(commit_result)}"
            )
        except Exception as exc:
            execution["ok"] = False
            execution["error"] = str(exc)
            if not execution.get("last_result"):
                execution["last_result"] = {
                    "ok": False,
                    "status": "failed",
                    "error": str(exc),
                }
            if not execution.get("final_answer"):
                execution["final_answer"] = str(exc)

        response = {
            "ok": bool(execution.get("ok")),
            "plan": copy.deepcopy(plan),
            "execution": copy.deepcopy(execution),
            "final_answer": str(execution.get("final_answer") or ""),
            "error": execution.get("error"),
        }
        record = PersonaRuntimeRecord(
            goal=goal,
            plan=copy.deepcopy(plan),
            execution=copy.deepcopy(execution),
            response=copy.deepcopy(response),
            timeline=[],
        )
        record.timeline = _build_timeline(record, planning_event=planning_event)
        self._last_record = record
        return self.get_display_state()

    def get_display_state(self) -> Dict[str, Any]:
        if self._last_record is None:
            display_state = _with_persona_presentation(
                {
                "ok": True,
                "display_state_source": "runtime_bridge",
                "runtime_status": "planning",
                "controller_status": "idle",
                "risk_level": "",
                "confirmation_required": False,
                "status_source": "runtime_bridge",
                "task_goal": "",
                "tool_calls": [],
                "result_summary": "no runtime task has been submitted yet",
                "blocked_reason": "",
                "trace": [],
                "execution_log": [],
                "last_result": {},
                "timeline": [],
                "persona_decision_trace": [],
                "search_results_summary": "",
                "compact_demo_summary": "",
                },
                audit_records=[],
            )
            self.runtime_state.update_display_state(display_state)
            return display_state

        record = self._last_record
        execution = record.execution if isinstance(record.execution, dict) else {}
        trace = _extract_trace(execution)
        execution_log = _extract_execution_log(execution)
        last_result = execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {}
        status = _derive_runtime_status(execution=execution, trace=trace, last_result=last_result)
        tool_calls = _extract_tool_calls(record.plan, execution, trace)
        blocked_reason = _extract_blocked_reason(status=status, execution=execution, last_result=last_result, trace=trace)
        result_summary = _extract_result_summary(execution=execution, last_result=last_result, trace=trace)
        search_results_summary = _extract_search_results_summary(execution)
        compact_demo_summary = _build_compact_demo_summary(record.plan, tool_calls, last_result)
        audit_records = build_l5_audit_records(execution, run_id=record.run_id)
        persona_trace = policy_decision_trace(record.policy_decision)
        controller_surface = _derive_controller_surface(
            runtime_status=status,
            audit_records=audit_records,
            trace=trace,
            last_result=last_result,
            policy_decision=record.policy_decision,
        )
        blocked_reason = blocked_reason or str(record.policy_decision.get("blocked_reason") or "")

        display_state = _with_persona_presentation(
            {
            "ok": status not in {"failed", "blocked"},
            "display_state_source": "runtime_bridge",
            "runtime_status": status,
            "controller_status": controller_surface["controller_status"],
            "risk_level": controller_surface["risk_level"],
            "confirmation_required": controller_surface["confirmation_required"],
            "status_source": _status_source(execution, trace, execution_log),
            "task_goal": record.goal,
            "tool_calls": tool_calls,
            "result_summary": result_summary,
            "blocked_reason": blocked_reason,
            "trace": trace,
            "execution_log": execution_log,
            "last_result": copy.deepcopy(last_result),
            "plan": copy.deepcopy(record.plan),
            "timeline": copy.deepcopy(record.timeline),
            "persona_decision_trace": persona_trace,
            "search_results_summary": search_results_summary,
            "compact_demo_summary": compact_demo_summary,
            },
            audit_records=audit_records,
        )
        self.runtime_state.update_display_state(display_state)
        return display_state

    def format_display_text(self) -> str:
        return format_persona_runtime_display(self.get_display_state())

    def _append_github_commit(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return response
        execution = response.get("execution")
        if not isinstance(execution, dict):
            return response

        summary_path = self.workspace_dir / "workspace" / "shared" / "summary.txt"
        summary_text = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else ""
        committed_summary = f"{summary_text.rstrip()}\n\nCommitted by persona runtime demo at {datetime.now(timezone.utc).isoformat()}\n"
        demo_repo = self._ensure_demo_repo()
        github_call = {
            "tool": "github_commit",
            "args": {
                "repo_path": str(demo_repo),
                "message": "demo: commit persona runtime summary",
                "files": [
                    {
                        "path": "summary.txt",
                        "content": committed_summary,
                    }
                ],
            },
        }
        tool_result = self.tool_call_executor.execute(github_call, source="persona_runtime_bridge")
        trace_event = tool_call_trace_event(tool_result)

        results = execution.get("results")
        if not isinstance(results, list):
            results = []
            execution["results"] = results
        results.append(
            {
                "step_index": len(results) + 1,
                "step": {
                    "type": "tool_call",
                    "tool_call": copy.deepcopy(github_call),
                },
                "result": copy.deepcopy(tool_result),
            }
        )

        for key in ("execution_log", "execution_trace"):
            events = execution.get(key)
            if not isinstance(events, list):
                events = []
                execution[key] = events
            events.append(copy.deepcopy(trace_event))

        execution["steps_executed"] = len(results)
        execution["last_result"] = copy.deepcopy(tool_result)
        execution["final_answer"] = _extract_tool_result_summary(tool_result)
        execution["ok"] = bool(execution.get("ok", True) and tool_result.get("ok"))
        execution["error"] = None if tool_result.get("ok") else tool_result.get("error")
        response["ok"] = bool(response.get("ok", True) and tool_result.get("ok"))
        response["execution"] = execution
        response["final_answer"] = execution["final_answer"]
        response["error"] = execution["error"]

        plan = response.get("plan")
        if isinstance(plan, dict):
            tool_calls = plan.get("tool_calls")
            if isinstance(tool_calls, list):
                tool_calls.append(copy.deepcopy(github_call))

        return response

    def _ensure_standard_demo_inputs(self) -> None:
        shared_dir = self.workspace_dir / "workspace" / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        input_path = shared_dir / "input.txt"
        if not input_path.exists():
            input_path.write_text("Persona runtime demo input.\n", encoding="utf-8")

    def _ensure_demo_repo(self) -> Path:
        repo = self.workspace_dir / "workspace" / "persona_runtime_demo_repo"
        repo.mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").exists():
            safe_subprocess_run(
                ["git", "init"],
                cwd=str(repo),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
        return repo

    def _ensure_hybrid_demo_repo(self) -> Path:
        repo = self.workspace_dir / "workspace" / "hybrid_demo_repo"
        repo.mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").exists():
            safe_subprocess_run(
                ["git", "init"],
                cwd=str(repo),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
        return repo

    def _append_tool_execution(
        self,
        execution: Dict[str, Any],
        tool_call: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> None:
        results = execution.get("results")
        if not isinstance(results, list):
            results = []
            execution["results"] = results
        results.append(
            {
                "step_index": len(results) + 1,
                "step": {
                    "type": "tool_call",
                    "tool_call": copy.deepcopy(tool_call),
                },
                "result": copy.deepcopy(tool_result),
            }
        )

        trace_event = tool_call_trace_event(tool_result)
        for key in ("execution_log", "execution_trace"):
            events = execution.get(key)
            if not isinstance(events, list):
                events = []
                execution[key] = events
            events.append(copy.deepcopy(trace_event))

        execution["steps_executed"] = len(results)
        execution["last_result"] = copy.deepcopy(tool_result)
        execution["ok"] = bool(execution.get("ok", True) and tool_result.get("ok"))
        if not tool_result.get("ok"):
            execution["error"] = tool_result.get("error")


def default_runtime_demo_goal() -> str:
    return "Read input.txt, produce summary.txt, then commit the summary with github_commit"


def _ui_input_to_goal(user_input: str) -> str:
    text = str(user_input or "").strip()
    if not text:
        return default_runtime_demo_goal()
    if text.lower() in {"run runtime-demo", "runtime-demo", "persona runtime demo", "run demo", "demo"}:
        return default_runtime_demo_goal()
    return text


def format_persona_runtime_display(display: Dict[str, Any]) -> str:
    tool_calls = display.get("tool_calls") if isinstance(display.get("tool_calls"), list) else []
    if tool_calls:
        tool_lines = []
        for index, item in enumerate(tool_calls, start=1):
            if not isinstance(item, dict):
                continue
            tool_lines.append(
                f"{index}. {item.get('tool') or '-'} "
                f"status={item.get('status') or '-'} "
                f"args={item.get('args_summary') or item.get('path') or '-'}"
            )
        tool_text = "\n".join(tool_lines) or "-"
    else:
        tool_text = "-"

    timeline = display.get("timeline") if isinstance(display.get("timeline"), list) else []
    timeline_lines = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        timeline_lines.append(
            f"{item.get('timestamp') or '-'} | {item.get('label') or '-'} | "
            f"{item.get('status') or '-'} | {item.get('detail') or '-'}"
        )
    timeline_text = "\n".join(timeline_lines) or "-"

    blocked_reason = str(display.get("blocked_reason") or "").strip()
    blocked_block = f"\n\n[BLOCKED]\n{blocked_reason}" if blocked_reason else ""
    replay_block = "\nReplay       : trace replay\n" if display.get("replay") else ""
    search_summary = str(display.get("search_results_summary") or "").strip()
    search_block = f"\n[SEARCH RESULTS SUMMARY]\n{search_summary}\n\n" if search_summary else ""
    compact_summary = str(display.get("compact_demo_summary") or "").strip()
    compact_block = f"[COMPACT DEMO SUMMARY]\n{compact_summary}\n\n" if compact_summary else ""
    persona_reply = str(display.get("persona_final_reply") or "").strip()
    persona_block = f"\n\n[PERSONA REPLY]\n{persona_reply}" if persona_reply else ""
    tts_pipeline = display.get("tts_pipeline") if isinstance(display.get("tts_pipeline"), dict) else {}
    tts_block = ""
    if tts_pipeline:
        tts_block = (
            "\n\n[TTS PIPELINE]\n"
            f"Input Source : {tts_pipeline.get('input_source') or '-'}\n"
            f"Voice Style  : {tts_pipeline.get('voice_style') or '-'}\n"
            f"Runtime Safe : {tts_pipeline.get('runtime_safe')}"
        )

    return (
        f"{compact_block}"
        "[PERSONA RUNTIME]\n"
        f"Status        : {display.get('runtime_status') or '-'}\n"
        f"Controller    : {display.get('controller_status') or '-'}\n"
        f"Risk          : {display.get('risk_level') or '-'}\n"
        f"Confirmation  : {display.get('confirmation_required')}\n"
        f"Status Source : {display.get('status_source') or '-'}\n"
        f"Display Source: {display.get('display_state_source') or '-'}\n"
        f"Task Goal     : {display.get('task_goal') or '-'}\n"
        f"{replay_block}"
        "\n"
        "[TASK FLOW]\n"
        f"{timeline_text}\n"
        "\n"
        "[TOOL CALLS]\n"
        f"{tool_text}\n"
        "\n"
        f"{search_block}"
        "[RESULT]\n"
        f"{display.get('result_summary') or '-'}"
        f"{blocked_block}"
        f"{persona_block}"
        f"{tts_block}"
    )


class _PersonaRuntimeDemoPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_calls": [
                {
                    "tool": "file_read",
                    "args": {
                        "path": "workspace/shared/input.txt",
                    },
                },
                {
                    "tool": "file_write",
                    "args": {
                        "path": "workspace/shared/summary.txt",
                        "content": "Summary:\n{{previous_content}}",
                    },
                },
            ],
        }


class _PersonaSearchDemoPlanner:
    def __init__(self, *, query: str) -> None:
        self.query = str(query or "").strip() or "local AI agent trace replay"

    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "web_search",
                "args": {
                    "query": self.query,
                    "limit": 3,
                },
            },
        }


def get_persona_runtime_bridge() -> PersonaRuntimeBridge:
    global _global_bridge
    try:
        return _global_bridge
    except NameError:
        _global_bridge = PersonaRuntimeBridge()
        return _global_bridge


def _derive_runtime_status(
    *,
    execution: Dict[str, Any],
    trace: List[Dict[str, Any]],
    last_result: Dict[str, Any],
) -> str:
    if last_result:
        last_status = str(last_result.get("status") or "").lower()
        if last_status == "blocked":
            return "blocked"
        if last_status in {"failed", "invalid_tool"}:
            return "failed"

    if trace:
        statuses = [str(item.get("status") or "").lower() for item in trace if isinstance(item, dict)]
        if any(status == "blocked" for status in statuses):
            return "blocked"
        if any(status in {"failed", "invalid_tool"} for status in statuses):
            return "failed"
        if statuses and all(status == "success" for status in statuses):
            return "done"
        return "executing"

    if execution:
        if execution.get("ok") is False:
            return "failed"
        return "executing"

    return "planning"


def _build_timeline(record: PersonaRuntimeRecord, *, planning_event: Dict[str, Any]) -> List[Dict[str, Any]]:
    execution = record.execution if isinstance(record.execution, dict) else {}
    trace = _extract_trace(execution)
    if record.plan.get("flow") == "hybrid_demo":
        timeline = [
            _timeline_event(
                step=0,
                phase="planning",
                label="Planning",
                status=str(planning_event.get("status") or "success"),
                detail=str(planning_event.get("detail") or ""),
                timestamp=str(planning_event.get("timestamp") or ""),
            )
        ]
        for index, event in enumerate(trace, start=1):
            tool = str(event.get("tool") or "-")
            timeline.append(
                _timeline_event(
                    step=index,
                    phase="executing",
                    label=f"Step {index}: {tool}",
                    status=str(event.get("status") or "-"),
                    detail=_format_trace_args(event),
                    timestamp=str(event.get("timestamp") or ""),
                    tool=tool,
                )
            )
        status = _derive_runtime_status(
            execution=execution,
            trace=trace,
            last_result=execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {},
        )
        timeline.append(
            _timeline_event(
                step=len(trace) + 1,
                phase="result",
                label="Result",
                status=status,
                detail=_extract_result_summary(
                    execution=execution,
                    last_result=execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {},
                    trace=trace,
                ),
            )
        )
        return timeline

    timeline = [copy.deepcopy(planning_event)]
    for index, event in enumerate(trace, start=1):
        tool = str(event.get("tool") or "-")
        status = str(event.get("status") or "-")
        timeline.append(
            _timeline_event(
                step=2,
                phase="executing",
                label=f"Step 2: executing tool ({tool})",
                status=status,
                detail=_format_trace_args(event),
                timestamp=str(event.get("timestamp") or ""),
                tool=tool,
            )
        )

    status = _derive_runtime_status(
        execution=execution,
        trace=trace,
        last_result=execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {},
    )
    timeline.append(
        _timeline_event(
            step=3,
            phase="result",
            label="Step 3: result",
            status=status,
            detail=_extract_result_summary(
                execution=execution,
                last_result=execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {},
                trace=trace,
            ),
        )
    )
    return timeline


def _timeline_event(
    *,
    step: int,
    phase: str,
    label: str,
    status: str,
    detail: str,
    timestamp: str | None = None,
    tool: str = "",
) -> Dict[str, Any]:
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "step": step,
        "phase": phase,
        "label": label,
        "status": status,
        "detail": detail,
        "tool": tool,
    }


def _format_trace_args(event: Dict[str, Any]) -> str:
    args = event.get("args_summary")
    return _summarize_args(args)


def _summarize_args(args: Any) -> str:
    if not isinstance(args, dict):
        return "-"
    parts = []
    for key in ("query", "limit", "path", "repo_path", "message"):
        value = args.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={value}")
    files = args.get("files")
    if isinstance(files, list):
        paths = []
        for item in files[:3]:
            if isinstance(item, dict):
                path = item.get("path")
                if path:
                    paths.append(str(path))
        parts.append(f"files={paths}")
    content = args.get("content")
    if isinstance(content, dict):
        parts.append(f"content_len={content.get('length') or 0}")
    elif isinstance(content, str):
        parts.append(f"content_len={len(content)}")
    return ", ".join(parts) if parts else str(args)


def _extract_tool_result_summary(tool_result: Dict[str, Any]) -> str:
    output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
    value = output.get("summary")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if output.get("commit_hash"):
        return f"created local git commit {str(output.get('commit_hash'))[:12]}"
    return str(tool_result.get("status") or "")


def _status_source(
    execution: Dict[str, Any],
    trace: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
) -> str:
    if trace:
        return "execution_trace"
    if execution_log:
        return "execution_log"
    if execution:
        return "runtime_execution"
    return "runtime_bridge"


def _extract_trace(execution: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = execution.get("execution_trace")
    if isinstance(trace, list):
        return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]
    return []


def _extract_execution_log(execution: Dict[str, Any]) -> List[Dict[str, Any]]:
    log = execution.get("execution_log")
    if isinstance(log, list):
        return [copy.deepcopy(item) for item in log if isinstance(item, dict)]
    return []


def _extract_tool_calls(
    plan: Dict[str, Any],
    execution: Dict[str, Any],
    trace: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    plan_calls = plan.get("tool_calls")
    if isinstance(plan_calls, list):
        for item in plan_calls:
            if isinstance(item, dict):
                calls.append(
                    {
                        "tool": str(item.get("tool") or ""),
                        "path": _first_path_from_args(item.get("args")),
                        "args_summary": _summarize_args(item.get("args")),
                        "status": "",
                    }
                )
    elif isinstance(plan.get("tool_call"), dict):
        item = plan["tool_call"]
        calls.append(
            {
                "tool": str(item.get("tool") or ""),
                "path": _first_path_from_args(item.get("args")),
                "args_summary": _summarize_args(item.get("args")),
                "status": "",
            }
        )

    results = execution.get("results")
    if isinstance(results, list):
        for index, result_item in enumerate(results):
            if not isinstance(result_item, dict):
                continue
            result = result_item.get("result") if isinstance(result_item.get("result"), dict) else {}
            if index < len(calls):
                calls[index]["status"] = str(result.get("status") or "")
            else:
                calls.append(
                    {
                        "tool": str(result.get("tool") or ""),
                        "path": _first_path_from_args(result.get("args")),
                        "args_summary": _summarize_args(result.get("args")),
                        "status": str(result.get("status") or ""),
                    }
                )

    for index, event in enumerate(trace):
        if index < len(calls) and not calls[index].get("status"):
            calls[index]["status"] = str(event.get("status") or "")
        if index < len(calls) and not calls[index].get("args_summary"):
            calls[index]["args_summary"] = _format_trace_args(event)

    return calls


def _first_path_from_args(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    value = args.get("path")
    if value is None:
        return ""
    return str(value)


def _extract_result_summary(
    *,
    execution: Dict[str, Any],
    last_result: Dict[str, Any],
    trace: List[Dict[str, Any]],
) -> str:
    value = execution.get("final_answer")
    if isinstance(value, str) and value.strip():
        return value.strip()

    output = last_result.get("output") if isinstance(last_result.get("output"), dict) else {}
    for key in ("summary", "content", "message", "result"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if trace:
        last = trace[-1]
        summary = last.get("result_summary")
        if summary not in (None, "", [], {}):
            return str(summary)

    error = execution.get("error") or last_result.get("error")
    if error:
        return str(error)

    return ""


def _build_compact_demo_summary(
    plan: Dict[str, Any],
    tool_calls: List[Dict[str, Any]],
    last_result: Dict[str, Any],
) -> str:
    if plan.get("flow") != "hybrid_demo":
        return ""

    by_tool = {
        str(item.get("tool") or ""): str(item.get("status") or "-")
        for item in tool_calls
        if isinstance(item, dict)
    }
    rows = [
        ("Step 1: web_search", by_tool.get("web_search", "-")),
        ("Step 2: file_write", by_tool.get("file_write", "-")),
        ("Step 3: github_commit", by_tool.get("github_commit", "-")),
    ]

    lines = [f"{label:<24} {status}" for label, status in rows]
    output = last_result.get("output") if isinstance(last_result.get("output"), dict) else {}
    commit_created = (
        by_tool.get("github_commit") == "success"
        and bool(output.get("commit_hash") or output.get("git_commit"))
    )
    result = "local git commit created" if commit_created else "local git commit not created"
    lines.append(f"{'Result:':<24} {result}")
    return "\n".join(lines)


def _build_search_results_summary(search_output: Dict[str, Any]) -> str:
    query = str(search_output.get("query") or "").strip()
    provider = str(search_output.get("provider") or "").strip()
    result_count = search_output.get("result_count")
    results = search_output.get("results")
    if not isinstance(results, list):
        results = []

    lines = [
        "Search results summary",
        f"Query: {query or '-'}",
        f"Provider: {provider or '-'}",
        f"Results found: {result_count if result_count not in (None, '') else len(results)}",
        "Safety: results were summarized only; no external content was downloaded or executed.",
        "",
        "Top results:",
    ]

    for index, item in enumerate(results[:3], start=1):
        if not isinstance(item, dict):
            continue
        title = _compact_line(item.get("title"), max_length=90)
        url = _compact_line(item.get("url"), max_length=120)
        snippet = _compact_line(item.get("snippet"), max_length=180)
        lines.append(f"{index}. {title or url or '-'}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   Summary: {snippet}")

    if not results:
        lines.append("-")

    return "\n".join(lines).rstrip() + "\n"


def _derive_controller_surface(
    *,
    runtime_status: str,
    audit_records: List[Dict[str, Any]],
    trace: List[Dict[str, Any]],
    last_result: Dict[str, Any],
    policy_decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    policy = policy_decision if isinstance(policy_decision, dict) else {}
    final_decisions = [
        str(record.get("final_decision") or "").strip()
        for record in audit_records
        if isinstance(record, dict) and str(record.get("final_decision") or "").strip()
    ]
    statuses = [
        str(record.get("result_status") or "").strip().lower()
        for record in audit_records
        if isinstance(record, dict) and str(record.get("result_status") or "").strip()
    ]
    risk_levels = [
        str(record.get("risk_level") or "").strip()
        for record in audit_records
        if isinstance(record, dict) and str(record.get("risk_level") or "").strip()
    ]
    confirmation_required = any(
        bool(record.get("confirmation_required"))
        for record in audit_records
        if isinstance(record, dict)
    )

    if not confirmation_required:
        confirmation_required = any(
            bool(event.get("confirmation_required"))
            for event in trace
            if isinstance(event, dict)
        )
    if policy.get("confirmation_required") is True:
        confirmation_required = True

    controller_status = _derive_controller_status(
        runtime_status=runtime_status,
        final_decisions=final_decisions,
        result_statuses=statuses,
        confirmation_required=confirmation_required,
        last_result=last_result,
        policy_decision=policy,
    )

    return {
        "controller_status": controller_status,
        "risk_level": str(policy.get("risk_level") or "") or _highest_risk_level(risk_levels),
        "confirmation_required": confirmation_required,
    }


def _derive_controller_status(
    *,
    runtime_status: str,
    final_decisions: List[str],
    result_statuses: List[str],
    confirmation_required: bool,
    last_result: Dict[str, Any],
    policy_decision: Dict[str, Any] | None = None,
) -> str:
    policy = policy_decision if isinstance(policy_decision, dict) else {}
    if policy and policy.get("allowed") is False:
        return "blocked"
    normalized_decisions = {value.lower() for value in final_decisions}
    normalized_results = {value.lower() for value in result_statuses}
    last_status = str(last_result.get("status") or "").strip().lower()

    if confirmation_required:
        return "needs_confirmation"
    if "blocked" in normalized_decisions or "blocked" in normalized_results or last_status == "blocked":
        return "blocked"
    if "answer_directly" in normalized_decisions or "stop" in normalized_decisions:
        return "answer_directly"
    if "allow_tool" in normalized_decisions or normalized_results:
        return "allowed"
    if runtime_status in {"done", "executing"}:
        return "allowed"
    if runtime_status == "failed":
        return "failed"
    return "idle"


def _highest_risk_level(risk_levels: List[str]) -> str:
    order = {"": 0, "none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    best = ""
    best_score = -1
    for value in risk_levels:
        normalized = value.strip().lower()
        score = order.get(normalized, 1 if normalized else 0)
        if score > best_score:
            best = value
            best_score = score
    return best


def _with_persona_presentation(
    display: Dict[str, Any],
    *,
    audit_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    enriched = copy.deepcopy(display)
    enriched["display_state_source"] = "runtime_bridge"
    safe_audit = [copy.deepcopy(record) for record in audit_records if isinstance(record, dict)]
    presentation = _build_persona_presentation(enriched, safe_audit)
    enriched["audit_records"] = safe_audit
    enriched["audit_record"] = copy.deepcopy(safe_audit)
    enriched["persona_status_update"] = presentation["persona_status_update"]
    enriched["persona_intent_explanation"] = presentation["persona_intent_explanation"]
    enriched["persona_reasoning_summary"] = presentation["persona_reasoning_summary"]
    enriched["persona_final_reply"] = presentation["persona_final_reply"]
    enriched["tts_pipeline"] = _build_tts_pipeline(presentation["persona_final_reply"])
    enriched["presentation_log"] = _build_presentation_log(
        persona_final_reply=presentation["persona_final_reply"],
        tts_pipeline=enriched["tts_pipeline"],
    )
    enriched["persona_runtime_contract"] = {
        "role": "human_presentation_layer",
        "display_state_source": "runtime_bridge",
        "presentation_flow": ["runtime", "audit", "persona", "display", "tts"],
        "input_sources": ["controller final decision", "runtime result", "audit records"],
        "can": ["read_audit", "summarize", "render_text", "prepare_tts_input"],
        "cannot": ["call_tool", "choose_tool_policy", "execute", "retry", "confirm", "change_controller_decision", "invent_missing_runtime_state"],
        "no_reverse_path": True,
        "forbidden_reverse_paths": ["persona->controller", "persona->tool", "persona->runtime", "tts->runtime", "tts->controller"],
    }
    return ensure_display_state_contract(enriched)


def _build_persona_presentation(
    display: Dict[str, Any],
    audit_records: List[Dict[str, Any]],
) -> Dict[str, str]:
    status = str(display.get("runtime_status") or "planning").strip()
    goal = str(display.get("task_goal") or "").strip()
    result_summary = str(display.get("result_summary") or "").strip()
    blocked_reason = str(display.get("blocked_reason") or "").strip()
    tool_calls = display.get("tool_calls") if isinstance(display.get("tool_calls"), list) else []

    persona_status_update = _persona_status_text(status=status, goal=goal)
    persona_intent_explanation = _persona_intent_text(tool_calls=tool_calls, audit_records=audit_records)
    persona_reasoning_summary = _persona_audit_summary(audit_records)
    persona_final_reply = _persona_final_text(
        status=status,
        result_summary=result_summary,
        blocked_reason=blocked_reason,
    )

    return {
        "persona_status_update": persona_status_update,
        "persona_intent_explanation": persona_intent_explanation,
        "persona_reasoning_summary": persona_reasoning_summary,
        "persona_final_reply": persona_final_reply,
    }


def _persona_status_text(*, status: str, goal: str) -> str:
    if not goal:
        return "No runtime task has been submitted yet."
    return f"Runtime status is {status}: {goal}"


def _persona_intent_text(
    *,
    tool_calls: List[Any],
    audit_records: List[Dict[str, Any]],
) -> str:
    if not tool_calls:
        return "No tool use has been recorded by the controller."

    parts = []
    for index, item in enumerate(tool_calls, start=1):
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "-")
        status = str(item.get("status") or "-")
        parts.append(f"{index}. controller selected {tool}; result status={status}")

    confirmation_count = sum(1 for record in audit_records if record.get("confirmation_required"))
    if confirmation_count:
        parts.append(f"confirmation was required for {confirmation_count} audited step(s)")

    return "\n".join(parts) if parts else "No controller-selected tool calls are available."


def _persona_audit_summary(audit_records: List[Dict[str, Any]]) -> str:
    if not audit_records:
        return "No audit records are available yet."

    lines = []
    for record in audit_records:
        step = record.get("step_index")
        tool = str(record.get("requested_tool") or "-")
        decision = str(record.get("final_decision") or "-")
        risk = str(record.get("risk_level") or "-")
        result = str(record.get("result_status") or "-")
        lines.append(f"step {step}: tool={tool}, decision={decision}, risk={risk}, result={result}")
    return "\n".join(lines)


def _persona_final_text(
    *,
    status: str,
    result_summary: str,
    blocked_reason: str,
) -> str:
    if status == "done":
        if result_summary:
            return result_summary
        return "Runtime finished successfully. No additional result text was provided."

    if status == "blocked":
        return blocked_reason or result_summary or "Runtime is blocked. No extra persona inference was added."

    if status == "failed":
        return result_summary or "Runtime failed. No extra persona inference was added."

    return result_summary or "Runtime has not produced a final answer yet."


def _build_tts_pipeline(persona_final_reply: str) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    moss_tts_path = repo_root.parent / "ai_models" / "moss_tts" / "MOSS-TTS-Nano"
    return {
        "input_source": "persona_final_reply",
        "text_normalization": True,
        "voice_style": "default",
        "speaker_profile": "default",
        "tts_model": "MOSS-TTS-Nano",
        "tts_model_path": str(moss_tts_path),
        "audio_output": "",
        "runtime_safe": True,
        "controller_writeback": False,
        "audit_writeback": False,
        "ready": bool(persona_final_reply.strip()),
    }


def _build_presentation_log(
    *,
    persona_final_reply: str,
    tts_pipeline: Dict[str, Any],
) -> Dict[str, Any]:
    text_hash = hashlib.sha256(persona_final_reply.encode("utf-8", errors="replace")).hexdigest()
    return {
        "reply_id": text_hash[:16],
        "text_hash": text_hash,
        "voice_id": str(tts_pipeline.get("speaker_profile") or "default"),
        "tts_model": str(tts_pipeline.get("tts_model") or ""),
        "audio_path": str(tts_pipeline.get("audio_output") or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "persona_presentation_layer",
    }


def _extract_search_results_summary(execution: Dict[str, Any]) -> str:
    results = execution.get("results")
    if not isinstance(results, list):
        return ""
    for item in results:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if result.get("tool") != "web_search":
            continue
        output = result.get("output") if isinstance(result.get("output"), dict) else {}
        summary = _build_search_results_summary(output)
        return summary.strip()
    return ""


def _compact_line(value: Any, *, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _extract_blocked_reason(
    *,
    status: str,
    execution: Dict[str, Any],
    last_result: Dict[str, Any],
    trace: List[Dict[str, Any]],
) -> str:
    if status != "blocked":
        return ""

    error = last_result.get("error") or execution.get("error")
    if error:
        return str(error)

    for event in reversed(trace):
        if not isinstance(event, dict):
            continue
        if str(event.get("status") or "").lower() == "blocked":
            return str(event.get("error") or event.get("result_summary") or "blocked")

    return "blocked by ZERO runtime"
