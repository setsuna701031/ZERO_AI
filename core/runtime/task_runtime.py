# task_runtime.py
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_FINISHED = "finished"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_RETRYING = "retrying"
TASK_STATUS_WAITING = "waiting"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_PAUSED = "paused"
TASK_STATUS_CANCELED = "canceled"

TERMINAL_STATUSES = {
    TASK_STATUS_FINISHED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELED,
}


@dataclass
class RuntimeTickResult:
    ok: bool
    action: str
    task_name: str
    status: str
    message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "task_name": self.task_name,
            "status": self.status,
            "message": self.message,
            "error": self.error,
        }


class TaskRuntime:
    """
    負責單一 task 的 runtime_state.json 狀態維護。
    這層不直接做 scheduler 排程決策，只負責：
    - 初始化 runtime state
    - 狀態轉換
    - history / error / retry / timeout / wait_until_tick 維護
    - 將 task 在單次 tick 後應該呈現的狀態寫回檔案

    這樣 scheduler.py 只需要專心決定「下一個跑誰」。
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # public api
    # ------------------------------------------------------------------

    def ensure_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        確保 task 對應的 runtime_state.json 一定存在。
        若不存在則依 task 內容建立初始狀態。
        """
        runtime_state_file = self._get_runtime_state_file(task)
        if os.path.exists(runtime_state_file):
            return self.load_runtime_state(task)

        state = self._build_initial_state(task)
        self.save_runtime_state(task, state)
        return state

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state_file = self._get_runtime_state_file(task)
        if not os.path.exists(runtime_state_file):
            return self.ensure_runtime_state(task)

        with open(runtime_state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._normalize_state(task, data)

    def save_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        runtime_state_file = self._get_runtime_state_file(task)
        os.makedirs(os.path.dirname(runtime_state_file), exist_ok=True)

        normalized = self._normalize_state(task, state)

        with open(runtime_state_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)

    def get_status(self, task: Dict[str, Any]) -> str:
        state = self.ensure_runtime_state(task)
        return state["status"]

    def set_status(
        self,
        task: Dict[str, Any],
        new_status: str,
        *,
        error: Optional[str] = None,
        append_history: bool = True,
    ) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state.get("status", TASK_STATUS_QUEUED)
        state["status"] = new_status

        if append_history and old_status != new_status:
            self._append_history(state, f"{old_status} -> {new_status}")

        if error is not None:
            state["last_error"] = error

        self.save_runtime_state(task, state)
        return state

    def mark_running(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_RUNNING
        state["last_run_tick"] = current_tick

        if old_status != TASK_STATUS_RUNNING:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_RUNNING}")

        self.save_runtime_state(task, state)
        return state

    def mark_finished(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_FINISHED
        state["finished_tick"] = current_tick

        if old_status != TASK_STATUS_FINISHED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_FINISHED}")

        self.save_runtime_state(task, state)
        return state

    def mark_canceled(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_CANCELED
        state["finished_tick"] = current_tick

        if old_status != TASK_STATUS_CANCELED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_CANCELED}")

        self.save_runtime_state(task, state)
        return state

    def mark_paused(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_PAUSED

        if old_status != TASK_STATUS_PAUSED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_PAUSED}")

        self.save_runtime_state(task, state)
        return state

    def resume_paused(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_QUEUED

        if old_status != TASK_STATUS_QUEUED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_QUEUED}")

        self.save_runtime_state(task, state)
        return state

    def mark_waiting(
        self,
        task: Dict[str, Any],
        *,
        until_tick: int,
        reason: str = "",
    ) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_WAITING
        state["wait_until_tick"] = max(0, int(until_tick))
        if reason:
            state["last_error"] = reason

        if old_status != TASK_STATUS_WAITING:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_WAITING}")

        self.save_runtime_state(task, state)
        return state

    def wake_waiting_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_QUEUED
        state["wait_until_tick"] = 0

        if old_status != TASK_STATUS_QUEUED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_QUEUED}")

        self.save_runtime_state(task, state)
        return state

    def mark_blocked(self, task: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_BLOCKED
        if reason:
            state["last_error"] = reason

        if old_status != TASK_STATUS_BLOCKED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_BLOCKED}")

        self.save_runtime_state(task, state)
        return state

    def unblock_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_QUEUED

        if old_status != TASK_STATUS_QUEUED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_QUEUED}")

        self.save_runtime_state(task, state)
        return state

    def requeue_running_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        用於 cooperative scheduling：
        running 一輪後沒做完，放回 queue 等下一個 tick。
        """
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_QUEUED

        if old_status != TASK_STATUS_QUEUED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_QUEUED}")

        self.save_runtime_state(task, state)
        return state

    def mark_failed_or_retrying(
        self,
        task: Dict[str, Any],
        *,
        error_message: str,
        current_tick: int,
    ) -> Dict[str, Any]:
        """
        當 task 執行失敗時：
        - 若仍可 retry：進入 retrying，設定 next_retry_tick
        - 否則：進入 failed
        """
        state = self.ensure_runtime_state(task)

        state["last_error"] = error_message
        state["last_failure_tick"] = current_tick
        state["retry_count"] = int(state.get("retry_count", 0)) + 1

        max_retries = int(state.get("max_retries", 0))
        retry_delay = int(state.get("retry_delay", 0))
        old_status = state["status"]

        if state["retry_count"] <= max_retries:
            state["status"] = TASK_STATUS_RETRYING
            state["next_retry_tick"] = current_tick + max(0, retry_delay)

            if old_status != TASK_STATUS_RETRYING:
                self._append_history(state, f"{old_status} -> {TASK_STATUS_RETRYING}")
        else:
            state["status"] = TASK_STATUS_FAILED
            state["finished_tick"] = current_tick

            if old_status != TASK_STATUS_FAILED:
                self._append_history(state, f"{old_status} -> {TASK_STATUS_FAILED}")

        self.save_runtime_state(task, state)
        return state

    def retry_ready_to_queue(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)

        old_status = state["status"]
        state["status"] = TASK_STATUS_QUEUED
        state["next_retry_tick"] = 0

        if old_status != TASK_STATUS_QUEUED:
            self._append_history(state, f"{old_status} -> {TASK_STATUS_QUEUED}")

        self.save_runtime_state(task, state)
        return state

    def check_timeout_before_run(
        self,
        task: Dict[str, Any],
        *,
        current_tick: int,
    ) -> Optional[RuntimeTickResult]:
        """
        若 task 已超時，直接標成 failed。
        timeout_ticks == 0 代表不啟用 timeout。
        """
        state = self.ensure_runtime_state(task)

        timeout_ticks = int(state.get("timeout_ticks", 0))
        if timeout_ticks <= 0:
            return None

        created_tick = int(state.get("created_tick", 0))
        if current_tick - created_tick < timeout_ticks:
            return None

        self.mark_failed_or_retrying(
            task,
            error_message=f"Task timeout after {timeout_ticks} ticks.",
            current_tick=current_tick,
        )
        state = self.load_runtime_state(task)

        return RuntimeTickResult(
            ok=False,
            action="timeout",
            task_name=self._task_name(task),
            status=state["status"],
            message="task timed out",
            error=state.get("last_error"),
        )

    def should_wake_waiting(self, task: Dict[str, Any], current_tick: int) -> bool:
        state = self.ensure_runtime_state(task)
        if state["status"] != TASK_STATUS_WAITING:
            return False
        return current_tick >= int(state.get("wait_until_tick", 0))

    def should_release_retry(self, task: Dict[str, Any], current_tick: int) -> bool:
        state = self.ensure_runtime_state(task)
        if state["status"] != TASK_STATUS_RETRYING:
            return False
        return current_tick >= int(state.get("next_retry_tick", 0))

    def snapshot_for_queue_list(self, task: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_state(task)
        return {
            "task_name": self._task_name(task),
            "status": state["status"],
            "priority": int(state.get("priority", 0)),
            "retry_count": int(state.get("retry_count", 0)),
            "max_retries": int(state.get("max_retries", 0)),
            "timeout_ticks": int(state.get("timeout_ticks", 0)),
            "history": list(state.get("history", [])),
            "last_error": state.get("last_error"),
            "runtime_state_file": self._get_runtime_state_file(task),
            "plan_file": task.get("plan_file"),
            "log_file": task.get("log_file"),
        }

    def sync_runtime_fields_back_to_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        把 runtime_state 的核心欄位同步回 task dict，
        讓舊的 task_manager / queue-list 還可以直接讀 task 內容。
        """
        state = self.ensure_runtime_state(task)
        task = copy.deepcopy(task)

        task["status"] = state["status"]
        task["retry_count"] = state["retry_count"]
        task["max_retries"] = state["max_retries"]
        task["retry_delay"] = state["retry_delay"]
        task["next_retry_tick"] = state["next_retry_tick"]
        task["timeout_ticks"] = state["timeout_ticks"]
        task["wait_until_tick"] = state["wait_until_tick"]
        task["last_error"] = state["last_error"]
        task["history"] = list(state["history"])
        task["runtime_state_file"] = self._get_runtime_state_file(task)

        return task

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _build_initial_state(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self._normalize_state(
            task,
            {
                "task_name": self._task_name(task),
                "status": task.get("status", TASK_STATUS_QUEUED),
                "priority": int(task.get("priority", 0)),
                "retry_count": int(task.get("retry_count", 0)),
                "max_retries": int(
                    task.get("max_retries", task.get("retry", task.get("max_retry", 0)))
                ),
                "retry_delay": int(task.get("retry_delay", task.get("delay", 0))),
                "next_retry_tick": int(task.get("next_retry_tick", 0)),
                "timeout_ticks": int(task.get("timeout_ticks", task.get("timeout", 0))),
                "wait_until_tick": int(task.get("wait_until_tick", 0)),
                "created_tick": int(task.get("created_tick", 0)),
                "last_run_tick": task.get("last_run_tick"),
                "last_failure_tick": task.get("last_failure_tick"),
                "finished_tick": task.get("finished_tick"),
                "last_error": task.get("last_error"),
                "history": list(task.get("history", ["queued"])),
                "runtime_state_file": self._get_runtime_state_file(task),
                "plan_file": task.get("plan_file"),
                "log_file": task.get("log_file"),
            },
        )

    def _normalize_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "task_name": state.get("task_name", self._task_name(task)),
            "status": state.get("status", TASK_STATUS_QUEUED),
            "priority": int(state.get("priority", task.get("priority", 0))),
            "retry_count": int(state.get("retry_count", task.get("retry_count", 0))),
            "max_retries": int(
                state.get(
                    "max_retries",
                    task.get("max_retries", task.get("retry", task.get("max_retry", 0))),
                )
            ),
            "retry_delay": int(
                state.get("retry_delay", task.get("retry_delay", task.get("delay", 0)))
            ),
            "next_retry_tick": int(state.get("next_retry_tick", task.get("next_retry_tick", 0))),
            "timeout_ticks": int(
                state.get("timeout_ticks", task.get("timeout_ticks", task.get("timeout", 0)))
            ),
            "wait_until_tick": int(state.get("wait_until_tick", task.get("wait_until_tick", 0))),
            "created_tick": int(state.get("created_tick", task.get("created_tick", 0))),
            "last_run_tick": state.get("last_run_tick"),
            "last_failure_tick": state.get("last_failure_tick"),
            "finished_tick": state.get("finished_tick"),
            "last_error": state.get("last_error"),
            "history": list(state.get("history", task.get("history", ["queued"]))),
            "runtime_state_file": self._get_runtime_state_file(task),
            "plan_file": state.get("plan_file", task.get("plan_file")),
            "log_file": state.get("log_file", task.get("log_file")),
        }

        if not normalized["history"]:
            normalized["history"] = ["queued"]

        return normalized

    def _append_history(self, state: Dict[str, Any], entry: str) -> None:
        history = state.setdefault("history", [])
        if not history or history[-1] != entry:
            history.append(entry)

    def _get_runtime_state_file(self, task: Dict[str, Any]) -> str:
        if task.get("runtime_state_file"):
            return str(task["runtime_state_file"])

        task_dir = task.get("task_dir")
        if task_dir:
            return os.path.join(task_dir, "runtime_state.json")

        workspace_dir = task.get("workspace_dir", "")
        task_name = self._task_name(task)
        if workspace_dir:
            return os.path.join(workspace_dir, task_name, "runtime_state.json")

        raise ValueError("Task is missing runtime_state_file / task_dir / workspace_dir.")

    def _task_name(self, task: Dict[str, Any]) -> str:
        name = task.get("task_name") or task.get("id") or task.get("name")
        if not name:
            raise ValueError("Task is missing task_name/id/name.")
        return str(name)