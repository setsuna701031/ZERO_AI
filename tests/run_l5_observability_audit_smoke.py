from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_audit import AUDIT_RECORD_KEYS, build_l5_audit_records
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-observability-audit-smoke]"
WORKSPACE = REPO_ROOT / "workspace" / "shared" / "l5_observability_audit"
INPUT_PATH = WORKSPACE / "input.txt"
OUTPUT_PATH = WORKSPACE / "output.txt"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


class AuditTaskPlanner:
    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
        previous = context.get("previous_tool_observation")
        if not isinstance(previous, dict):
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_observability_audit/input.txt"},
            }

        observation = previous.get("observation") if isinstance(previous.get("observation"), dict) else {}
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        if observation.get("type") == "file_content" and data.get("path") == "shared/l5_observability_audit/input.txt":
            observed_content = str(data.get("content") or "")
            return {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "path": "shared/l5_observability_audit/output.txt",
                    "content": f"audit observed copy:\n{observed_content}",
                    "allow_overwrite": True,
                },
            }

        if observation.get("type") == "file_write":
            return {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"path": "shared/l5_observability_audit/output.txt"},
            }

        return {"type": "respond", "message": "audit smoke complete"}


def main() -> int:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    source_text = "audit trace payload\n"
    INPUT_PATH.write_text(source_text, encoding="utf-8")
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    loop = AgentLoop(
        planner=AuditTaskPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
        max_tool_cycles=4,
    )
    result = loop.run("run observable L5 audit task")
    result_before = copy.deepcopy(result)
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    records = build_l5_audit_records(execution, run_id="audit_smoke_run")

    if result.get("ok") is not True:
        return fail(f"real L5 task failed before audit formatting: {result}")
    if not records:
        return fail(f"audit records were not generated from trace: {execution}")
    pass_step("audit records are generated from a real L5 trace")

    expected_keys = set(AUDIT_RECORD_KEYS)
    for index, record in enumerate(records, start=1):
        if set(record.keys()) != expected_keys:
            return fail(f"audit record {index} keys are unstable: {record}")
    pass_step("every audit record has stable keys")

    if not any(record.get("final_decision") for record in records):
        return fail(f"final_decision missing from audit: {records}")
    pass_step("final_decision appears in audit")

    if not any(record.get("observation_summary") or isinstance(record.get("budget_remaining"), dict) for record in records):
        return fail(f"decision_input summary missing from audit: {records}")
    pass_step("decision_input appears through stable audit summaries")

    for key in ("why_call_tool", "why_not_call_tool", "why_stop_or_replan"):
        if not all(key in record for record in records):
            return fail(f"{key} missing from audit records: {records}")
    pass_step("why fields appear in audit")

    for key in ("risk_level", "risk_reason", "confirmation_required"):
        if not all(key in record for record in records):
            return fail(f"{key} missing from audit records: {records}")
    pass_step("risk fields appear in audit")

    essential_tools = [record.get("requested_tool") for record in records if record.get("requested_tool") in {"read_file", "write_file"}]
    if essential_tools[:3] != ["read_file", "write_file", "read_file"]:
        return fail(f"audit did not preserve essential tool sequence: {records}")

    if result != result_before:
        return fail("audit formatter altered execution result")
    if not OUTPUT_PATH.exists() or source_text not in OUTPUT_PATH.read_text(encoding="utf-8", errors="replace"):
        return fail("audit formatter changed or lost output artifact")
    pass_step("audit layer does not alter execution result")

    scheduler_text = (REPO_ROOT / "core" / "tasks" / "scheduler.py").read_text(encoding="utf-8", errors="replace")
    if "tool_audit" in scheduler_text or "build_l5_audit_records" in scheduler_text:
        return fail("scheduler.py was coupled to the L5 audit formatter")
    pass_step("scheduler remains unchanged by audit layer")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
