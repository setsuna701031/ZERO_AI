from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop


SHARED_DIR = REPO_ROOT / "workspace" / "shared"

INPUT_PATH = SHARED_DIR / "agent_loop_capability_input.txt"
SUMMARY_OUTPUT_PATH = SHARED_DIR / "agent_loop_capability_summary.txt"
ACTION_ITEMS_OUTPUT_PATH = SHARED_DIR / "agent_loop_capability_action_items.txt"


class FakeRouter:
    def route(self, context: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        return {
            "mode": "task",
            "task": True,
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "input_path": str(INPUT_PATH),
            "summary_output_path": str(SUMMARY_OUTPUT_PATH),
            "action_items_output_path": str(ACTION_ITEMS_OUTPUT_PATH),
            "capability_hint": {
                "matched": True,
                "capability": "document_flow",
                "operation": "summary_and_action_items",
                "reason": "explicit_path_smoke",
                "input_path": str(INPUT_PATH),
                "summary_output_path": str(SUMMARY_OUTPUT_PATH),
                "action_items_output_path": str(ACTION_ITEMS_OUTPUT_PATH),
            },
            "capability_registry_hint": {
                "capability": "document_flow",
                "operation": "summary_and_action_items",
                "registry_operation": "run_summary_and_action_items",
                "capability_registered": True,
                "operation_registered": True,
            },
        }


class FakePlanner:
    def plan(self, context: Dict[str, Any], user_input: str, route: Any = None) -> Dict[str, Any]:
        return {
            "ok": True,
            "planner_mode": "capability_explicit_path_smoke",
            "intent": "task",
            "final_answer": "",
            "steps": [],
            "meta": {
                "fallback_used": False,
                "step_count": 0,
            },
        }


class FakeScheduler:
    def __init__(self) -> None:
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.counter = 0

    def create_task(
        self,
        goal: str,
        priority: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[list] = None,
    ) -> Dict[str, Any]:
        self.counter += 1
        task_id = f"agent_loop_capability_explicit_paths_{self.counter}"
        task_dir = REPO_ROOT / "workspace" / "tasks" / task_id

        task = {
            "id": task_id,
            "task_id": task_id,
            "task_name": task_id,
            "title": goal,
            "goal": goal,
            "status": "queued",
            "priority": priority,
            "timeout_ticks": timeout_ticks,
            "depends_on": depends_on or [],
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "steps": [],
            "steps_total": 0,
            "current_step_index": 0,
            "results": [],
            "step_results": [],
            "execution_log": [],
            "execution_trace": [],
            "final_answer": "",
        }

        self.tasks[task_id] = task
        return {
            "ok": True,
            "task_name": task_id,
            "task": task,
        }

    def submit_existing_task(self, task_id: str) -> Dict[str, Any]:
        task = self.tasks.get(task_id)
        if isinstance(task, dict):
            task["status"] = "queued"
        return {
            "ok": True,
            "task_id": task_id,
            "status": "queued",
        }

    def _get_task_from_repo(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.tasks.get(task_id)

    def _persist_task_payload(self, task_id: str, task: Dict[str, Any]) -> None:
        self.tasks[task_id] = dict(task)


def fail(message: str) -> int:
    print(f"[agent-loop-capability-explicit-paths-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[agent-loop-capability-explicit-paths-smoke] PASS: {message}")


def write_input() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_PATH.write_text(
        (
            "AgentLoop Capability Explicit Paths Notes\n\n"
            "Alice will finish the explicit-path task draft by Friday.\n"
            "Bob will verify that AgentLoop generates capability_execution enabled tasks.\n"
            "Carol will prepare the release note before the internal demo.\n"
        ),
        encoding="utf-8",
    )


def main() -> int:
    print("[agent-loop-capability-explicit-paths-smoke] START")
    print(f"[agent-loop-capability-explicit-paths-smoke] repo: {REPO_ROOT}")

    write_input()
    pass_step(f"input written: {INPUT_PATH}")

    scheduler = FakeScheduler()
    agent = AgentLoop(
        router=FakeRouter(),
        planner=FakePlanner(),
        scheduler=scheduler,
        debug=False,
    )

    result = agent.run(
        "Use document_flow capability with explicit paths to produce summary and action items."
    )

    print("[agent-loop-capability-explicit-paths-smoke] agent result")
    for key in ("ok", "mode", "final_answer", "error"):
        print(f"{key}: {result.get(key)}")

    if not result.get("ok"):
        return fail(f"AgentLoop returned non-ok: {result.get('error')}")

    extra_task = result.get("task")
    if not isinstance(extra_task, dict):
        return fail("result.task missing or invalid")

    capability_execution = extra_task.get("capability_execution")
    if not isinstance(capability_execution, dict):
        return fail("task.capability_execution missing")

    if capability_execution.get("enabled") is not True:
        return fail(f"expected capability_execution.enabled=True, got: {capability_execution}")

    if capability_execution.get("status") != "pending":
        return fail(f"expected capability_execution.status=pending, got: {capability_execution.get('status')}")

    expected_paths = {
        "input_path": str(INPUT_PATH),
        "summary_output_path": str(SUMMARY_OUTPUT_PATH),
        "action_items_output_path": str(ACTION_ITEMS_OUTPUT_PATH),
    }

    for key, expected in expected_paths.items():
        actual = str(capability_execution.get(key) or "")
        if actual != expected:
            return fail(f"{key} mismatch: expected {expected}, got {actual}")
        pass_step(f"{key} carried into capability_execution")

    if extra_task.get("capability") != "document_flow":
        return fail(f"task.capability mismatch: {extra_task.get('capability')}")

    if extra_task.get("operation") != "summary_and_action_items":
        return fail(f"task.operation mismatch: {extra_task.get('operation')}")

    pass_step("AgentLoop produced enabled capability task with explicit paths")

    print("[agent-loop-capability-explicit-paths-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())