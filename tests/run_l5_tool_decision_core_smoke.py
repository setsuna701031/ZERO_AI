from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-tool-decision-core-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def require_status(result: Dict[str, Any], status: str) -> int:
    if result.get("status") != status:
        return fail(f"expected status {status}: {result}")
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    observation = output.get("observation") if isinstance(output.get("observation"), dict) else {}
    if not isinstance(observation, dict) or not observation.get("type"):
        return fail(f"missing standardized observation: {result}")
    return 0


class TwoStepPlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_tool_decision/input.txt"},
            }
        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        if observation.get("type") == "file_content":
            content = str(observation.get("data", {}).get("content") or "")
            return {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "path": "shared/l5_tool_decision/output.txt",
                    "content": f"copied:\n{content}",
                    "allow_overwrite": True,
                },
            }
        return {"type": "respond", "message": "done"}


class InfinitePlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        cycle = int(context.get("tool_decision_cycle") or 0)
        return {
            "type": "tool_call",
            "tool": "read_file",
            "args": {"path": f"shared/l5_tool_decision/loop_{cycle}.txt"},
        }


def main() -> int:
    workspace = REPO_ROOT / "workspace" / "shared" / "l5_tool_decision"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "input.txt").write_text("hello l5\n", encoding="utf-8")
    for index in range(4):
        (workspace / f"loop_{index}.txt").write_text(f"loop {index}\n", encoding="utf-8")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = ToolCallExecutor(registry)

    read_result = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {"path": "shared/l5_tool_decision/input.txt"}},
        source="l5_smoke",
    )
    if read_result.get("ok") is not True or require_status(read_result, "success"):
        return fail(f"read_file decision failed: {read_result}")
    pass_step("valid read_file tool_call returns success observation")

    write_result = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "write_file",
            "args": {
                "path": "shared/l5_tool_decision/direct_write.txt",
                "content": "direct write\n",
                "allow_overwrite": True,
            },
        },
        source="l5_smoke",
    )
    if write_result.get("ok") is not True or require_status(write_result, "success"):
        return fail(f"write_file decision failed: {write_result}")
    pass_step("valid write_file tool_call succeeds under workspace scope")

    list_result = executor.execute_decision(
        {"type": "tool_call", "tool": "list_dir", "args": {"path": "shared/l5_tool_decision"}},
        source="l5_smoke",
    )
    if list_result.get("ok") is not True or require_status(list_result, "success"):
        return fail(f"list_dir decision failed: {list_result}")
    pass_step("valid list_dir tool_call returns success observation")

    unknown_result = executor.execute_decision(
        {"type": "tool_call", "tool": "missing_tool", "args": {}},
        source="l5_smoke",
    )
    if unknown_result.get("ok") is not False or require_status(unknown_result, "invalid_tool"):
        return fail(f"unknown tool was not blocked: {unknown_result}")
    pass_step("unknown tool returns blocked/error observation")

    invalid_args_result = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {}},
        source="l5_smoke",
    )
    if invalid_args_result.get("ok") is not False or require_status(invalid_args_result, "invalid_args"):
        return fail(f"invalid args were not reported: {invalid_args_result}")
    pass_step("invalid args return validation observation without execution")

    denied_result = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {"path": "../outside.txt"}},
        source="l5_smoke",
    )
    if denied_result.get("ok") is not False or require_status(denied_result, "denied"):
        return fail(f"denied path was not reported: {denied_result}")
    pass_step("path outside allowed scope returns denied observation")

    non_tool_result = executor.execute_decision(
        {"type": "respond", "message": "plain answer"},
        source="l5_smoke",
    )
    if non_tool_result.get("ok") is not True or require_status(non_tool_result, "no_tool"):
        return fail(f"non-tool output did not return no_tool: {non_tool_result}")
    pass_step("non-tool LLM output does not execute a tool")

    loop = AgentLoop(
        planner=TwoStepPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=3,
    )
    loop_result = loop.run("read then write through observations")
    execution = loop_result.get("execution") if isinstance(loop_result.get("execution"), dict) else {}
    if loop_result.get("ok") is not True or execution.get("steps_executed") != 2:
        return fail(f"two-step decision flow failed: {loop_result}")
    output_text = (workspace / "output.txt").read_text(encoding="utf-8", errors="replace")
    if "hello l5" not in output_text:
        return fail(f"write step did not use prior observation: {output_text}")
    pass_step("read_file observation feeds next decision cycle for write_file")

    max_loop = AgentLoop(
        planner=InfinitePlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=3,
    )
    max_result = max_loop.run("loop forever")
    max_execution = max_result.get("execution") if isinstance(max_result.get("execution"), dict) else {}
    if max_result.get("ok") is not False or max_execution.get("stopped_reason") != "max_tool_cycles":
        return fail(f"max-cycle guard did not stop safely: {max_result}")
    pass_step("max-cycle guard prevents infinite tool loops")

    scheduler_path = REPO_ROOT / "core" / "tasks" / "scheduler.py"
    scheduler_text = scheduler_path.read_text(encoding="utf-8", errors="replace")
    forbidden = ("tool_decision", "tool_executor", "filesystem_tools")
    leaked = [item for item in forbidden if item in scheduler_text]
    if leaked:
        return fail(f"scheduler imports/mentions tool layer details: {leaked}")
    pass_step("scheduler remains unaware of tool decision internals")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
