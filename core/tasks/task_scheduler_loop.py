import os
import json
import time
from datetime import datetime
from core.runtime.task_runner import TaskRunner


WORKSPACE_TASKS_DIR = r"E:\zero_ai\workspace\tasks"
SCHEDULER_LOG = r"E:\zero_ai\workspace\scheduler.log"
MAX_TASKS_PER_TICK = 20
SLEEP_SECONDS = 2


ACTIVE_STATUSES = {
    "queued",
    "ready",
    "running",
    "retrying",
    "waiting",
    "replanning",
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)

    os.makedirs(os.path.dirname(SCHEDULER_LOG), exist_ok=True)
    with open(SCHEDULER_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def safe_load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_tasks():
    tasks = []

    if not os.path.exists(WORKSPACE_TASKS_DIR):
        return tasks

    for name in os.listdir(WORKSPACE_TASKS_DIR):
        task_dir = os.path.join(WORKSPACE_TASKS_DIR, name)
        if not os.path.isdir(task_dir):
            continue

        plan_file = os.path.join(task_dir, "plan.json")
        if not os.path.exists(plan_file):
            continue

        runtime_file = os.path.join(task_dir, "runtime_state.json")

        plan = safe_load_json(plan_file)
        runtime = safe_load_json(runtime_file)

        task = {
            "task_name": name,
            "task_dir": task_dir,
            "workspace_dir": task_dir,
            "plan_file": plan_file,
            "runtime_state_file": runtime_file,
            "execution_log_file": os.path.join(task_dir, "execution_log.json"),
            "result_file": os.path.join(task_dir, "result.json"),
            "log_file": os.path.join(task_dir, "task.log"),

            # plan
            "goal": plan.get("goal", ""),
            "title": plan.get("title", ""),
            "steps": plan.get("steps", []),
            "depends_on": plan.get("depends_on", []),
            "priority": plan.get("priority", runtime.get("priority", 0)),
            "max_retries": plan.get("max_retries", runtime.get("max_retries", 0)),
            "retry_delay": plan.get("retry_delay", runtime.get("retry_delay", 0)),
            "timeout_ticks": plan.get("timeout_ticks", runtime.get("timeout_ticks", 0)),
            "max_replans": plan.get("max_replans", runtime.get("max_replans", 1)),

            # runtime
            "status": runtime.get("status", "queued"),
            "retry_count": runtime.get("retry_count", 0),
            "replan_count": runtime.get("replan_count", 0),
            "created_tick": runtime.get("created_tick", 0),
            "current_step_index": runtime.get("current_step_index", 0),
            "results": runtime.get("results", []),
            "step_results": runtime.get("step_results", []),
            "last_step_result": runtime.get("last_step_result"),
            "final_answer": runtime.get("final_answer", ""),
            "failure_type": runtime.get("failure_type"),
            "failure_message": runtime.get("failure_message"),
            "last_error": runtime.get("last_error"),
            "blocked_reason": runtime.get("blocked_reason", ""),
            "next_retry_tick": runtime.get("next_retry_tick", 0),
            "cancel_requested": runtime.get("cancel_requested", False),
            "cancel_reason": runtime.get("cancel_reason", ""),
        }

        tasks.append(task)

    return tasks


def filter_active_tasks(tasks):
    active = []
    for task in tasks:
        status = str(task.get("status", "queued") or "queued").strip().lower()
        if status in ACTIVE_STATUSES:
            active.append(task)
    return active


def sort_tasks(tasks):
    return sorted(
        tasks,
        key=lambda t: (
            int(t.get("priority", 0) or 0),
            -int(t.get("created_tick", 0) or 0),
            str(t.get("task_name", "")),
        ),
        reverse=True,
    )


def main():
    runner = TaskRunner(debug=True)
    tick = 0

    log("Scheduler started")

    while True:
        log(f"===== SCHEDULER TICK {tick} =====")

        all_tasks = load_tasks()
        active_tasks = filter_active_tasks(all_tasks)
        active_tasks = sort_tasks(active_tasks)
        active_tasks = active_tasks[:MAX_TASKS_PER_TICK]

        log(
            f"loaded_tasks={len(all_tasks)} "
            f"active_tasks={len(active_tasks)} "
            f"max_tasks_per_tick={MAX_TASKS_PER_TICK}"
        )

        for task in active_tasks:
            task_name = task.get("task_name", "unknown_task")
            status = task.get("status", "queued")
            priority = task.get("priority", 0)

            log(f"Running task: {task_name} | status={status} | priority={priority}")

            try:
                result = runner.run_one_tick(task, current_tick=tick)
                action = result.get("action")
                log(f"Result: {task_name} -> {action}")
            except Exception as e:
                log(f"ERROR: {task_name} -> {e}")

        tick += 1
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()