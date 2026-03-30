from __future__ import annotations

import time
from typing import Any, Dict, Optional, Union

from .agent_loop import AgentLoop
from .task_manager import Task, TaskManager


class TaskScheduler:
    """
    最小可用 Task Scheduler

    功能：
    1. 從 TaskManager 找出下一個 pending task
    2. 呼叫 AgentLoop 執行
    3. 支援 run_once / run_until_empty / loop_forever

    向下相容：
    - find_next_task() 可回傳 Task 或 task_id
    - run_once() 會自動判斷型別
    """

    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        agent_loop: Optional[AgentLoop] = None,
        poll_interval: float = 1.0,
        **kwargs: Any,
    ) -> None:
        self.task_manager = task_manager or TaskManager()
        self.agent_loop = agent_loop or AgentLoop(task_manager=self.task_manager)
        self.poll_interval = poll_interval
        self.extra_config = kwargs

    def find_next_task(self) -> Optional[Task]:
        """
        回傳下一個 pending task 物件。
        """
        pending_tasks = self.task_manager.get_pending_tasks()
        if not pending_tasks:
            return None

        # 先用建立順序 / 載入順序
        return pending_tasks[0]

    def _normalize_task(
        self,
        task_or_id: Optional[Union[str, Task]],
    ) -> Optional[Task]:
        if task_or_id is None:
            return None

        if isinstance(task_or_id, Task):
            return task_or_id

        if isinstance(task_or_id, str):
            return self.task_manager.load_task(task_or_id)

        return None

    def run_once(self) -> bool:
        """
        執行一個 task。
        回傳：
        - True  = 有跑到 task
        - False = 沒有 pending task
        """
        next_item = self.find_next_task()
        task = self._normalize_task(next_item)

        if task is None:
            print("[Scheduler] No pending tasks")
            return False

        print(f"[Scheduler] Running task: {task.task_id}")
        result = self.agent_loop.run_task(task)

        status = result.get("status")
        if status == "completed":
            print(f"[Scheduler] Task completed: {task.task_id}")
        elif status == "failed":
            print(f"[Scheduler] Task failed: {task.task_id} | {result.get('error')}")
        else:
            print(f"[Scheduler] Task finished with status: {status}")

        return True

    def run_until_empty(self) -> None:
        print("[Scheduler] Started (until empty)")

        while True:
            did_run = self.run_once()
            if not did_run:
                print("[Scheduler] Stopped (queue empty)")
                break

    def loop_forever(self) -> None:
        print("[Scheduler] Started (loop mode)")

        try:
            while True:
                did_run = self.run_once()
                if not did_run:
                    time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("[Scheduler] Stopped by user")