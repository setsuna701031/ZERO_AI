from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.agent.agent_loop import AgentLoop
from core.tasks.scheduler import Scheduler


class MinimalPlanner:
    """
    最小可跑 planner
    只做一件事：
    - 把 user_input 裡的 inline step 交給 Scheduler 內建 parser 去處理
    - 這樣 agent_loop task mode 就能跑通
    """

    def plan(
        self,
        context: Dict[str, Any] | None = None,
        user_input: str = "",
        route: Any = None,
    ) -> Dict[str, Any]:
        text = str(user_input or "").strip()
        steps = self._parse_inline_steps(text)

        return {
            "planner_mode": "minimal_test_planner",
            "intent": "manual_inline",
            "summary": "Minimal planner generated inline task steps.",
            "final_answer": "",
            "steps": steps,
        }

    def _parse_inline_steps(self, text: str) -> list[dict]:
        segments = [seg.strip() for seg in text.split("::") if seg.strip()]
        if len(segments) <= 1:
            return []

        steps: list[dict] = []

        for seg in segments[1:]:
            lower = seg.lower()
            if not lower.startswith("step="):
                continue

            raw = seg.split("=", 1)[1].strip()
            parsed = self._parse_one_step(raw)
            if isinstance(parsed, dict):
                steps.append(parsed)

        return steps

    def _parse_one_step(self, value: str) -> dict | None:
        raw = str(value or "").strip()
        lower = raw.lower()

        if lower.startswith("write_file:"):
            payload = raw.split(":", 1)[1]
            if "|" in payload:
                path, content = payload.split("|", 1)
            else:
                path, content = payload, ""
            path = path.strip()
            if not path:
                return None
            return {
                "type": "write_file",
                "path": path,
                "content": content,
            }

        if lower.startswith("run_python:"):
            path = raw.split(":", 1)[1].strip()
            if not path:
                return None
            return {
                "type": "run_python",
                "path": path,
            }

        if lower.startswith("verify:"):
            payload = raw.split(":", 1)[1].strip()

            if payload.startswith("contains="):
                keyword = payload.split("=", 1)[1].strip()
                return {
                    "type": "verify",
                    "contains": keyword,
                }

            if payload.startswith("equals="):
                expected = payload.split("=", 1)[1]
                return {
                    "type": "verify",
                    "equals": expected,
                }

            if payload.startswith("path="):
                path = payload.split("=", 1)[1].strip()
                return {
                    "type": "verify",
                    "path": path,
                }

            return {
                "type": "verify",
                "contains": payload,
            }

        if lower.startswith("read_file:"):
            path = raw.split(":", 1)[1].strip()
            if not path:
                return None
            return {
                "type": "read_file",
                "path": path,
            }

        if lower.startswith("command:"):
            command = raw.split(":", 1)[1].strip()
            if not command:
                return None
            return {
                "type": "command",
                "command": command,
            }

        return None


def print_block(title: str, data: Any) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    if isinstance(data, dict):
        pprint(data, sort_dicts=False)
    else:
        print(data)


def main() -> None:
    print("\n[AgentLoop Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    scheduler = Scheduler(
        workspace_dir="workspace",
        allow_commands=True,
        debug=True,
    )

    loop = AgentLoop(
        planner=MinimalPlanner(),
        scheduler=scheduler,
        debug=True,
    )

    user_input = (
        "建立任務：write hello test "
        ":: step=write_file:shared/test.py|print('ok') "
        ":: step=verify:contains=ok"
    )

    print_block("RUN AGENT LOOP TASK MODE", {"user_input": user_input})

    result = loop.run(user_input)
    print_block("loop.run result", result)

    if not isinstance(result, dict) or not result.get("ok"):
        print("AgentLoop task mode failed.")
        return

    task_id = str(result.get("task_id") or "").strip()
    if not task_id:
        print("No task_id returned.")
        return

    print_block("TICK SCHEDULER", {"task_id": task_id})

    for i in range(10):
        print(f"\nTICK {i}")
        tick_result = scheduler.tick()
        pprint(tick_result, sort_dicts=False)

    task = scheduler._get_task_from_repo(task_id)

    print_block(
        "FINAL TASK STATE",
        {
            "task_id": task_id,
            "task": task,
        },
    )

    if isinstance(task, dict):
        summary = {
            "status": task.get("status"),
            "history": task.get("history"),
            "replanned": task.get("replanned"),
            "replan_count": task.get("replan_count"),
            "current_step_index": task.get("current_step_index"),
            "steps_total": task.get("steps_total"),
            "steps": task.get("steps"),
            "final_answer": task.get("final_answer"),
            "last_error": task.get("last_error"),
        }
        print_block("TASK SUMMARY", summary)


if __name__ == "__main__":
    main()