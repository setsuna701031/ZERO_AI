from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor, tool_call_trace_event
from core.tools.tool_decision import parse_tool_decision
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l4-tool-decision-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class ToolDecisionPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "type": "tool_call",
            "tool": "read_file",
            "args": {
                "path": "shared/l4_tool_decision/input.txt",
            },
        }


def main() -> int:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = ToolCallExecutor(registry)

    direct_decision = {
        "type": "tool_call",
        "tool": "write_file",
        "args": {
            "path": "shared/l4_tool_decision/input.txt",
            "content": "hello from tool decision\n",
            "allow_overwrite": True,
        },
    }
    parsed = parse_tool_decision(direct_decision)
    if parsed.get("ok") is not True or parsed.get("tool") != "write_file":
        return fail(f"failed to parse direct tool_call decision: {parsed}")
    pass_step("parser accepts direct tool_call JSON")

    write_result = executor.execute(direct_decision, source="llm_tool_decision_smoke")
    if write_result.get("ok") is not True:
        return fail(f"direct tool decision did not execute: {write_result}")
    observation = write_result.get("output", {}).get("observation")
    if not isinstance(observation, dict) or observation.get("type") != "file_write":
        return fail(f"write result missing standardized observation: {write_result}")
    pass_step("direct tool_call goes through ToolCallExecutor and returns observation")

    wrapped_decision = {
        "action": {
            "type": "tool_call",
            "tool": "read_file",
            "args": {
                "path": "shared/l4_tool_decision/input.txt",
            },
        }
    }
    wrapped_result = executor.execute(wrapped_decision, source="llm_tool_decision_smoke")
    if wrapped_result.get("ok") is not True:
        return fail(f"wrapped tool decision did not execute: {wrapped_result}")
    wrapped_observation = wrapped_result.get("output", {}).get("observation")
    if not isinstance(wrapped_observation, dict) or wrapped_observation.get("type") != "file_content":
        return fail(f"wrapped result missing file_content observation: {wrapped_result}")
    if "hello from tool decision" not in str(wrapped_observation.get("data", {}).get("content", "")):
        return fail(f"wrapped observation missing read content: {wrapped_observation}")
    pass_step("parser accepts wrapper action.tool_call JSON")

    string_result = executor.execute(json.dumps(wrapped_decision), source="llm_tool_decision_smoke")
    if string_result.get("ok") is not True:
        return fail(f"JSON string tool decision did not execute: {string_result}")
    pass_step("parser accepts JSON string decisions")

    non_tool_result = executor.execute(
        {
            "type": "respond",
            "message": "not a tool call",
        },
        source="llm_tool_decision_smoke",
    )
    if non_tool_result.get("ok") is not False or non_tool_result.get("status") != "blocked":
        return fail(f"non-tool decision was not blocked: {non_tool_result}")
    non_tool_observation = non_tool_result.get("output", {}).get("observation")
    if not isinstance(non_tool_observation, dict) or non_tool_observation.get("type") != "tool_error":
        return fail(f"non-tool decision missing error observation: {non_tool_result}")
    pass_step("non-tool decisions return blocked/error observation")

    bad_args_result = executor.execute(
        {
            "type": "tool_call",
            "tool": "read_file",
            "args": "workspace/demo.txt",
        },
        source="llm_tool_decision_smoke",
    )
    if bad_args_result.get("ok") is not False or bad_args_result.get("status") != "blocked":
        return fail(f"bad args decision was not blocked: {bad_args_result}")
    pass_step("parameter validation errors return blocked observation")

    trace = tool_call_trace_event(wrapped_result)
    for key in ("tool", "args_summary", "status", "duration_ms"):
        if key not in trace:
            return fail(f"trace missing {key}: {trace}")
    if trace.get("tool") != "read_file" or trace.get("status") != "success":
        return fail(f"trace has wrong tool/status: {trace}")
    if trace.get("duration_ms") is None:
        return fail(f"trace missing duration: {trace}")
    pass_step("trace includes tool, args summary, status, and duration")

    loop = AgentLoop(
        planner=ToolDecisionPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    loop_result = loop.run("read the L4 tool decision smoke file")
    if loop_result.get("ok") is not True:
        return fail(f"agent loop did not execute structured tool decision: {loop_result}")
    execution = loop_result.get("execution") if isinstance(loop_result.get("execution"), dict) else {}
    last_result = execution.get("last_result") if isinstance(execution.get("last_result"), dict) else {}
    loop_observation = last_result.get("output", {}).get("observation")
    if not isinstance(loop_observation, dict) or loop_observation.get("type") != "file_content":
        return fail(f"agent loop did not receive standardized observation: {loop_result}")
    if "read " not in str(loop_result.get("final_answer") or ""):
        return fail(f"loop final answer did not use observation summary: {loop_result}")
    pass_step("agent loop receives standardized observation from LLM-style tool decision")

    scheduler_path = REPO_ROOT / "core" / "tasks" / "scheduler.py"
    scheduler_text = scheduler_path.read_text(encoding="utf-8", errors="replace")
    if "tool_decision" in scheduler_text:
        return fail("scheduler should not know tool_decision")
    pass_step("scheduler remains unaware of tool decision bridge")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
