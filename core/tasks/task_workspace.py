from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

from core.tasks.task_paths import TaskPathManager


class TaskWorkspace:
    def __init__(self, base_dir: str = "workspace/tasks"):
        base_dir_abs = os.path.abspath(base_dir)
        workspace_root = os.path.dirname(base_dir_abs)

        self.path_manager = TaskPathManager(workspace_root=workspace_root)
        self.path_manager.ensure_workspace()

        self.workspace_root = self.path_manager.workspace_root
        self.base_dir = self.path_manager.tasks_root
        self.shared_dir = os.path.join(self.workspace_root, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)

    def create_workspace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be dict")

        enriched_task = self.path_manager.enrich_task(task)
        task_id = str(enriched_task.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("Task missing id/task_id/task_name")

        paths = self.path_manager.ensure_task_paths(task_id)

        task_dir = paths["task_dir"]
        plan_file = paths["plan_file"]
        runtime_state_file = paths["runtime_state_file"]
        execution_log_file = paths["execution_log_file"]
        result_file = paths["result_file"]
        task_file = paths["task_file"]
        log_file = paths["log_file"]

        os.makedirs(self.shared_dir, exist_ok=True)

        enriched_task["workspace_root"] = self.workspace_root
        enriched_task["workspace_dir"] = self.base_dir
        enriched_task["shared_dir"] = self.shared_dir
        enriched_task["task_dir"] = task_dir
        enriched_task["plan_file"] = plan_file
        enriched_task["runtime_state_file"] = runtime_state_file
        enriched_task["execution_log_file"] = execution_log_file
        enriched_task["result_file"] = result_file
        enriched_task["log_file"] = log_file

        # 先寫 task.json，確保資料夾不是空的
        self._save(task_file, enriched_task)

        # 建立基礎檔案，讓後續每層都能直接覆蓋/追加
        if not os.path.exists(plan_file):
            self._save(plan_file, self._initial_plan_payload(enriched_task))

        if not os.path.exists(runtime_state_file):
            self._save(runtime_state_file, self._initial_runtime_state(enriched_task))

        if not os.path.exists(execution_log_file):
            self._save(execution_log_file, [])

        if not os.path.exists(result_file):
            self._save(result_file, self._initial_result_payload(enriched_task))

        if not os.path.exists(log_file):
            self._write_text(log_file, "")

        return enriched_task

    def save_plan(self, task: Dict[str, Any], plan: Dict[str, Any]) -> None:
        task = self.path_manager.enrich_task(task)
        plan_file = self._require_path(task, "plan_file")
        payload = copy.deepcopy(plan if isinstance(plan, dict) else {"raw_plan": plan})
        self._save(plan_file, payload)

    def append_execution_log(self, task: Dict[str, Any], log_entry: Dict[str, Any]) -> None:
        task = self.path_manager.enrich_task(task)
        execution_log_file = self._require_path(task, "execution_log_file")
        logs: List[Dict[str, Any]] = []

        if os.path.exists(execution_log_file):
            try:
                with open(execution_log_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        logs = loaded
            except Exception:
                logs = []

        logs.append(
            copy.deepcopy(
                log_entry if isinstance(log_entry, dict) else {"message": str(log_entry)}
            )
        )
        self._save(execution_log_file, logs)

    def save_result(self, task: Dict[str, Any], result: Dict[str, Any]) -> None:
        task = self.path_manager.enrich_task(task)
        result_file = self._require_path(task, "result_file")
        payload = copy.deepcopy(result if isinstance(result, dict) else {"raw_result": result})
        self._save(result_file, payload)

    def save_task_snapshot(self, task: Dict[str, Any]) -> None:
        task = self.path_manager.enrich_task(task)
        task_id = str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()
        if not task_id:
            raise ValueError("Task missing id/task_id/task_name")

        task_file = self.path_manager.task_snapshot_file(task_id)
        self._save(task_file, task)

    def append_text_log(self, task: Dict[str, Any], line: str) -> None:
        task = self.path_manager.enrich_task(task)
        log_file = self._require_path(task, "log_file")
        existing = ""

        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            except Exception:
                existing = ""

        if existing and not existing.endswith("\n"):
            existing += "\n"
        existing += str(line) + "\n"
        self._write_text(log_file, existing)

    def save_json(self, dir_path: str, filename: str, data: Any) -> None:
        os.makedirs(dir_path, exist_ok=True)
        path = os.path.join(dir_path, filename)
        self._save(path, data)

    def _require_path(self, task: Dict[str, Any], key: str) -> str:
        value = str(task.get(key, "")).strip()
        if not value:
            raise ValueError(f"Task missing required path field: {key}")
        return value

    def _initial_plan_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        planner_result = task.get("planner_result", {})
        if isinstance(planner_result, dict) and planner_result:
            return copy.deepcopy(planner_result)

        steps = task.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        return {
            "planner_mode": "",
            "intent": "",
            "final_answer": "",
            "steps": copy.deepcopy(steps),
        }

    def _initial_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        steps = task.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        history = task.get("history", ["queued"])
        if isinstance(history, str):
            history = [history]
        elif not isinstance(history, list):
            history = ["queued"]

        return {
            "task_name": str(task.get("task_name") or task.get("task_id") or task.get("id") or ""),
            "status": str(task.get("status", "queued")),
            "priority": int(task.get("priority", 0)),
            "retry_count": int(task.get("retry_count", 0)),
            "max_retries": int(task.get("max_retries", 0)),
            "retry_delay": int(task.get("retry_delay", 0)),
            "next_retry_tick": int(task.get("next_retry_tick", 0)),
            "timeout_ticks": int(task.get("timeout_ticks", 0)),
            "wait_until_tick": int(task.get("wait_until_tick", 0)),
            "created_tick": int(task.get("created_tick", 0)),
            "last_run_tick": task.get("last_run_tick"),
            "last_failure_tick": task.get("last_failure_tick"),
            "finished_tick": task.get("finished_tick"),
            "last_error": task.get("last_error"),
            "history": copy.deepcopy(history),
            "runtime_state_file": str(task.get("runtime_state_file", "")),
            "plan_file": str(task.get("plan_file", "")),
            "log_file": str(task.get("log_file", "")),
            "result_file": str(task.get("result_file", "")),
            "execution_log_file": str(task.get("execution_log_file", "")),
            "workspace_root": str(task.get("workspace_root", self.workspace_root)),
            "workspace_dir": str(task.get("workspace_dir", self.base_dir)),
            "shared_dir": str(task.get("shared_dir", self.shared_dir)),
            "task_dir": str(task.get("task_dir", "")),
            "current_step_index": int(task.get("current_step_index", 0)),
            "steps_total": int(task.get("steps_total", len(steps))),
            "steps": copy.deepcopy(steps),
            "results": copy.deepcopy(task.get("results", [])) if isinstance(task.get("results", []), list) else [],
            "step_results": copy.deepcopy(task.get("step_results", [])) if isinstance(task.get("step_results", []), list) else [],
            "last_step_result": copy.deepcopy(task.get("last_step_result")),
            "final_answer": str(task.get("final_answer", "")),
            "replan_count": int(task.get("replan_count", 0)),
            "replanned": bool(task.get("replanned", False)),
            "replan_reason": str(task.get("replan_reason", "")),
            "max_replans": int(task.get("max_replans", 1)),
            "execution_log": copy.deepcopy(task.get("execution_log", [])) if isinstance(task.get("execution_log", []), list) else [],
            "goal": str(task.get("goal", "")),
            "title": str(task.get("title", "")),
            "planner_result": copy.deepcopy(task.get("planner_result", {})) if isinstance(task.get("planner_result", {}), dict) else {},
        }

    def _initial_result_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": None,
            "task_name": str(task.get("task_name") or task.get("task_id") or task.get("id") or ""),
            "status": str(task.get("status", "queued")),
            "final_answer": str(task.get("final_answer", "")),
            "result": None,
            "error": None,
        }

    def _write_text(self, path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _save(self, path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)