from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.runtime.task_runtime import TaskRuntime
from tests.isolation_helper import isolated_workspace


class FakePendingReviewRunner:
    def __init__(self) -> None:
        self.call_count = 0

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.call_count += 1
        review_payload = {
            "ok": True,
            "status": "pending_review",
            "review_id": "review-smoke-001",
            "requires_review": True,
            "agent_action": "await_review_decision",
            "reason": "repo edit requires human review",
        }
        return {
            "ok": True,
            "action": "repo_edit_review",
            "status": "pending_review",
            "runtime_state": {
                "status": "pending_review",
                "current_step_index": 0,
                "steps_total": 1,
                "results": [],
                "step_results": [],
                "execution_log": [],
                "execution_trace": [],
                "last_step_result": review_payload,
                "last_error": None,
                "final_answer": "",
            },
            "last_result": review_payload,
        }


def fail(message: str) -> int:
    print(f"[pending-review-gate-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[pending-review-gate-smoke] PASS: {message}")


def make_task(workspace: Path, task_id: str) -> Dict[str, Any]:
    task_dir = workspace / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return {
        "id": task_id,
        "task_id": task_id,
        "task_name": task_id,
        "title": "Pending review gate smoke",
        "goal": "Verify pending_review stops the agent loop.",
        "status": "queued",
        "steps": [{"type": "repo_edit", "title": "edit file with review"}],
        "steps_total": 1,
        "current_step_index": 0,
        "results": [],
        "step_results": [],
        "execution_log": [],
        "execution_trace": [],
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "task_dir": str(task_dir),
    }


def assert_waiting_review_result(result: Dict[str, Any]) -> Optional[str]:
    if result.get("status") != "blocked":
        return f"expected status blocked, got {result.get('status')}"
    if result.get("action") != "await_review_decision":
        return f"expected action await_review_decision, got {result.get('action')}"
    if result.get("loop_decision") != "pending_review":
        return f"expected loop_decision pending_review, got {result.get('loop_decision')}"
    if result.get("next_action") != "wait_for_review":
        return f"expected next_action wait_for_review, got {result.get('next_action')}"
    if result.get("review_id") != "review-smoke-001":
        return f"expected review_id review-smoke-001, got {result.get('review_id')}"

    task = result.get("task")
    if not isinstance(task, dict):
        return "result.task missing"
    if task.get("status") != "blocked":
        return f"expected task.status blocked, got {task.get('status')}"
    if task.get("review_status") != "waiting_review":
        return f"expected task.review_status waiting_review, got {task.get('review_status')}"
    if task.get("review_id") != "review-smoke-001":
        return f"expected task.review_id review-smoke-001, got {task.get('review_id')}"
    if task.get("requires_review") is not True:
        return f"expected task.requires_review True, got {task.get('requires_review')}"
    if task.get("agent_action") != "await_review_decision":
        return f"expected task.agent_action await_review_decision, got {task.get('agent_action')}"
    return None


def main() -> int:
    print("[pending-review-gate-smoke] START")

    with isolated_workspace("pending_review_gate") as workspace:
        runtime = TaskRuntime(workspace_root=str(workspace))
        runner = FakePendingReviewRunner()
        agent = AgentLoop(task_runner=runner, task_runtime=runtime, debug=False)
        task = make_task(workspace, "pending_review_gate_task")

        result = agent.run_task_loop(
            task=task,
            current_tick=1,
            user_input="fake pending review task",
            original_plan={"ok": True, "steps": task["steps"]},
        )

        error = assert_waiting_review_result(result)
        if error:
            return fail(error)
        pass_step("run_task_loop stops at pending_review")

        runtime_state_file = Path(task["runtime_state_file"])
        if not runtime_state_file.exists():
            return fail("runtime_state.json was not written")

        runtime_state = json.loads(runtime_state_file.read_text(encoding="utf-8"))
        if runtime_state.get("status") != "blocked":
            return fail(f"expected runtime status blocked, got {runtime_state.get('status')}")
        if runtime_state.get("review_status") != "waiting_review":
            return fail(
                f"expected runtime review_status waiting_review, got {runtime_state.get('review_status')}"
            )
        if runtime_state.get("review_id") != "review-smoke-001":
            return fail(f"expected runtime review_id, got {runtime_state.get('review_id')}")
        pass_step("runtime_state records review gate")

        terminal_runner = FakePendingReviewRunner()
        terminal_agent = AgentLoop(task_runner=terminal_runner, task_runtime=runtime, debug=False)
        terminal_task = make_task(workspace, "pending_review_until_terminal_task")
        terminal_result = terminal_agent.run_task_until_terminal(
            task=terminal_task,
            current_tick=1,
            user_input="fake pending review until terminal",
            original_plan={"ok": True, "steps": terminal_task["steps"]},
            max_cycles=3,
        )

        if terminal_runner.call_count != 1:
            return fail(f"expected run_task_until_terminal to stop after 1 call, got {terminal_runner.call_count}")
        if terminal_result.get("stop_reason") != "wait_for_review":
            return fail(f"expected stop_reason wait_for_review, got {terminal_result.get('stop_reason')}")
        if terminal_result.get("status") != "blocked":
            return fail(f"expected terminal status blocked, got {terminal_result.get('status')}")
        pass_step("run_task_until_terminal does not continue after pending_review")

    print("[pending-review-gate-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
