from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_controller import DENY_TOOL
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-stability-reproducibility-smoke]"
WORKSPACE = REPO_ROOT / "workspace" / "shared" / "l5_stability_reproducibility"
INPUT_PATH = WORKSPACE / "input.txt"
MAX_TRACE_EVENTS = 12
MAX_IDENTICAL_PROPOSAL_REPEAT = 1


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class ReproducibleTaskPlanner:
    def __init__(self, output_name: str) -> None:
        self.output_name = output_name

    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        output_path = f"shared/l5_stability_reproducibility/{self.output_name}"

        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_stability_reproducibility/input.txt"},
            }

        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        if observation.get("type") == "file_content" and data.get("path") == "shared/l5_stability_reproducibility/input.txt":
            observed_content = str(data.get("content") or "")
            return {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "path": output_path,
                    "content": f"stable observed copy:\n{observed_content}",
                    "allow_overwrite": True,
                },
            }

        if observation.get("type") == "file_write":
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": output_path},
            }

        return {"type": "respond", "message": "stability run complete"}


def main() -> int:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    source_text = "stable reproducible payload\n"
    INPUT_PATH.write_text(source_text, encoding="utf-8")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    run_summaries: List[Dict[str, Any]] = []

    for run_index in range(1, 4):
        summary = _run_real_task(registry, run_index, source_text)
        if not summary.get("ok"):
            return fail(str(summary.get("error") or summary))
        run_summaries.append(summary)
        pass_step(f"real task run {run_index} is stable and observable")

    tool_sequences = [summary["essential_tools"] for summary in run_summaries]
    if any(sequence != ["read_file", "write_file", "read_file"] for sequence in tool_sequences):
        return fail(f"essential tool sequence changed across runs: {tool_sequences}")
    pass_step("essential tool sequence is stable across three runs")

    decision_sequences = [summary["final_decisions"] for summary in run_summaries]
    if any(sequence != ["ALLOW_TOOL", "ALLOW_TOOL", "ALLOW_TOOL"] for sequence in decision_sequences):
        return fail(f"final decisions are unstable or unexpected: {decision_sequences}")
    pass_step("controller final decisions remain stable")

    for summary in run_summaries:
        budget_shapes = summary["budget_shapes"]
        if len(budget_shapes) < 3 or not all(_valid_budget_shape(item) for item in budget_shapes[:3]):
            return fail(f"budget remaining shape is invalid: {budget_shapes}")
    pass_step("budget remaining is structurally valid across runs")

    failure = _run_denied_failure_path(registry)
    if not failure.get("ok"):
        return fail(str(failure.get("error") or failure))
    pass_step("denied failure path is reproducible and does not execute a tool")

    print(f"{PREFIX} ALL PASS")
    return 0


def _run_real_task(registry: ToolRegistry, run_index: int, source_text: str) -> Dict[str, Any]:
    output_path = WORKSPACE / f"output_{run_index}.txt"
    if output_path.exists():
        output_path.unlink()

    loop = AgentLoop(
        planner=ReproducibleTaskPlanner(output_name=output_path.name),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=4,
    )
    result = loop.run(f"run stable read/write/verify task {run_index}")
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    results = execution.get("results") if isinstance(execution.get("results"), list) else []
    events = _events_from_execution(execution)

    if result.get("ok") is not True:
        return {"ok": False, "error": f"run {run_index} failed: {result}"}
    if len(events) > MAX_TRACE_EVENTS:
        return {"ok": False, "error": f"run {run_index} trace too long: {len(events)}"}

    tools = [item.get("result", {}).get("tool") for item in results if isinstance(item, dict)]
    essential_tools = _essential_chain(tools)
    if essential_tools != ["read_file", "write_file", "read_file"]:
        return {"ok": False, "error": f"run {run_index} missing essential chain: {tools}"}

    if not output_path.exists():
        return {"ok": False, "error": f"run {run_index} output missing: {output_path}"}
    output_text = output_path.read_text(encoding="utf-8", errors="replace")
    if not output_text.strip() or source_text not in output_text:
        return {"ok": False, "error": f"run {run_index} output empty or not observation-derived: {output_text!r}"}

    tool_events = [event for event in events if event.get("tool") in {"read_file", "write_file"}]
    if len(tool_events) < 3:
        return {"ok": False, "error": f"run {run_index} missing controller trace events: {events}"}

    for event_index, event in enumerate(tool_events[:3], start=1):
        if not isinstance(event.get("decision_input"), dict):
            return {"ok": False, "error": f"run {run_index} event {event_index} missing decision_input: {event}"}
        if not event.get("final_decision"):
            return {"ok": False, "error": f"run {run_index} event {event_index} missing final_decision: {event}"}
        for key in ("why_call_tool", "why_not_call_tool", "why_stop_or_replan"):
            if key not in event:
                return {"ok": False, "error": f"run {run_index} event {event_index} missing {key}: {event}"}

    repeats = _proposal_repeat_counts(tool_events)
    excessive = [item for item in repeats if item[1] > MAX_IDENTICAL_PROPOSAL_REPEAT]
    if excessive:
        return {"ok": False, "error": f"run {run_index} repeated identical proposals: {excessive}"}

    if execution.get("stopped_reason") == "max_tool_cycles":
        return {"ok": False, "error": f"run {run_index} stopped at max_tool_cycles: {execution}"}

    return {
        "ok": True,
        "essential_tools": essential_tools,
        "final_decisions": [event.get("final_decision") for event in tool_events[:3]],
        "budget_shapes": [
            event.get("decision_input", {}).get("budget_remaining")
            for event in tool_events[:3]
        ],
    }


def _run_denied_failure_path(registry: ToolRegistry) -> Dict[str, Any]:
    executor = ToolCallExecutor(registry)
    attempts = []
    for _ in range(3):
        result = executor.execute_decision(
            {"type": "tool_call", "tool": "read_file", "args": {"path": "../outside.txt"}},
            source="stability_reproducibility_smoke",
        )
        attempts.append(result)

    decisions = [item.get("final_decision") for item in attempts]
    statuses = [item.get("status") for item in attempts]
    if any(decision != DENY_TOOL for decision in decisions):
        return {"ok": False, "error": f"denied path decisions varied: {decisions}"}
    if any(status != "denied" for status in statuses):
        return {"ok": False, "error": f"denied path statuses varied: {statuses}"}
    if any(item.get("ok") is not False for item in attempts):
        return {"ok": False, "error": f"denied path unexpectedly executed: {attempts}"}
    if any(item.get("request_id") for item in attempts):
        return {"ok": False, "error": f"denied path produced execution request ids: {attempts}"}
    return {"ok": True}


def _events_from_execution(execution: Dict[str, Any]) -> List[Dict[str, Any]]:
    execution_trace = execution.get("execution_trace") if isinstance(execution.get("execution_trace"), list) else []
    execution_log = execution.get("execution_log") if isinstance(execution.get("execution_log"), list) else []
    trace_events = [event for event in execution_trace if isinstance(event, dict)]
    if any(isinstance(event.get("decision_input"), dict) for event in trace_events):
        return trace_events
    return [event for event in execution_log if isinstance(event, dict)]


def _essential_chain(tools: List[Any]) -> List[str]:
    chain: List[str] = []
    for tool in tools:
        if tool in {"read_file", "write_file"}:
            chain.append(str(tool))
    return chain


def _proposal_repeat_counts(events: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for event in events:
        decision_input = event.get("decision_input") if isinstance(event.get("decision_input"), dict) else {}
        key = "|".join(
            [
                str(event.get("tool") or decision_input.get("requested_tool") or ""),
                str(event.get("args_summary") or ""),
                str(decision_input.get("last_tool") or ""),
                str(decision_input.get("observation_summary") or ""),
            ]
        )
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items())


def _valid_budget_shape(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = {"loop_steps", "tool_calls", "same_tool_repeats", "retries_for_tool"}
    if not required.issubset(value.keys()):
        return False
    return all(isinstance(value.get(key), int) and value.get(key) >= 0 for key in required)


if __name__ == "__main__":
    raise SystemExit(main())
