from __future__ import annotations

import time

from core.tasks.scheduler import Scheduler
from core.tasks.scheduler_thread import SchedulerThread
from core.tasks.task_repository import TaskRepository
from core.tools.tool_registry import ToolRegistry
from core.planning.planner import Planner


def build_task_from_plan(title, plan):
    steps = []
    if isinstance(plan, dict):
        steps = plan.get("steps", [])

    return steps


def main():
    print("ZERO System starting...")

    repo = TaskRepository("workspace/tasks.json")
    tool_registry = ToolRegistry(workspace_dir="workspace")

    planner = Planner()

    scheduler = Scheduler(
        task_repo=repo,
        workspace_dir="workspace",
        tool_registry=tool_registry,
    )

    scheduler_thread = SchedulerThread(scheduler, interval=1)
    scheduler_thread.start()

    print("ZERO System ready.")
    print("Scheduler running in background...")

    while True:
        try:
            cmd = input("ZERO> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            scheduler_thread.stop()
            break

        if not cmd:
            continue

        if cmd == "exit":
            scheduler_thread.stop()
            break

        elif cmd == "tasks":
            tasks = repo.list_tasks()
            print(tasks)

        elif cmd.startswith("add "):
            title = cmd[4:].strip()

            print("Planning task...")

            plan = planner.plan(user_input=title)

            steps = build_task_from_plan(title, plan)

            task_id = f"task_{int(time.time())}"

            task = {
                "id": task_id,
                "task_name": task_id,
                "title": title,
                "goal": title,
                "status": "queued",
                "steps": steps,
                "current_step_index": 0,
                "execution_log": [],
                "planner_result": plan,
                "final_answer": "",
                "workspace_dir": "workspace/tasks",
            }

            repo.add_task(task)

            print("Task added:", title)
            print("Steps:", steps)

        else:
            print("commands: add <task>, tasks, exit")


if __name__ == "__main__":
    main()