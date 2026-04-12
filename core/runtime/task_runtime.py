from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.failure_policy import FailurePolicy  # ✅ NEW

TERMINAL_STATUSES = {
    "finished",
    "failed",
    "cancelled",
    "timeout",
}

NON_TERMINAL_STATUSES = {
    "queued",
    "planning",
    "ready",
    "running",
    "waiting",
    "blocked",
    "retrying",
    "replanning",
    "paused",
}

DEFAULT_FAILURE_TYPE = "internal_error"

FAILURE_TYPES = {
    "transient_error",
    "tool_error",
    "validation_error",
    "dependency_unmet",
    "timeout",
    "unsafe_action_blocked",
    "unsafe_action",
    "cancelled",
    "internal_error",
}


class TaskRuntime:
    def __init__(
        self,
        workspace_root: str = "workspace",
        debug: bool = False,
        trace_log_filename: str = "task_runtime_trace.log",
    ) -> None:
        self.workspace_root = workspace_root
        self.debug = debug
        self.trace_log_filename = trace_log_filename
        self.state_machine = RuntimeStateMachine(debug=debug)

    # ============================================================
    # runtime state
    # ============================================================

    def ensure_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)

        if os.path.exists(runtime_state_file):
            state = self._read_json(runtime_state_file, {})
            return state

        state = self._build_initial_runtime_state(task)
        self._write_json(runtime_state_file, state)
        return state

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        if not os.path.exists(runtime_state_file):
            return self.ensure_runtime_state(task)
        return self._read_json(runtime_state_file, {})

    def save_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        self._ensure_parent_dir(runtime_state_file)
        self._write_json(runtime_state_file, state)
        return state

    # ============================================================
    # 🔥 核心：failure → decision
    # ============================================================

    def mark_failed(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        failure_type: str = DEFAULT_FAILURE_TYPE,
        failure_message: str = "",
    ) -> Dict[str, Any]:

        state = self.load_runtime_state(task)

        failure_type = self._normalize_failure_type(failure_type)

        # ✅ 決策（核心新增）
        decision = FailurePolicy.decide(failure_type)

        state["status"] = "failed"
        state["last_failure_tick"] = current_tick
        state["last_error"] = failure_message
        state["failure_type"] = failure_type
        state["failure_message"] = failure_message

        # ✅ 關鍵：寫入 decision
        state["failure_decision"] = {
            "retry": decision.retry,
            "replan": decision.replan,
            "fail": decision.fail,
            "wait": decision.wait,
        }

        self.save_runtime_state(task, state)

        self._trace(
            "mark_failed",
            {
                "failure_type": failure_type,
                "decision": state["failure_decision"],
            },
            runtime_state_file=self._get_runtime_state_file(task),
        )

        return {
            "ok": False,
            "status": "failed",
            "failure_type": failure_type,
            "decision": state["failure_decision"],
            "task": task,
            "runtime_state": state,
        }

    # ============================================================
    # utils
    # ============================================================

    def _build_initial_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_name": task.get("task_name", ""),
            "status": "queued",
            "steps": [],
            "results": [],
            "execution_log": [],
            "current_step_index": 0,
            "steps_total": 0,
            "replan_count": 0,
            "max_replans": task.get("max_replans", 1),
        }

    def _normalize_failure_type(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in FAILURE_TYPES:
            return text
        return DEFAULT_FAILURE_TYPE

    def _task_name(self, task: Dict[str, Any]) -> str:
        return task.get("task_name") or task.get("task_id") or "unknown_task"

    def _get_runtime_state_file(self, task: Dict[str, Any]) -> str:
        task_dir = task.get("task_dir") or f"{self.workspace_root}/tasks/{self._task_name(task)}"
        return os.path.join(task_dir, "runtime_state.json")

    def _read_json(self, path: str, default: Any = None) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)

    def _write_json(self, path: str, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _ensure_parent_dir(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _trace(self, label: str, payload: Dict[str, Any], runtime_state_file: str = ""):
        trace_path = runtime_state_file.replace("runtime_state.json", "trace.log")
        line = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "label": label,
            "payload": payload,
        }
        try:
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:
            pass

        if self.debug:
            print(label, payload)