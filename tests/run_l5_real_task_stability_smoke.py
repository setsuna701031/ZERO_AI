from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-real-task-stability-smoke]"
WORKSPACE = REPO_ROOT / "workspace" / "shared" / "l5_real_task_stability"
INPUT_PATH = WORKSPACE / "input.txt"
OUTPUT_PATH = WORKSPACE / "output.txt"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class RealTaskPlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_real_task_stability/input.txt"},
            }

        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        if observation.get("type") == "file_content" and data.get("path") == "shared/l5_real_task_stability/input.txt":
            observed_content = str(data.get("content") or "")
            return {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "path": "shared/l5_real_task_stability/output.txt",
                    "content": f"verified copy from observation:\n{observed_content}",
                    "allow_overwrite": True,
                },
            }

        if observation.get("type") == "file_write":
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_real_task_stability/output.txt"},
            }

        return {"type": "respond", "message": "real task stability complete"}


def main() -> int:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    source_text = "real task observed payload 2026\n"
    INPUT_PATH.write_text(source_text, encoding="utf-8")
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    loop = AgentLoop(
        planner=RealTaskPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=4,
    )
    result = loop.run("read source, write observed copy, verify output")
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    results = execution.get("results") if isinstance(execution.get("results"), list) else []

    if result.get("ok") is not True:
        return fail(f"AgentLoop real task failed: {result}")
    if len(results) != 3 or execution.get("steps_executed") != 3:
        return fail(f"expected read_file -> write_file -> read_file chain: {result}")

    tools = [item.get("result", {}).get("tool") for item in results if isinstance(item, dict)]
    if tools != ["read_file", "write_file", "read_file"]:
        return fail(f"unexpected tool chain: {tools} in {result}")
    pass_step("real read_file -> write_file -> read_file verification chain executed")

    write_result = results[1].get("result") if isinstance(results[1], dict) else {}
    write_args = write_result.get("args") if isinstance(write_result, dict) else {}
    write_content = str(write_args.get("content") or "")
    if source_text not in write_content:
        return fail(f"write_file did not use previous read_file observation: {write_args}")
    if "hardcoded" in write_content.lower():
        return fail(f"write_file content appears hardcoded: {write_args}")
    pass_step("write_file uses previous read_file observation content")

    if not OUTPUT_PATH.exists():
        return fail(f"output file missing: {OUTPUT_PATH}")
    output_text = OUTPUT_PATH.read_text(encoding="utf-8", errors="replace")
    if not output_text.strip() or source_text not in output_text:
        return fail(f"output file is empty or missing observed content: {output_text!r}")
    pass_step("output file exists and contains non-empty observed content")

    trace_events = _events_from_execution(execution)
    if len(trace_events) < 3:
        return fail(f"execution_trace/execution_log missing tool events: {execution}")

    for index, event in enumerate(trace_events[:3], start=1):
        if not isinstance(event.get("decision_input"), dict):
            return fail(f"decision_input missing from event {index}: {event}")
        if not event.get("final_decision"):
            return fail(f"controller final decision missing from event {index}: {event}")
        for key in ("why_call_tool", "why_not_call_tool", "why_stop_or_replan"):
            if key not in event:
                return fail(f"{key} missing from event {index}: {event}")
    pass_step("controller decision_input, final decision, and why fields are recorded")

    final_decisions = [event.get("final_decision") for event in trace_events[:3]]
    if final_decisions != ["ALLOW_TOOL", "ALLOW_TOOL", "ALLOW_TOOL"]:
        return fail(f"unexpected controller final decisions: {final_decisions}")

    second_input = trace_events[1].get("decision_input")
    if second_input.get("requested_tool") != "write_file" or second_input.get("last_tool") != "read_file":
        return fail(f"second decision did not bind read observation to write tool: {second_input}")
    if "read " not in str(second_input.get("observation_summary") or ""):
        return fail(f"second decision missing prior observation summary: {second_input}")
    pass_step("second decision carries previous read_file observation metadata")

    if len(results) > 3 or execution.get("stopped_reason") == "max_tool_cycles":
        return fail(f"loop did not stop after bounded real task chain: {execution}")
    repeated = _max_repeated_tool_run(tools)
    if repeated > 1:
        return fail(f"excessive repeated tool calls detected: {tools}")
    pass_step("no infinite loop or excessive repeated tool calls")

    print(f"{PREFIX} ALL PASS")
    return 0


def _events_from_execution(execution: Dict[str, Any]) -> List[Dict[str, Any]]:
    execution_trace = execution.get("execution_trace") if isinstance(execution.get("execution_trace"), list) else []
    execution_log = execution.get("execution_log") if isinstance(execution.get("execution_log"), list) else []
    trace_events = [event for event in execution_trace if isinstance(event, dict)]
    if any(isinstance(event.get("decision_input"), dict) for event in trace_events):
        return trace_events
    return [event for event in execution_log if isinstance(event, dict)]


def _max_repeated_tool_run(tools: List[Any]) -> int:
    max_run = 0
    current_tool = None
    current_run = 0
    for tool in tools:
        if tool == current_tool:
            current_run += 1
        else:
            current_tool = tool
            current_run = 1
        max_run = max(max_run, current_run)
    return max_run


if __name__ == "__main__":
    raise SystemExit(main())
