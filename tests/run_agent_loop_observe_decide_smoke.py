from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop


class FakeTaskRunner:
    def __init__(
        self,
        *,
        ok: bool,
        status: str,
        action: str,
        current_step_index: int,
        steps_total: int,
        error: str = "",
    ) -> None:
        self.ok = ok
        self.status = status
        self.action = action
        self.current_step_index = current_step_index
        self.steps_total = steps_total
        self.error = error

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        is_finished = self.status == "finished"
        final_answer = "fake task finished" if is_finished else ""

        runtime_state = {
            "status": self.status,
            "current_step_index": self.current_step_index,
            "steps_total": self.steps_total,
            "results": [
                {
                    "step_index": max(1, self.current_step_index),
                    "result": {
                        "ok": self.ok,
                        "final_answer": final_answer,
                        "error": self.error or None,
                    },
                }
            ],
            "step_results": [],
            "execution_log": [],
            "execution_trace": [],
            "last_step_result": {
                "ok": self.ok,
                "final_answer": final_answer,
                "error": self.error or None,
            },
            "last_error": self.error or None,
            "final_answer": final_answer,
        }

        return {
            "ok": self.ok,
            "action": self.action,
            "status": self.status,
            "final_answer": final_answer,
            "error": self.error or None,
            "runtime_state": runtime_state,
            "last_result": {
                "ok": self.ok,
                "final_answer": final_answer,
                "error": self.error or None,
            },
            "execution_trace": [],
        }


def fail(message: str) -> int:
    print(f"[agent-loop-observe-decide-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[agent-loop-observe-decide-smoke] PASS: {message}")


def make_task(
    case_name: str,
    *,
    steps_total: int = 1,
    max_replans: int = 1,
    replan_count: int = 0,
) -> Dict[str, Any]:
    steps = [
        {
            "type": "noop",
            "title": f"fake step {index + 1}",
        }
        for index in range(max(1, steps_total))
    ]

    return {
        "id": f"agent_loop_observe_decide_{case_name}",
        "task_id": f"agent_loop_observe_decide_{case_name}",
        "task_name": f"agent_loop_observe_decide_{case_name}",
        "title": f"AgentLoop observe decide smoke {case_name}",
        "goal": "Verify AgentLoop records observe/decide metadata.",
        "status": "queued",
        "steps": steps,
        "steps_total": len(steps),
        "current_step_index": 0,
        "results": [],
        "step_results": [],
        "execution_log": [],
        "execution_trace": [],
        "last_step_result": None,
        "last_error": None,
        "final_answer": "",
        "max_replans": max_replans,
        "replan_count": replan_count,
    }


def run_case(
    *,
    case_name: str,
    runner_ok: bool,
    runner_status: str,
    runner_action: str,
    current_step_index: int,
    steps_total: int,
    expected_ok: bool,
    expected_decision: str,
    expected_next_action: str,
    expected_terminal: bool,
    expected_should_replan: bool,
    expected_should_fail: bool,
    max_replans: int = 1,
    replan_count: int = 0,
    error: str = "",
) -> int:
    print(f"[agent-loop-observe-decide-smoke] CASE: {case_name}")

    task = make_task(
        case_name,
        steps_total=steps_total,
        max_replans=max_replans,
        replan_count=replan_count,
    )

    agent = AgentLoop(
        task_runner=FakeTaskRunner(
            ok=runner_ok,
            status=runner_status,
            action=runner_action,
            current_step_index=current_step_index,
            steps_total=steps_total,
            error=error,
        ),
        debug=False,
    )

    result = agent.run_task_loop(
        task=task,
        current_tick=1,
        user_input=f"fake observe decide test {case_name}",
        original_plan={
            "ok": True,
            "steps": task["steps"],
        },
    )

    print("[agent-loop-observe-decide-smoke] result")
    for key in (
        "ok",
        "mode",
        "action",
        "status",
        "loop_decision",
        "next_action",
        "final_answer",
        "error",
    ):
        print(f"{key}: {result.get(key)}")

    if bool(result.get("ok")) is not expected_ok:
        return fail(f"{case_name}: expected ok={expected_ok}, got: {result.get('ok')}")

    if result.get("mode") != "task_loop":
        return fail(f"{case_name}: expected mode task_loop, got: {result.get('mode')}")

    if result.get("loop_decision") != expected_decision:
        return fail(
            f"{case_name}: expected loop_decision {expected_decision}, got: {result.get('loop_decision')}"
        )

    if result.get("next_action") != expected_next_action:
        return fail(
            f"{case_name}: expected next_action {expected_next_action}, got: {result.get('next_action')}"
        )

    returned_task = result.get("task")
    if not isinstance(returned_task, dict):
        return fail(f"{case_name}: result.task missing or invalid")

    if returned_task.get("last_decision") != expected_decision:
        return fail(f"{case_name}: task.last_decision mismatch: {returned_task.get('last_decision')}")
    pass_step(f"{case_name}: task.last_decision recorded")

    if returned_task.get("next_action") != expected_next_action:
        return fail(f"{case_name}: task.next_action mismatch: {returned_task.get('next_action')}")
    pass_step(f"{case_name}: task.next_action recorded")

    last_observation = returned_task.get("last_observation")
    if not isinstance(last_observation, dict) or not last_observation:
        return fail(f"{case_name}: task.last_observation missing")
    pass_step(f"{case_name}: task.last_observation recorded")

    observation_status = str(last_observation.get("status") or "").strip().lower()
    if observation_status != runner_status:
        return fail(f"{case_name}: last_observation.status expected {runner_status}, got: {observation_status}")
    pass_step(f"{case_name}: last_observation.status verified")

    loop_cycle_count = returned_task.get("loop_cycle_count")
    if not isinstance(loop_cycle_count, int) or loop_cycle_count < 1:
        return fail(f"{case_name}: task.loop_cycle_count expected >= 1, got: {loop_cycle_count}")
    pass_step(f"{case_name}: task.loop_cycle_count incremented")

    loop_history = returned_task.get("loop_history")
    if not isinstance(loop_history, list) or len(loop_history) < 1:
        return fail(f"{case_name}: task.loop_history expected at least 1 item, got: {loop_history}")
    pass_step(f"{case_name}: task.loop_history recorded")

    history_item = loop_history[-1]
    if not isinstance(history_item, dict):
        return fail(f"{case_name}: last loop_history item invalid")

    if history_item.get("decision") != expected_decision:
        return fail(f"{case_name}: loop_history decision mismatch: {history_item.get('decision')}")

    if history_item.get("next_action") != expected_next_action:
        return fail(f"{case_name}: loop_history next_action mismatch: {history_item.get('next_action')}")

    if history_item.get("terminal") is not expected_terminal:
        return fail(
            f"{case_name}: loop_history terminal expected {expected_terminal}, got: {history_item.get('terminal')}"
        )

    if bool(history_item.get("should_replan")) is not expected_should_replan:
        return fail(
            f"{case_name}: loop_history should_replan expected {expected_should_replan}, got: {history_item.get('should_replan')}"
        )

    if bool(history_item.get("should_fail")) is not expected_should_fail:
        return fail(
            f"{case_name}: loop_history should_fail expected {expected_should_fail}, got: {history_item.get('should_fail')}"
        )

    history_observation = history_item.get("observation")
    if not isinstance(history_observation, dict):
        return fail(f"{case_name}: loop_history observation missing")

    history_status = str(history_observation.get("status") or "").strip().lower()
    if history_status != runner_status:
        return fail(f"{case_name}: loop_history observation.status expected {runner_status}, got: {history_status}")

    if expected_terminal:
        terminal_reason = str(returned_task.get("terminal_reason") or "").strip()
        if not terminal_reason:
            return fail(f"{case_name}: terminal_reason should be recorded")
    else:
        terminal_reason = str(returned_task.get("terminal_reason") or "").strip()
        if terminal_reason:
            return fail(f"{case_name}: terminal_reason should remain empty, got: {terminal_reason}")

    pass_step(f"{case_name}: loop_history content verified")
    return 0


def main() -> int:
    print("[agent-loop-observe-decide-smoke] START")

    cases = [
        {
            "case_name": "finish",
            "runner_ok": True,
            "runner_status": "finished",
            "runner_action": "already_finished",
            "current_step_index": 1,
            "steps_total": 1,
            "expected_ok": True,
            "expected_decision": "finish",
            "expected_next_action": "finish",
            "expected_terminal": True,
            "expected_should_replan": False,
            "expected_should_fail": False,
        },
        {
            "case_name": "continue",
            "runner_ok": True,
            "runner_status": "running",
            "runner_action": "step_completed",
            "current_step_index": 0,
            "steps_total": 2,
            "expected_ok": True,
            "expected_decision": "continue",
            "expected_next_action": "run_next_tick",
            "expected_terminal": False,
            "expected_should_replan": False,
            "expected_should_fail": False,
        },
        {
            "case_name": "replan",
            "runner_ok": False,
            "runner_status": "failed",
            "runner_action": "step_failed",
            "current_step_index": 1,
            "steps_total": 2,
            "expected_ok": False,
            "expected_decision": "replan",
            "expected_next_action": "replan",
            "expected_terminal": False,
            "expected_should_replan": True,
            "expected_should_fail": False,
            "max_replans": 1,
            "replan_count": 0,
            "error": "fake recoverable failure",
        },
        {
            "case_name": "fail_no_replan",
            "runner_ok": False,
            "runner_status": "failed",
            "runner_action": "step_failed",
            "current_step_index": 1,
            "steps_total": 2,
            "expected_ok": False,
            "expected_decision": "fail",
            "expected_next_action": "finish",
            "expected_terminal": True,
            "expected_should_replan": False,
            "expected_should_fail": True,
            "max_replans": 1,
            "replan_count": 1,
            "error": "fake unrecoverable failure",
        },
        {
            "case_name": "blocked",
            "runner_ok": False,
            "runner_status": "blocked",
            "runner_action": "guard_blocked",
            "current_step_index": 0,
            "steps_total": 1,
            "expected_ok": False,
            "expected_decision": "blocked",
            "expected_next_action": "finish",
            "expected_terminal": True,
            "expected_should_replan": False,
            "expected_should_fail": True,
            "error": "fake guard blocked",
        },
    ]

    for case in cases:
        result = run_case(**case)
        if result != 0:
            return result

    print("[agent-loop-observe-decide-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())