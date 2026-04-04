import time

from core.tasks.scheduler import Scheduler
from core.tasks.task_repository import TaskRepository
from core.tools.tool_registry import ToolRegistry

repo = TaskRepository("workspace/tasks.json")
tool_registry = ToolRegistry(workspace_dir="workspace")

scheduler = Scheduler(
    task_repo=repo,
    workspace_dir="workspace",
    tool_registry=tool_registry,
)

print("Scheduler loop started...")

while True:
    scheduler.rebuild_queue_from_repo()
    result = scheduler.run_one()

    if result.get("task_id") is not None or result.get("ok"):
        print(result)

    time.sleep(1)