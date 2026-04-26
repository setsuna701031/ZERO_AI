from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop


class SequenceTaskRunner:
    def __init__(
        self,
        statuses: list[str],
        *,
        ok_values: Optional[list[bool]] = None,
        actions: Optional[list[str]] = None,
        errors: Optional[list[str]] = None,
    ) -> None:
        self.statuses = list(statuses)
        self.ok_values = list(ok_values) if isinstance(ok_values, list) else []
        self.actions = list(actions) if isinstance(actions, list) else []
        self.errors = list(errors) if isinstance(errors, list) else []
        self.calls = 0

    def _value_at(self, values: list[Any], index: int, default: Any) -> Any:
        if not values:
            return default
        return values[min(index, len(values) - 1)]

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        index = min(self.calls, len(self.statuses) - 1)
        status = self.statuses[index]
        ok = bool(self._value_at(self.ok_values, index, status not in {"failed", "blocked"}))
        error = str(self._value_at(self.errors, index, "") or "")

        default_action = "already_finished" if status == "finished" else "step_completed"
        if status == "failed":
            default_action = "step_failed"
        if status == "blocked":
            default_action = "guard_blocked"

        action = str(self._value_at(self.actions, index, default_action) or default_action)

        self.calls += 1

        is_finished = status == "finished"
        current_step_index = self.calls if not is_finished else len(self.statuses)
        steps_total = len(self.statuses)

        final_answer = "sequence task finished" if is_finished else ""

        runtime_state = {
            "status": status,
            "current_step_index": current_step_index,
            "steps_total": steps_total,
            "results": [
                {
                    "step_index": current_step_index,
                    "result": {
                        "ok": ok,
                        "final_answer": final_answer,
                        "error": error or None,
                    },
                }
            ],
            "step_results": [],
            "execution_log": [],
            "execution_trace": [],
            "last_step_result": {
                "ok": ok,
                "final_answer": final_answer,
                "error": error or None,
            },
            "last_error": error or None,
            "final_answer": final_answer,
        }

        return {
            "ok": ok,
            "action": action,
            "status": status,
            "final_answer": final_answer,
            "error": error or None,
            "runtime_state": runtime_state,
            "last_result": {
                "ok": ok,
                "final_answer": final_answer,
                "error": error or None,
            },
            "execution_trace": [],
        }


def fail(message: str) -> int:
    print(f"[agent-loop-until-terminal-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[agent-loop-until-terminal-smoke] PASS: {message}")


def make_task(
    name: str,
    steps_total: int,
    *,
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
        "id": name,
        "task_id": name,
        "task_name": name,
        "title": name,
        "goal": "Verify run_task_until_terminal loop wrapper.",
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


def make_plan(steps_total: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "steps": [
            {
                "type": "noop",
                "title": f"fake step {index + 1}",
            }
            for index in range(max(1, steps_total))
        ],
    }


def print_result(result: Dict[str, Any]) -> None:
    print("[agent-loop-until-terminal-smoke] result")
    for key in (
        "ok",
        "mode",
        "action",
        "stop_reason",
        "status",
        "cycle_count",
        "loop_decision",
        "next_action",
        "error",
    ):
        print(f"{key}: {result.get(key)}")


def assert_common_until_terminal_result(
    result: Dict[str, Any],
    *,
    case_name: str,
    expected_ok: bool,
    expected_action: str,
    expected_stop_reason: str,
    expected_status: str,
    expected_cycle_count: int,
    expected_loop_decision: str,
    expected_next_action: str,
) -> int:
    if bool(result.get("ok")) is not expected_ok:
        return fail(f"{case_name} expected ok={expected_ok}, got {result.get('ok')}")

    if result.get("mode") != "task_until_terminal":
        return fail(f"{case_name} expected mode task_until_terminal, got {result.get('mode')}")

    if result.get("action") != expected_action:
        return fail(f"{case_name} expected action {expected_action}, got {result.get('action')}")

    if result.get("stop_reason") != expected_stop_reason:
        return fail(f"{case_name} expected stop_reason {expected_stop_reason}, got {result.get('stop_reason')}")

    if result.get("status") != expected_status:
        return fail(f"{case_name} expected status {expected_status}, got {result.get('status')}")

    if result.get("cycle_count") != expected_cycle_count:
        return fail(f"{case_name} expected cycle_count {expected_cycle_count}, got {result.get('cycle_count')}")

    if result.get("loop_decision") != expected_loop_decision:
        return fail(f"{case_name} expected loop_decision {expected_loop_decision}, got {result.get('loop_decision')}")

    if result.get("next_action") != expected_next_action:
        return fail(f"{case_name} expected next_action {expected_next_action}, got {result.get('next_action')}")

    cycles = result.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != expected_cycle_count:
        return fail(f"{case_name} expected {expected_cycle_count} cycles, got {cycles}")

    task = result.get("task")
    if not isinstance(task, dict):
        return fail(f"{case_name} result.task missing")

    if task.get("last_decision") != expected_loop_decision:
        return fail(f"{case_name} task.last_decision expected {expected_loop_decision}, got {task.get('last_decision')}")

    if task.get("next_action") != expected_next_action:
        return fail(f"{case_name} task.next_action expected {expected_next_action}, got {task.get('next_action')}")

    history = task.get("loop_history")
    if not isinstance(history, list) or len(history) < expected_cycle_count:
        return fail(f"{case_name} expected loop_history >= {expected_cycle_count}, got {history}")

    return 0


def test_continue_until_finish() -> int:
    print("[agent-loop-until-terminal-smoke] CASE: continue_until_finish")

    runner = SequenceTaskRunner(["running", "running", "finished"])
    agent = AgentLoop(task_runner=runner, debug=False)

    result = agent.run_task_until_terminal(
        task=make_task("agent_loop_until_terminal_finish", 3),
        current_tick=0,
        user_input="fake until terminal finish",
        original_plan=make_plan(3),
        max_cycles=5,
    )

    print_result(result)

    check = assert_common_until_terminal_result(
        result,
        case_name="continue_until_finish",
        expected_ok=True,
        expected_action="loop_stopped",
        expected_stop_reason="finish",
        expected_status="finished",
        expected_cycle_count=3,
        expected_loop_decision="finish",
        expected_next_action="finish",
    )
    if check != 0:
        return check

    cycles = result.get("cycles")
    expected_next_actions = ["run_next_tick", "run_next_tick", "finish"]
    actual_next_actions = [str(item.get("next_action") or "") for item in cycles if isinstance(item, dict)]
    if actual_next_actions != expected_next_actions:
        return fail(f"continue_until_finish next_action sequence mismatch: {actual_next_actions}")

    pass_step("continue_until_finish verified")
    return 0


def test_max_cycles_reached() -> int:
    print("[agent-loop-until-terminal-smoke] CASE: max_cycles_reached")

    runner = SequenceTaskRunner(["running", "running", "running", "running"])
    agent = AgentLoop(task_runner=runner, debug=False)

    result = agent.run_task_until_terminal(
        task=make_task("agent_loop_until_terminal_max_cycles", 4),
        current_tick=0,
        user_input="fake until terminal max cycles",
        original_plan=make_plan(4),
        max_cycles=2,
    )

    print_result(result)

    check = assert_common_until_terminal_result(
        result,
        case_name="max_cycles_reached",
        expected_ok=False,
        expected_action="max_cycles_reached",
        expected_stop_reason="max_cycles_reached",
        expected_status="blocked",
        expected_cycle_count=2,
        expected_loop_decision="continue",
        expected_next_action="finish",
    )
    if check != 0:
        return check

    task = result.get("task")
    if task.get("terminal_reason") != "max_cycles_reached":
        return fail(f"max_cycles_reached expected terminal_reason max_cycles_reached, got {task.get('terminal_reason')}")

    pass_step("max_cycles_reached verified")
    return 0


def test_replan_stop() -> int:
    print("[agent-loop-until-terminal-smoke] CASE: replan_stop")

    runner = SequenceTaskRunner(
        ["failed"],
        ok_values=[False],
        actions=["step_failed"],
        errors=["fake recoverable failure"],
    )
    agent = AgentLoop(task_runner=runner, debug=False)

    result = agent.run_task_until_terminal(
        task=make_task("agent_loop_until_terminal_replan", 2, max_replans=1, replan_count=0),
        current_tick=0,
        user_input="fake until terminal replan stop",
        original_plan=make_plan(2),
        max_cycles=5,
    )

    print_result(result)

    check = assert_common_until_terminal_result(
        result,
        case_name="replan_stop",
        expected_ok=False,
        expected_action="loop_stopped",
        expected_stop_reason="replan",
        expected_status="failed",
        expected_cycle_count=1,
        expected_loop_decision="replan",
        expected_next_action="replan",
    )
    if check != 0:
        return check

    pass_step("replan_stop verified")
    return 0


def test_fail_stop() -> int:
    print("[agent-loop-until-terminal-smoke] CASE: fail_stop")

    runner = SequenceTaskRunner(
        ["failed"],
        ok_values=[False],
        actions=["step_failed"],
        errors=["fake unrecoverable failure"],
    )
    agent = AgentLoop(task_runner=runner, debug=False)

    result = agent.run_task_until_terminal(
        task=make_task("agent_loop_until_terminal_fail", 2, max_replans=1, replan_count=1),
        current_tick=0,
        user_input="fake until terminal fail stop",
        original_plan=make_plan(2),
        max_cycles=5,
    )

    print_result(result)

    check = assert_common_until_terminal_result(
        result,
        case_name="fail_stop",
        expected_ok=False,
        expected_action="loop_stopped",
        expected_stop_reason="finish",
        expected_status="failed",
        expected_cycle_count=1,
        expected_loop_decision="fail",
        expected_next_action="finish",
    )
    if check != 0:
        return check

    pass_step("fail_stop verified")
    return 0


def test_blocked_stop() -> int:
    print("[agent-loop-until-terminal-smoke] CASE: blocked_stop")

    runner = SequenceTaskRunner(
        ["blocked"],
        ok_values=[False],
        actions=["guard_blocked"],
        errors=["fake guard blocked"],
    )
    agent = AgentLoop(task_runner=runner, debug=False)

    result = agent.run_task_until_terminal(
        task=make_task("agent_loop_until_terminal_blocked", 1),
        current_tick=0,
        user_input="fake until terminal blocked stop",
        original_plan=make_plan(1),
        max_cycles=5,
    )

    print_result(result)

    check = assert_common_until_terminal_result(
        result,
        case_name="blocked_stop",
        expected_ok=False,
        expected_action="loop_stopped",
        expected_stop_reason="finish",
        expected_status="blocked",
        expected_cycle_count=1,
        expected_loop_decision="blocked",
        expected_next_action="finish",
    )
    if check != 0:
        return check

    pass_step("blocked_stop verified")
    return 0


def main() -> int:
    print("[agent-loop-until-terminal-smoke] START")

    tests = (
        test_continue_until_finish,
        test_max_cycles_reached,
        test_replan_stop,
        test_fail_stop,
        test_blocked_stop,
    )

    for test in tests:
        result = test()
        if result != 0:
            return result

    print("[agent-loop-until-terminal-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())