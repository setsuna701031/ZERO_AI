from core.tasks.scheduler import Scheduler


def main() -> None:
    s = Scheduler(workspace_dir="workspace", allow_commands=True)

    print("SCHEDULER_BUILD =", s.tick()["scheduler_build"])

    goal = (
        "test replanner::"
        "step=write_file:shared/hello.py|print('hello')\n::"
        "step=run_python:shared/hello.py::"
        "step=verify:contains=world"
    )

    submit_result = s.submit_task(goal)
    print("SUBMIT.status =", submit_result.get("status"))
    task_id = submit_result.get("task_id") or submit_result.get("task_name")
    print("TASK_ID =", task_id)

    for i in range(1, 8):
        tick_result = s.tick()
        executed = tick_result.get("executed_results", [])

        print(f"\n=== TICK {i} ===")
        print("executed_count =", tick_result.get("executed_count"))

        if executed:
            first = executed[0]
            print("executed.task_id =", first.get("task_id"))
            print("executed.status =", first.get("status"))

            result = first.get("result", {}) or {}
            print("result.action =", result.get("action"))
            print("result.error =", result.get("error"))
            print("result.replan_result =", result.get("replan_result"))

        snapshot = s.get_queue_snapshot()
        task_rows = snapshot.get("tasks", [])
        target = None

        for row in task_rows:
            if row.get("task_id") == task_id or row.get("task_name") == task_id:
                target = row
                break

        if target:
            print("task.status =", target.get("status"))
            print("task.replan_count =", target.get("replan_count"))
            print("task.replanned =", target.get("replanned"))
            print("task.current_step_index =", target.get("current_step_index"))
            print("task.steps =", target.get("steps"))
            print("task.last_error =", target.get("last_error"))
        else:
            print("task not found in snapshot")


if __name__ == "__main__":
    main()