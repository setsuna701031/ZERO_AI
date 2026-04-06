from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional


class TaskWorkspace:
    """
    Task workspace manager

    職責：
    1. 建立 task workspace 資料夾
    2. 寫入 plan.json
    3. 寫入 runtime_state.json
    4. 寫入 execution_log.json
    5. 寫入 result.json
    6. 確保 scheduler / repo / runtime 的落盤格式一致
    """

    def __init__(self, tasks_root: str = "workspace/tasks") -> None:
        self.tasks_root = os.path.abspath(tasks_root)
        self.workspace_root = os.path.abspath(os.path.dirname(self.tasks_root))
        self.shared_dir = os.path.join(self.workspace_root, "shared")

        os.makedirs(self.tasks_root, exist_ok=True)
        os.makedirs(self.shared_dir, exist_ok=True)

    # ============================================================
    # public api
    # ============================================================

    def create_workspace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be dict")

        task_id = self._task_id(task)
        if not task_id:
            raise ValueError("task_id missing")

        task_dir = os.path.join(self.tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)

        enriched = copy.deepcopy(task)
        enriched["task_id"] = task_id
        enriched["task_name"] = str(enriched.get("task_name") or task_id)
        enriched["workspace_root"] = self.workspace_root
        enriched["workspace_dir"] = self.tasks_root
        enriched["shared_dir"] = self.shared_dir
        enriched["task_dir"] = task_dir
        enriched["plan_file"] = os.path.join(task_dir, "plan.json")
        enriched["runtime_state_file"] = os.path.join(task_dir, "runtime_state.json")
        enriched["execution_log_file"] = os.path.join(task_dir, "execution_log.json")
        enriched["result_file"] = os.path.join(task_dir, "result.json")
        enriched["log_file"] = os.path.join(task_dir, "task.log")

        if "created_at" not in enriched or enriched.get("created_at") is None:
            enriched["created_at"] = int(time.time())

        if "history" not in enriched or not isinstance(enriched.get("history"), list):
            enriched["history"] = ["queued"]

        return enriched

    def save_plan(self, task: Dict[str, Any], planner_result: Dict[str, Any]) -> None:
        task = self.create_workspace(task)

        plan_path = str(task.get("plan_file") or "").strip()
        if not plan_path:
            raise ValueError("plan_file missing")

        payload = planner_result if isinstance(planner_result, dict) else {}
        self._write_json(plan_path, payload)

    def save_task_snapshot(self, task: Dict[str, Any]) -> None:
        task = self.create_workspace(task)

        runtime_state = self._build_runtime_state(task)
        execution_log = self._build_execution_log(task)
        result_payload = self._build_result_payload(task)

        runtime_state_path = str(task.get("runtime_state_file") or "").strip()
        execution_log_path = str(task.get("execution_log_file") or "").strip()
        result_path = str(task.get("result_file") or "").strip()

        if not runtime_state_path:
            raise ValueError("runtime_state_file missing")
        if not execution_log_path:
            raise ValueError("execution_log_file missing")
        if not result_path:
            raise ValueError("result_file missing")

        self._write_json(runtime_state_path, runtime_state)
        self._write_json(execution_log_path, execution_log)
        self._write_json(result_path, result_payload)

        self._touch_log_file(task)

    def load_plan(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = self.create_workspace(task)
        path = str(task.get("plan_file") or "").strip()
        if not path or not os.path.exists(path):
            return {}
        return self._read_json(path, default={})

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = self.create_workspace(task)
        path = str(task.get("runtime_state_file") or "").strip()
        if not path or not os.path.exists(path):
            return {}
        data = self._read_json(path, default={})
        return data if isinstance(data, dict) else {}

    def load_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = self.create_workspace(task)
        path = str(task.get("result_file") or "").strip()
        if not path or not os.path.exists(path):
            return {}
        data = self._read_json(path, default={})
        return data if isinstance(data, dict) else {}

    def load_execution_log(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        task = self.create_workspace(task)
        path = str(task.get("execution_log_file") or "").strip()
        if not path or not os.path.exists(path):
            return []
        data = self._read_json(path, default=[])
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    # ============================================================
    # builders
    # ============================================================

    def _build_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        steps = self._ensure_list(task.get("steps"))
        results = self._ensure_list(task.get("results"))
        execution_log = self._ensure_list(task.get("execution_log"))
        history = self._ensure_list(task.get("history"), default=["queued"])
        depends_on = self._ensure_list(task.get("depends_on"))

        planner_result = task.get("planner_result", {})
        if not isinstance(planner_result, dict):
            planner_result = {}

        current_step_index = self._to_int(task.get("current_step_index"), default=0)
        steps_total = self._to_int(task.get("steps_total"), default=len(steps))
        priority = self._to_int(task.get("priority"), default=0)
        retry_count = self._to_int(task.get("retry_count"), default=0)
        max_retries = self._to_int(task.get("max_retries"), default=0)
        retry_delay = self._to_int(task.get("retry_delay"), default=0)
        next_retry_tick = self._to_int(task.get("next_retry_tick"), default=0)
        timeout_ticks = self._to_int(task.get("timeout_ticks"), default=0)
        wait_until_tick = self._to_int(task.get("wait_until_tick"), default=0)
        created_tick = self._to_int(task.get("created_tick"), default=0)
        replan_count = self._to_int(task.get("replan_count"), default=0)
        max_replans = self._to_int(task.get("max_replans"), default=1)

        payload = {
            "task_name": str(task.get("task_name") or self._task_id(task)),
            "status": str(task.get("status") or "queued"),
            "priority": priority,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "retry_delay": retry_delay,
            "next_retry_tick": next_retry_tick,
            "timeout_ticks": timeout_ticks,
            "wait_until_tick": wait_until_tick,
            "created_tick": created_tick,
            "last_run_tick": task.get("last_run_tick"),
            "last_failure_tick": task.get("last_failure_tick"),
            "finished_tick": task.get("finished_tick"),
            "last_error": task.get("last_error"),
            "history": copy.deepcopy(history),
            "runtime_state_file": str(task.get("runtime_state_file") or ""),
            "plan_file": str(task.get("plan_file") or ""),
            "log_file": str(task.get("log_file") or ""),
            "result_file": str(task.get("result_file") or ""),
            "execution_log_file": str(task.get("execution_log_file") or ""),
            "workspace_root": str(task.get("workspace_root") or self.workspace_root),
            "workspace_dir": str(task.get("workspace_dir") or self.tasks_root),
            "shared_dir": str(task.get("shared_dir") or self.shared_dir),
            "task_dir": str(task.get("task_dir") or ""),
            "current_step_index": current_step_index,
            "steps_total": steps_total,
            "steps": copy.deepcopy(steps),
            "results": copy.deepcopy(results),
            "step_results": copy.deepcopy(results),
            "last_step_result": copy.deepcopy(results[-1]) if results else None,
            "final_answer": str(task.get("final_answer") or ""),
            "replan_count": replan_count,
            "replanned": bool(task.get("replanned", False)),
            "replan_reason": str(task.get("replan_reason") or ""),
            "max_replans": max_replans,
            "execution_log": copy.deepcopy(execution_log),
            "goal": str(task.get("goal") or ""),
            "title": str(task.get("title") or task.get("goal") or ""),
            "planner_result": copy.deepcopy(planner_result),
        }

        if depends_on:
            payload["depends_on"] = copy.deepcopy(depends_on)
        else:
            payload["depends_on"] = []

        return payload

    def _build_execution_log(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        execution_log = self._ensure_list(task.get("execution_log"))
        return copy.deepcopy(execution_log)

    def _build_result_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        status = str(task.get("status") or "queued")
        final_answer = task.get("final_answer")
        if final_answer is None:
            final_answer = ""

        result_payload = {
            "ok": self._result_ok_from_status(status),
            "task_name": str(task.get("task_name") or self._task_id(task)),
            "status": status,
            "final_answer": str(final_answer),
            "result": copy.deepcopy(self._last_result(task)),
            "error": task.get("last_error"),
        }
        return result_payload

    # ============================================================
    # helpers
    # ============================================================

    def _touch_log_file(self, task: Dict[str, Any]) -> None:
        log_path = str(task.get("log_file") or "").strip()
        if not log_path:
            return

        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")

    def _last_result(self, task: Dict[str, Any]) -> Any:
        results = self._ensure_list(task.get("results"))
        if results:
            return results[-1]
        return None

    def _result_ok_from_status(self, status: str) -> Optional[bool]:
        normalized = str(status or "").strip().lower()
        if normalized in {"finished", "done", "success", "completed"}:
            return True
        if normalized in {"failed", "error", "cancelled", "timeout"}:
            return False
        return None

    def _task_id(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()

    def _ensure_list(self, value: Any, default: Optional[List[Any]] = None) -> List[Any]:
        if isinstance(value, list):
            return copy.deepcopy(value)
        if default is not None:
            return copy.deepcopy(default)
        return []

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _write_json(self, path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_json(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)