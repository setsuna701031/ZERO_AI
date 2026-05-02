from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_controller import ALLOW_TOOL, ANSWER_DIRECTLY, DENY_TOOL, REPLAN
from core.tools.tool_failure_policy import CAN_RETRY, classify_tool_failure
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-observation-decision-closure-smoke]"
REQUIRED_DECISION_INPUT_KEYS = {
    "goal",
    "requested_tool",
    "last_tool",
    "observation_summary",
    "previous_failures",
    "budget_remaining",
}


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class ObservationClosurePlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_observation_closure/input.txt"},
            }

        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        if observation.get("type") == "file_content" and data.get("path") == "shared/l5_observation_closure/input.txt":
            observed_content = str(data.get("content") or "")
            return {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "path": "shared/l5_observation_closure/output.txt",
                    "content": f"from observation:\n{observed_content}",
                    "allow_overwrite": True,
                },
            }
        if observation.get("type") == "file_write":
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_observation_closure/output.txt"},
            }
        return {"type": "respond", "message": "closure complete"}


def main() -> int:
    workspace = REPO_ROOT / "workspace" / "shared" / "l5_observation_closure"
    workspace.mkdir(parents=True, exist_ok=True)
    source_text = "observed payload 42\n"
    (workspace / "input.txt").write_text(source_text, encoding="utf-8")
    output_path = workspace / "output.txt"
    if output_path.exists():
        output_path.unlink()

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    loop = AgentLoop(
        planner=ObservationClosurePlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=4,
    )
    result = loop.run("copy by using only the previous observation")
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    results = execution.get("results") if isinstance(execution.get("results"), list) else []
    if result.get("ok") is not True or len(results) != 3:
        return fail(f"closure task did not execute read->write->read: {result}")

    expected_output = f"from observation:\n{source_text}"
    actual_output = output_path.read_text(encoding="utf-8", errors="replace")
    if actual_output != expected_output:
        return fail(f"write_file content was not sourced from read_file observation: {actual_output!r}")

    write_result = results[1].get("result") if isinstance(results[1], dict) else {}
    write_args = write_result.get("args") if isinstance(write_result, dict) else {}
    if source_text not in str(write_args.get("content") or ""):
        return fail(f"write_file args did not include first observation content: {write_args}")
    pass_step("write_file content is derived from previous read_file observation")

    execution_log = execution.get("execution_log") if isinstance(execution.get("execution_log"), list) else []
    if len(execution_log) != 3:
        return fail(f"execution_log missing controller decisions: {execution_log}")
    for index, event in enumerate(execution_log, start=1):
        decision_input = event.get("decision_input") if isinstance(event.get("decision_input"), dict) else {}
        missing = sorted(REQUIRED_DECISION_INPUT_KEYS - set(decision_input.keys()))
        if missing:
            return fail(f"decision_input missing keys at event {index}: {missing} in {event}")
        for key in ("why_call_tool", "why_not_call_tool", "why_stop_or_replan"):
            if key not in event:
                return fail(f"{key} missing from controller log event {index}: {event}")
    second_input = execution_log[1].get("decision_input")
    if second_input.get("requested_tool") != "write_file" or second_input.get("last_tool") != "read_file":
        return fail(f"second decision did not bind observation to next tool: {second_input}")
    if "read " not in str(second_input.get("observation_summary") or ""):
        return fail(f"second decision did not carry observation summary: {second_input}")
    pass_step("decision_input and why fields are present in every controller trace event")

    executor = ToolCallExecutor(registry)
    invalid = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {}},
        source="closure_smoke",
    )
    if invalid.get("final_decision") != REPLAN or invalid.get("status") != "invalid_args":
        return fail(f"invalid_args did not route to REPLAN without execution: {invalid}")

    denied = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {"path": "../outside.txt"}},
        source="closure_smoke",
    )
    if denied.get("final_decision") != DENY_TOOL or denied.get("status") != "denied":
        return fail(f"denied path did not route to DENY_TOOL: {denied}")

    repeat = executor.execute_decision(
        {"type": "tool_call", "tool": "read_file", "args": {"path": "shared/l5_observation_closure/input.txt"}},
        source="closure_smoke",
        decision_input={
            "goal": "answer from existing observation",
            "requested_tool": "read_file",
            "last_tool": "read_file",
            "observation_summary": "read 20 chars from shared/l5_observation_closure/input.txt",
            "previous_failures": [],
            "budget_remaining": {},
            "tool_budget": {},
            "loop_steps": 1,
            "tool_calls": 1,
            "same_tool_repeats": 1,
            "retries_for_tool": 0,
        },
    )
    if repeat.get("final_decision") != ANSWER_DIRECTLY or repeat.get("status") != "no_tool":
        return fail(f"same proposal repeat did not answer directly/stop safely: {repeat}")

    if classify_tool_failure("tool_empty_output").get("decision_class") != CAN_RETRY:
        return fail("empty output failure did not classify as CAN_RETRY")
    pass_step("failure branches route to bounded decisions")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
