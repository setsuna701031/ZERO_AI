from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_registry import ToolRegistry


PREFIX = "[agent-loop-tool-call-smoke]"
SHARED = REPO_ROOT / "workspace" / "shared"
INPUT = SHARED / "input.txt"
SUMMARY = SHARED / "summary.txt"


class ToolCallPlanner:
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


class InvalidToolPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "missing_tool",
                "args": {},
            },
        }


class BlockedWritePlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "file_write",
                "args": {
                    "path": "../outside.txt",
                    "content": "nope",
                },
            },
        }


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    SHARED.mkdir(parents=True, exist_ok=True)
    INPUT.write_text("Tool call input for agent loop.\n", encoding="utf-8")
    if SUMMARY.exists():
        SUMMARY.unlink()

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    loop = AgentLoop(
        planner=ToolCallPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    result = loop.run("read input and write summary")
    if not result.get("ok"):
        return fail(f"agent loop failed: {result}")
    pass_step("agent loop executed tool_calls")

    if not SUMMARY.exists():
        return fail(f"summary file missing: {SUMMARY}")
    summary_text = SUMMARY.read_text(encoding="utf-8", errors="replace")
    if "Tool call input for agent loop." not in summary_text:
        return fail(f"summary file did not contain observed tool output: {summary_text}")
    pass_step("summary file generated from file_read observation")

    execution = result.get("execution")
    if not isinstance(execution, dict):
        return fail(f"execution missing: {result}")

    execution_log = execution.get("execution_log")
    if not isinstance(execution_log, list) or len(execution_log) < 2:
        return fail(f"execution_log missing tool_call records: {execution}")
    if not all(item.get("event_type") == "tool_call" for item in execution_log):
        return fail(f"execution_log contains non-tool_call records: {execution_log}")
    pass_step("execution_log contains tool_call records")

    execution_trace = execution.get("execution_trace")
    if not isinstance(execution_trace, list) or len(execution_trace) < 2:
        return fail(f"execution_trace missing tool_call records: {execution}")
    pass_step("execution_trace contains tool_call records")

    invalid_loop = AgentLoop(
        planner=InvalidToolPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    invalid_result = invalid_loop.run("call missing tool")
    invalid_execution = invalid_result.get("execution") if isinstance(invalid_result, dict) else {}
    invalid_last = invalid_execution.get("last_result") if isinstance(invalid_execution, dict) else {}
    if invalid_last.get("status") != "invalid_tool":
        return fail(f"invalid tool did not return invalid_tool: {invalid_result}")
    pass_step("invalid tool_call returns invalid_tool without crashing")

    blocked_loop = AgentLoop(
        planner=BlockedWritePlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    blocked_result = blocked_loop.run("attempt unsafe write")
    blocked_execution = blocked_result.get("execution") if isinstance(blocked_result, dict) else {}
    blocked_last = blocked_execution.get("last_result") if isinstance(blocked_execution, dict) else {}
    if blocked_last.get("status") != "blocked":
        return fail(f"unsafe write did not return blocked: {blocked_result}")
    pass_step("unsafe file_write returns blocked without executing")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
