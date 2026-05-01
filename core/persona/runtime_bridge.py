from __future__ import annotations

import copy
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor, tool_call_trace_event
from core.tools.tool_registry import ToolRegistry


RUNTIME_STATUSES = {"planning", "executing", "blocked", "done", "failed"}


@dataclass
class PersonaRuntimeRecord:
    goal: str
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

    def submit_ui_task(self, user_input: str) -> Dict[str, Any]:
        goal = _ui_input_to_goal(user_input)
        planner = _PersonaRuntimeDemoPlanner()
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

    def get_display_state(self) -> Dict[str, Any]:
        if self._last_record is None:
            return {
                "ok": True,
                "runtime_status": "planning",
                "status_source": "runtime_bridge",
                "task_goal": "",
                "tool_calls": [],
                "result_summary": "no runtime task has been submitted yet",
                "blocked_reason": "",
                "trace": [],
                "execution_log": [],
                "last_result": {},
                "timeline": [],
            }

        record = self._last_record
        execution = record.execution if isinstance(record.execution, dict) else {}
        trace = _extract_trace(execution)
        execution_log = _extract_execution_log(execution)
        last_result = execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {}
        status = _derive_runtime_status(execution=execution, trace=trace, last_result=last_result)
        tool_calls = _extract_tool_calls(record.plan, execution, trace)
        blocked_reason = _extract_blocked_reason(status=status, execution=execution, last_result=last_result, trace=trace)
        result_summary = _extract_result_summary(execution=execution, last_result=last_result, trace=trace)

        return {
            "ok": status not in {"failed", "blocked"},
            "runtime_status": status,
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
        }

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
            subprocess.run(
                ["git", "init"],
                cwd=str(repo),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                shell=False,
            )
        return repo


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

    return (
        "[PERSONA RUNTIME]\n"
        f"Status        : {display.get('runtime_status') or '-'}\n"
        f"Status Source : {display.get('status_source') or '-'}\n"
        f"Task Goal     : {display.get('task_goal') or '-'}\n"
        f"{replay_block}"
        "\n"
        "[TASK FLOW]\n"
        f"{timeline_text}\n"
        "\n"
        "[TOOL CALLS]\n"
        f"{tool_text}\n"
        "\n"
        "[RESULT]\n"
        f"{display.get('result_summary') or '-'}"
        f"{blocked_block}"
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
    for key in ("path", "repo_path", "message"):
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
