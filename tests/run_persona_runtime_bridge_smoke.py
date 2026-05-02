from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.persona.runtime_bridge import PersonaRuntimeBridge


PREFIX = "[persona-runtime-bridge-smoke]"
SHARED = REPO_ROOT / "workspace" / "shared"
INPUT = SHARED / "input.txt"
SUMMARY = SHARED / "summary.txt"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    SHARED.mkdir(parents=True, exist_ok=True)
    INPUT.write_text("Persona runtime bridge input.\n", encoding="utf-8")
    if SUMMARY.exists():
        SUMMARY.unlink()

    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    initial = bridge.get_display_state()
    if initial.get("runtime_status") not in {"planning", "executing", "blocked", "done", "failed"}:
        return fail(f"initial status is not UI-safe: {initial}")
    pass_step("bridge exposes UI-safe initial status")

    display = bridge.submit_ui_task("read workspace/shared/input.txt and write workspace/shared/summary.txt")
    if display.get("runtime_status") != "done":
        return fail(f"runtime demo did not finish as done: {display}")
    pass_step("bridge can create and run a ZERO runtime task")

    if not SUMMARY.exists():
        return fail(f"summary file missing: {SUMMARY}")
    summary_text = SUMMARY.read_text(encoding="utf-8", errors="replace")
    if "Persona runtime bridge input." not in summary_text:
        return fail(f"summary file missing expected content: {summary_text}")
    pass_step("runtime task generated summary artifact")

    status = bridge.get_display_state()
    if status.get("display_state_source") != "runtime_bridge":
        return fail(f"display state is not sourced from runtime_bridge: {status}")
    if status.get("task_goal") == "":
        return fail(f"task goal missing from display state: {status}")
    if status.get("controller_status") not in {"allowed", "blocked", "needs_confirmation", "answer_directly", "failed"}:
        return fail(f"controller status missing from display state: {status}")
    if "risk_level" not in status:
        return fail(f"risk level missing from display state: {status}")
    if not isinstance(status.get("confirmation_required"), bool):
        return fail(f"confirmation flag missing from display state: {status}")
    if status.get("status_source") not in {"execution_trace", "execution_log", "runtime_execution"}:
        return fail(f"status is not sourced from runtime trace/log: {status}")
    pass_step("display state is derived from runtime bridge trace/log data")

    trace = status.get("trace")
    if not isinstance(trace, list) or not trace:
        return fail(f"trace missing from display state: {status}")
    if trace[0].get("event_type") != "tool_call":
        return fail(f"trace does not contain tool_call events: {trace}")
    pass_step("trace contains tool_call events")

    tool_calls = status.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) < 2:
        return fail(f"tool calls missing from display state: {status}")
    tool_names = {item.get("tool") for item in tool_calls if isinstance(item, dict)}
    if not {"file_read", "file_write", "github_commit"}.issubset(tool_names):
        return fail(f"expected file_read/file_write/github_commit tool calls: {tool_calls}")
    pass_step("display state includes tool calls")

    github_call = next((item for item in tool_calls if isinstance(item, dict) and item.get("tool") == "github_commit"), {})
    if github_call.get("status") != "success":
        return fail(f"github_commit did not succeed in timeline tool calls: {tool_calls}")
    if "files=" not in str(github_call.get("args_summary") or ""):
        return fail(f"github_commit args summary missing files: {github_call}")
    pass_step("tool call timeline includes github_commit args summary")

    timeline = status.get("timeline")
    if not isinstance(timeline, list) or len(timeline) < 5:
        return fail(f"timeline missing planning/tool/result events: {status}")
    labels = [str(item.get("label") or "") for item in timeline if isinstance(item, dict)]
    if not any("Step 1: planning" in label for label in labels):
        return fail(f"timeline missing planning step: {timeline}")
    if not any("Step 2: executing tool (github_commit)" in label for label in labels):
        return fail(f"timeline missing github_commit execution step: {timeline}")
    if not any("Step 3: result" in label for label in labels):
        return fail(f"timeline missing result step: {timeline}")
    if not all(item.get("timestamp") for item in timeline if isinstance(item, dict)):
        return fail(f"timeline events missing timestamps: {timeline}")
    pass_step("timeline shows ordered planning, tool execution, and result steps")

    result_summary = str(status.get("result_summary") or "")
    if "commit" not in result_summary.lower() and "success" not in result_summary.lower():
        return fail(f"result summary missing expected content: {status}")
    pass_step("display state includes result summary")

    replay = bridge.replay_last_task()
    if replay.get("replay") is not True:
        return fail(f"replay flag missing: {replay}")
    if replay.get("timeline") != status.get("timeline"):
        return fail("replay should return the last recorded timeline without rerunning")
    pass_step("bridge can replay the last task trace")

    text = bridge.format_display_text()
    for needle in ("[PERSONA RUNTIME]", "Status", "Controller", "Risk", "Confirmation", "Display Source", "Task Goal", "[TASK FLOW]", "[TOOL CALLS]", "[RESULT]"):
        if needle not in text:
            return fail(f"formatted display missing {needle}: {text}")
    pass_step("bridge formats a UI-readable text panel")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
