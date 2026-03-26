from core.agent_loop import AgentLoop
from core.task_manager import TaskManager


class DummyPlanner:
    def plan(self, goal: str):
        return [
            {
                "title": "建立 demo 資料夾",
                "description": goal,
                "tool": "workspace",
                "input": {
                    "action": "mkdir",
                    "path": "demo_task_loop"
                }
            }
        ]


class DummyStepExecutor:
    def execute(self, tool, input_data):
        return {
            "ok": True,
            "tool": tool,
            "input": input_data
        }


def main():
    task_manager = TaskManager("workspace")
    agent = AgentLoop(
        task_manager=task_manager,
        planner=DummyPlanner(),
        step_executor=DummyStepExecutor(),
    )

    task = task_manager.create_task(
        task_id="task_loop_test",
        title="建立測試資料夾",
        goal="建立一個 demo 資料夾"
    )

    agent.run_task(task.task_id)

    loaded = task_manager.load_task(task.task_id)
    print("Task finished.")
    print(loaded.to_dict())


if __name__ == "__main__":
    main()