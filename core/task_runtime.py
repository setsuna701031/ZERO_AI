from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class TaskRuntime:
    """
    ZERO Task Runtime

    負責：
    - 執行任務
    - 建立 plan.json
    - 逐步執行 steps
    - 寫入 step_XX.json
    - 寫入 result.json
    - 寫 log.txt
    - 回寫任務狀態:
        created -> running -> finished / failed
    """

    def __init__(
        self,
        workspace_root: Path | str,
        task_manager: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.task_manager = task_manager

    # =========================================================
    # Run Task
    # =========================================================

    def run_task(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        goal = str(task_info.get("goal", "")).strip()

        if not task_name:
            raise ValueError("task_info['task_name'] is required.")

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._set_task_status(task_name, "running")
            self._append_log(task_dir, f"Task started: {task_name}")
            self._append_log(task_dir, f"Goal: {goal}")
            self._append_log(task_dir, "Status changed to: running")

            # 1) 建立 plan
            plan = self._create_simple_plan(goal)
            self._save_json(task_dir / "plan.json", plan)

            steps = plan.get("steps", [])
            if not isinstance(steps, list):
                raise ValueError("plan['steps'] must be a list.")

            # 2) 逐步執行
            step_results: List[Dict[str, Any]] = []

            for index, step_text in enumerate(steps, start=1):
                step_result = self._execute_step(
                    step_index=index,
                    step_text=str(step_text),
                    goal=goal,
                )

                step_file = task_dir / f"step_{index:02d}.json"
                self._save_json(step_file, step_result)
                step_results.append(step_result)

                self._append_log(
                    task_dir,
                    f"Step {index:02d} finished: {step_result.get('step_text', '')}",
                )

            # 3) 彙總結果
            result = self._build_final_result(
                task_name=task_name,
                goal=goal,
                step_results=step_results,
            )
            self._save_json(task_dir / "result.json", result)

            self._append_log(task_dir, "Task finished.")
            self._set_task_status(task_name, "finished")

            step_files = [
                str(task_dir / f"step_{i:02d}.json")
                for i in range(1, len(step_results) + 1)
            ]

            return {
                "success": True,
                "summary": f"Task finished: {task_name}",
                "data": {
                    "task_name": task_name,
                    "task_dir": str(task_dir),
                    "status": "finished",
                    "plan_file": str(task_dir / "plan.json"),
                    "step_files": step_files,
                    "result_file": str(task_dir / "result.json"),
                    "log_file": str(task_dir / "log.txt"),
                    "step_count": len(step_results),
                },
                "error": None,
            }

        except Exception as exc:
            self._append_log(task_dir, f"Task failed: {exc}")
            self._set_task_status(task_name, "failed")

            failed_result = {
                "status": "failed",
                "message": str(exc),
            }
            self._save_json(task_dir / "result.json", failed_result)

            return {
                "success": False,
                "summary": f"Task failed: {task_name}",
                "data": {
                    "task_name": task_name,
                    "task_dir": str(task_dir),
                    "status": "failed",
                    "result_file": str(task_dir / "result.json"),
                    "log_file": str(task_dir / "log.txt"),
                },
                "error": str(exc),
            }

    # =========================================================
    # Step Execution
    # =========================================================

    def _execute_step(
        self,
        step_index: int,
        step_text: str,
        goal: str,
    ) -> Dict[str, Any]:
        normalized_step = step_text.strip().lower()

        if normalized_step == "analyze goal":
            output = {
                "goal": goal,
                "analysis": f"Goal received: {goal}",
            }
        elif normalized_step == "execute task":
            output = {
                "execution": "Task executed (demo step loop)",
            }
        elif normalized_step == "save result":
            output = {
                "save": "Result prepared for persistence",
            }
        else:
            output = {
                "info": f"Unhandled step executed as generic step: {step_text}",
            }

        return {
            "step": step_index,
            "step_text": step_text,
            "status": "finished",
            "output": output,
        }

    def _build_final_result(
        self,
        task_name: str,
        goal: str,
        step_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "task_name": task_name,
            "goal": goal,
            "status": "finished",
            "message": "Task finished (step loop runtime)",
            "step_count": len(step_results),
            "steps": step_results,
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _set_task_status(self, task_name: str, status: str) -> None:
        if self.task_manager is None:
            return

        update_method = getattr(self.task_manager, "update_task_status", None)
        if callable(update_method):
            update_method(task_name, status)

    def _create_simple_plan(self, goal: str) -> Dict[str, Any]:
        return {
            "goal": goal,
            "steps": [
                "analyze goal",
                "execute task",
                "save result",
            ],
        }

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _append_log(self, task_dir: Path, text: str) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        log_file = task_dir / "log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")