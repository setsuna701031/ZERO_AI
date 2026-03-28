import time
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class StepExecutor:
    """
    負責逐步執行 planner 產生的 steps
    並在每個 step 前檢查 queue 狀態（pause / cancel）
    """

    def __init__(self, queue_controller=None):
        self.queue_controller = queue_controller

    def _wait_if_paused_or_cancelled(self, queue_task_id: str):
        if not self.queue_controller or not queue_task_id:
            return

        while True:
            status = self.queue_controller.get_status(queue_task_id)

            if status == "paused":
                time.sleep(1)
                continue

            if status == "cancelled":
                raise RuntimeError("task cancelled by user")

            return

    def execute_steps(
        self,
        steps: List[Dict[str, Any]],
        run_step_func: Callable[[Dict[str, Any]], Dict[str, Any]],
        state_file: Path,
        queue_task_id: str = "",
    ) -> Dict[str, Any]:

        total_steps = len(steps)

        for index, step in enumerate(steps, start=1):
            # Pause / Cancel 控制
            self._wait_if_paused_or_cancelled(queue_task_id)

            result = run_step_func(step)

            # 更新 state.json
            state = {}
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:
                    state = {}

            state["current_step_index"] = index
            state["last_finished_step"] = index
            state["progress_percent"] = int((index / total_steps) * 100)

            state_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        return {
            "success": True,
            "steps_executed": total_steps,
        }