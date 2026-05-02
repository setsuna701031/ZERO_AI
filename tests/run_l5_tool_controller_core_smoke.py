from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_controller import ALLOW_TOOL, ANSWER_DIRECTLY, REPLAN, STOP
from core.tools.tool_failure_policy import CAN_RETRY, MUST_STOP, NEED_REPLAN, classify_tool_failure
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-tool-controller-core-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class ReadWritePlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_tool_controller/input.txt"},
            }
        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        if observation.get("type") == "file_write":
            return {"type": "respond", "message": "done"}
        return {
            "type": "tool_call",
            "tool": "write_file",
            "args": {
                "path": "shared/l5_tool_controller/output.txt",
                "content": "controller chained write\n",
                "allow_overwrite": True,
            },
        }


def main() -> int:
    workspace = REPO_ROOT / "workspace" / "shared" / "l5_tool_controller"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "input.txt").write_text("controller input\n", encoding="utf-8")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = ToolCallExecutor(registry)

    direct = executor.execute_decision(
        {"type": "respond", "message": "answer directly"},
        source="controller_smoke",
    )
    if direct.get("status") != "no_tool" or direct.get("final_decision") != ANSWER_DIRECTLY:
        return fail(f"direct answer did not route through ANSWER_DIRECTLY: {direct}")
    pass_step("direct answer does not execute a tool")

    read = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "read_file",
            "args": {"path": "shared/l5_tool_controller/input.txt"},
        },
        source="controller_smoke",
    )
    if read.get("ok") is not True or read.get("final_decision") != ALLOW_TOOL:
        return fail(f"read_file was not allowed by controller: {read}")
    pass_step("read_file executes only after final ALLOW_TOOL decision")

    loop = AgentLoop(
        planner=ReadWritePlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=3,
    )
    chain = loop.run("read then write")
    execution = chain.get("execution") if isinstance(chain.get("execution"), dict) else {}
    results = execution.get("results") if isinstance(execution.get("results"), list) else []
    decisions = [
        item.get("result", {}).get("final_decision")
        for item in results
        if isinstance(item, dict)
    ]
    if chain.get("ok") is not True or decisions[:2] != [ALLOW_TOOL, ALLOW_TOOL]:
        return fail(f"read->write chain did not use controller ALLOW_TOOL decisions: {chain}")
    if not (workspace / "output.txt").exists():
        return fail("read->write chain did not create output file")
    pass_step("read -> write chain is controlled and observable")

    invalid = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {}},
        source="controller_smoke",
    )
    if invalid.get("status") != "invalid_args" or invalid.get("final_decision") != REPLAN:
        return fail(f"invalid args did not map to REPLAN without execution: {invalid}")
    if classify_tool_failure("invalid_args").get("decision_class") != CAN_RETRY:
        return fail("failure taxonomy did not classify invalid_args as CAN_RETRY")
    if classify_tool_failure("tool_not_found").get("decision_class") != MUST_STOP:
        return fail("failure taxonomy did not classify tool_not_found as MUST_STOP")
    if classify_tool_failure("failed").get("decision_class") != NEED_REPLAN:
        return fail("failure taxonomy did not classify failed as NEED_REPLAN")
    pass_step("failure taxonomy stays simple for decision and detailed for logs")

    stopped = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "read_file",
            "args": {"path": "shared/l5_tool_controller/input.txt"},
        },
        source="controller_smoke",
        decision_input={
            "goal": "budget stop",
            "requested_tool": "read_file",
            "last_tool": "",
            "observation_summary": "",
            "previous_failures": [],
            "budget_remaining": {},
            "tool_budget": {
                "max_loop_steps": 1,
                "max_tool_calls": 0,
                "max_same_tool_repeats": 1,
                "max_retries_per_tool": 1,
            },
            "loop_steps": 0,
            "tool_calls": 0,
            "same_tool_repeats": 0,
            "retries_for_tool": 0,
        },
    )
    if stopped.get("final_decision") != STOP or stopped.get("ok") is not False:
        return fail(f"budget exhaustion did not STOP before execution: {stopped}")
    controller = stopped.get("output", {}).get("controller") if isinstance(stopped.get("output"), dict) else {}
    budget = controller.get("budget_recommendation") if isinstance(controller, dict) else {}
    if budget.get("reason") != "max_tool_calls_exhausted":
        return fail(f"budget stop did not use termination priority: {stopped}")
    pass_step("budget exhaustion produces final STOP decision")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
