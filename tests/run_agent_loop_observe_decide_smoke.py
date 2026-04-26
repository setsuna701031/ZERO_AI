from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop


class FakeTaskRunner:
    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_state = {
            "status": "finished",
            "current_step_index": 1,
            "steps_total": 1,
            "results": [
                {
                    "step_index": 1,
                    "result": {
                        "ok": True,
                        "final_answer": "fake task finished",
                    },
                }
            ],
            "step_results": [],
            "execution_log": [],
            "execution_trace": [],
            "last_step_result": {
                "ok": True,
                "final_answer": "fake task finished",
            },
            "last_error": None,
            "final_answer": "fake task finished",
        }

        return {
            "ok": True,
            "action": "already_finished",
            "status": "finished",
            "final_answer": "fake task finished",
            "runtime_state": runtime_state,
            "last_result": {
                "ok": True,
                "final_answer": "fake task finished",
            },
            "execution_trace": [],
        }


def fail(message: str) -> int:
    print(f"[agent-loop-observe-decide-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[agent-loop-observe-decide-smoke] PASS: {message}")


def main() -> int:
    print("[agent-loop-observe-decide-smoke] START")

    task = {
        "id": "agent_loop_observe_decide_smoke",
        "task_id": "agent_loop_observe_decide_smoke",
        "task_name": "agent_loop_observe_decide_smoke",
        "title": "AgentLoop observe decide smoke",
        "goal": "Verify AgentLoop records observe/decide metadata.",
        "status": "queued",
        "steps": [
            {
                "type": "noop",
                "title": "fake step",
            }
        ],
        "steps_total": 1,
        "current_step_index": 0,
        "results": [],
        "step_results": [],
        "execution_log": [],
        "execution_trace": [],
        "last_step_result": None,
        "last_error": None,
        "final_answer": "",
        "max_replans": 1,
        "replan_count": 0,
    }

    agent = AgentLoop(
        task_runner=FakeTaskRunner(),
        debug=False,
    )

    result = agent.run_task_loop(
        task=task,
        current_tick=1,
        user_input="fake observe decide test",
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

    if not result.get("ok"):
        return fail(f"AgentLoop returned non-ok: {result.get('error')}")

    if result.get("mode") != "task_loop":
        return fail(f"expected mode task_loop, got: {result.get('mode')}")

    if result.get("loop_decision") != "finish":
        return fail(f"expected loop_decision finish, got: {result.get('loop_decision')}")

    if result.get("next_action") != "finish":
        return fail(f"expected next_action finish, got: {result.get('next_action')}")

    returned_task = result.get("task")
    if not isinstance(returned_task, dict):
        return fail("result.task missing or invalid")

    if returned_task.get("last_decision") != "finish":
        return fail(f"task.last_decision mismatch: {returned_task.get('last_decision')}")
    pass_step("task.last_decision recorded")

    if returned_task.get("next_action") != "finish":
        return fail(f"task.next_action mismatch: {returned_task.get('next_action')}")
    pass_step("task.next_action recorded")

    last_observation = returned_task.get("last_observation")
    if not isinstance(last_observation, dict) or not last_observation:
        return fail("task.last_observation missing")
    pass_step("task.last_observation recorded")

    observation_status = str(last_observation.get("status") or "").strip().lower()
    if observation_status != "finished":
        return fail(f"last_observation.status expected finished, got: {observation_status}")
    pass_step("last_observation.status verified")

    loop_cycle_count = returned_task.get("loop_cycle_count")
    if not isinstance(loop_cycle_count, int) or loop_cycle_count < 1:
        return fail(f"task.loop_cycle_count expected >= 1, got: {loop_cycle_count}")
    pass_step("task.loop_cycle_count incremented")

    loop_history = returned_task.get("loop_history")
    if not isinstance(loop_history, list) or len(loop_history) < 1:
        return fail(f"task.loop_history expected at least 1 item, got: {loop_history}")
    pass_step("task.loop_history recorded")

    history_item = loop_history[-1]
    if not isinstance(history_item, dict):
        return fail("last loop_history item invalid")

    if history_item.get("decision") != "finish":
        return fail(f"loop_history decision mismatch: {history_item.get('decision')}")

    if history_item.get("next_action") != "finish":
        return fail(f"loop_history next_action mismatch: {history_item.get('next_action')}")

    if history_item.get("terminal") is not True:
        return fail(f"loop_history terminal expected True, got: {history_item.get('terminal')}")

    history_observation = history_item.get("observation")
    if not isinstance(history_observation, dict):
        return fail("loop_history observation missing")

    history_status = str(history_observation.get("status") or "").strip().lower()
    if history_status != "finished":
        return fail(f"loop_history observation.status expected finished, got: {history_status}")

    pass_step("loop_history content verified")

    print("[agent-loop-observe-decide-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())