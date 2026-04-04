from core.tasks.scheduler import Scheduler


class DummyStepExecutor:
    def execute_step(self, step=None, task=None, previous_result=None):
        if step.get("tool_name") == "not_exist_tool":
            return {
                "ok": False,
                "error": "tool not found: not_exist_tool"
            }
        return {
            "ok": True,
            "result": step.get("message", "ok")
        }


class DummyReplanner:
    def replan(self, task=None, failed_step=None, failed_result=None):
        return {
            "steps": [
                {
                    "type": "respond",
                    "message": "這是 replan 後的新 step 1"
                },
                {
                    "type": "respond",
                    "message": "這是 replan 後的新 step 2"
                }
            ],
            "final_answer": "已重新規劃"
        }


scheduler = Scheduler(
    workspace_dir="workspace",
    step_executor=DummyStepExecutor(),
    replanner=DummyReplanner(),
    debug=True,
)

task = {
    "id": "task_replan_test_001",
    "title": "replan 測試",
    "goal": "測試失敗後是否會 replan",
    "status": "queued",
    "workspace": "workspace/tasks/task_replan_test_001",
    "steps": [
        {
            "type": "tool",
            "tool_name": "not_exist_tool",
            "tool_input": {}
        },
        {
            "type": "respond",
            "message": "原本第二步"
        }
    ],
    "current_step_index": 0,
    "execution_log": [],
    "replanned": False,
    "replan_reason": "",
    "replan_count": 0,
    "max_replans": 1
}

scheduler.add_task(task)

print("=== 第一次 run_next() ===")
r1 = scheduler.run_next()
print(r1)

print("\n=== queue 內容 ===")
print(scheduler.queue)

print("\n=== 第二次 run_next() ===")
r2 = scheduler.run_next()
print(r2)

print("\n=== 第三次 run_next() ===")
r3 = scheduler.run_next()
print(r3)