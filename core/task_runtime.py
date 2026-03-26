from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class RuntimeEvent:
    timestamp: str
    event_type: str
    task_id: Optional[str]
    message: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "message": self.message,
            "meta": self.meta,
        }


class TaskRuntime:
    """
    第一版 Runtime：
    - 追蹤目前 active root task
    - 追蹤 current running task
    - 記錄每一步結果 / 錯誤
    - 方便 agent_loop 讀寫執行狀態
    """

    def __init__(self) -> None:
        self.active_root_task_id: Optional[str] = None
        self.current_task_id: Optional[str] = None
        self.step_results: Dict[str, str] = {}
        self.step_errors: Dict[str, str] = {}
        self.events: List[RuntimeEvent] = []
        self.last_result: Optional[str] = None
        self.last_error: Optional[str] = None

    # -------------------------------------------------------------------------
    # Root task / current task
    # -------------------------------------------------------------------------
    def set_active_root_task(self, task_id: Optional[str]) -> None:
        self.active_root_task_id = task_id
        self._log_event(
            event_type="set_active_root_task",
            task_id=task_id,
            message=f"Active root task set to: {task_id}",
        )

    def get_active_root_task(self) -> Optional[str]:
        return self.active_root_task_id

    def set_current_task(self, task_id: Optional[str]) -> None:
        self.current_task_id = task_id
        self._log_event(
            event_type="set_current_task",
            task_id=task_id,
            message=f"Current task set to: {task_id}",
        )

    def get_current_task(self) -> Optional[str]:
        return self.current_task_id

    # -------------------------------------------------------------------------
    # 結果 / 錯誤
    # -------------------------------------------------------------------------
    def record_step_result(self, task_id: str, result: str) -> None:
        self.step_results[task_id] = result
        self.last_result = result
        self.last_error = None
        self._log_event(
            event_type="step_result",
            task_id=task_id,
            message=result,
        )

    def get_step_result(self, task_id: str) -> Optional[str]:
        return self.step_results.get(task_id)

    def record_step_error(self, task_id: str, error: str) -> None:
        self.step_errors[task_id] = error
        self.last_error = error
        self._log_event(
            event_type="step_error",
            task_id=task_id,
            message=error,
        )

    def get_step_error(self, task_id: str) -> Optional[str]:
        return self.step_errors.get(task_id)

    def get_last_result(self) -> Optional[str]:
        return self.last_result

    def get_last_error(self) -> Optional[str]:
        return self.last_error

    # -------------------------------------------------------------------------
    # 事件紀錄
    # -------------------------------------------------------------------------
    def log_info(self, message: str, task_id: Optional[str] = None, **meta: Any) -> None:
        self._log_event(
            event_type="info",
            task_id=task_id,
            message=message,
            meta=meta,
        )

    def log_warning(self, message: str, task_id: Optional[str] = None, **meta: Any) -> None:
        self._log_event(
            event_type="warning",
            task_id=task_id,
            message=message,
            meta=meta,
        )

    def log_error(self, message: str, task_id: Optional[str] = None, **meta: Any) -> None:
        self._log_event(
            event_type="error",
            task_id=task_id,
            message=message,
            meta=meta,
        )

    def get_events(self) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in self.events]

    def clear_events(self) -> None:
        self.events.clear()

    # -------------------------------------------------------------------------
    # reset / serialize
    # -------------------------------------------------------------------------
    def reset(self) -> None:
        self.active_root_task_id = None
        self.current_task_id = None
        self.step_results.clear()
        self.step_errors.clear()
        self.events.clear()
        self.last_result = None
        self.last_error = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_root_task_id": self.active_root_task_id,
            "current_task_id": self.current_task_id,
            "step_results": dict(self.step_results),
            "step_errors": dict(self.step_errors),
            "events": [event.to_dict() for event in self.events],
            "last_result": self.last_result,
            "last_error": self.last_error,
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        self.active_root_task_id = data.get("active_root_task_id")
        self.current_task_id = data.get("current_task_id")
        self.step_results = dict(data.get("step_results", {}))
        self.step_errors = dict(data.get("step_errors", {}))
        self.last_result = data.get("last_result")
        self.last_error = data.get("last_error")

        self.events = []
        for item in data.get("events", []):
            self.events.append(
                RuntimeEvent(
                    timestamp=item.get("timestamp", _utc_now_iso()),
                    event_type=item.get("event_type", "info"),
                    task_id=item.get("task_id"),
                    message=item.get("message", ""),
                    meta=dict(item.get("meta", {})),
                )
            )

    # -------------------------------------------------------------------------
    # internal
    # -------------------------------------------------------------------------
    def _log_event(
        self,
        event_type: str,
        task_id: Optional[str],
        message: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.events.append(
            RuntimeEvent(
                timestamp=_utc_now_iso(),
                event_type=event_type,
                task_id=task_id,
                message=message,
                meta=meta or {},
            )
        )