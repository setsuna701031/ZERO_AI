# -*- coding: utf-8 -*-
"""
ZERO Trace Logger

用途：
1. 提供統一 trace 事件格式
2. 支援寫入 json 檔（單一 run / task 一個檔）
3. 支援 execution / decision / correction / verifier / planner 等事件
4. 讓 trace_viewer 能讀到有結構的資料，而不是只有一坨文字

建議輸出目錄：
    data/traces/

事件格式範例：
{
  "ts": "2026-04-09T12:34:56.123456",
  "event_type": "execution",
  "source": "executor",
  "task_id": "task_001",
  "step_id": "step_001",
  "status": "success",
  "title": "execute python file",
  "message": "python workspace/shared/hello.py",
  "raw": {...}
}
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TRACE_DIR = Path("data/traces")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return repr(value)


def _json_default(value: Any) -> Any:
    try:
        if hasattr(value, "__dict__"):
            return value.__dict__
        return str(value)
    except Exception:
        return repr(value)


def _sanitize_payload(obj: Any) -> Any:
    """
    避免 trace 因為不可序列化物件爆掉。
    """
    try:
        json.dumps(obj, ensure_ascii=False, default=_json_default)
        return obj
    except Exception:
        try:
            return json.loads(json.dumps(obj, ensure_ascii=False, default=_json_default))
        except Exception:
            return _safe_str(obj)


@dataclass
class TraceEvent:
    seq: int
    ts: str
    event_type: str
    source: str
    task_id: str = ""
    step_id: str = ""
    status: str = ""
    title: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "event_type": self.event_type,
            "source": self.source,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "raw": _sanitize_payload(self.raw),
        }


class TraceLogger:
    """
    每個 task / run 對應一個 trace 檔。
    """

    def __init__(
        self,
        trace_dir: str | Path = DEFAULT_TRACE_DIR,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source: str = "system",
        auto_flush: bool = True,
    ) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        self.run_id = run_id or self._generate_run_id()
        self.task_id = task_id or ""
        self.source = source
        self.auto_flush = auto_flush

        self._lock = threading.RLock()
        self._events: List[TraceEvent] = []
        self._seq = 0

        self.file_path = self.trace_dir / self._build_file_name()

    def _generate_run_id(self) -> str:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        short = uuid.uuid4().hex[:8]
        return f"run_{now}_{short}"

    def _build_file_name(self) -> str:
        safe_task = self.task_id.strip() if self.task_id else "general"
        safe_task = safe_task.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return f"{safe_task}_{self.run_id}.json"

    @property
    def events(self) -> List[TraceEvent]:
        with self._lock:
            return list(self._events)

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def log(
        self,
        event_type: str,
        *,
        source: Optional[str] = None,
        task_id: Optional[str] = None,
        step_id: Optional[str] = None,
        status: Optional[str] = None,
        title: Optional[str] = None,
        message: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        event = TraceEvent(
            seq=self._next_seq(),
            ts=_now_iso(),
            event_type=_safe_str(event_type),
            source=_safe_str(source if source is not None else self.source),
            task_id=_safe_str(task_id if task_id is not None else self.task_id),
            step_id=_safe_str(step_id or ""),
            status=_safe_str(status or ""),
            title=_safe_str(title or ""),
            message=_safe_str(message or ""),
            raw=_sanitize_payload(raw or {}),
        )

        with self._lock:
            self._events.append(event)
            if self.auto_flush:
                self.flush()

        return event

    def flush(self) -> None:
        payload = self.to_dict()
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
        self.file_path.write_text(text, encoding="utf-8")

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            event_type_counts: Dict[str, int] = {}
            status_counts: Dict[str, int] = {}

            for ev in self._events:
                if ev.event_type:
                    event_type_counts[ev.event_type] = event_type_counts.get(ev.event_type, 0) + 1
                if ev.status:
                    status_counts[ev.status] = status_counts.get(ev.status, 0) + 1

            return {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "source": self.source,
                "created_at": self._events[0].ts if self._events else _now_iso(),
                "updated_at": _now_iso(),
                "summary": {
                    "event_count": len(self._events),
                    "event_types": event_type_counts,
                    "statuses": status_counts,
                },
                "events": [ev.to_dict() for ev in self._events],
            }

    def set_task(self, task_id: str) -> None:
        with self._lock:
            self.task_id = _safe_str(task_id)

    def mark_start(
        self,
        *,
        title: str = "task start",
        message: str = "",
        source: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "lifecycle",
            source=source,
            status="start",
            title=title,
            message=message,
            raw=raw,
        )

    def mark_end(
        self,
        *,
        title: str = "task end",
        message: str = "",
        status: str = "success",
        source: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "lifecycle",
            source=source,
            status=status,
            title=title,
            message=message,
            raw=raw,
        )

    def log_execution(
        self,
        *,
        step_id: str = "",
        status: str = "",
        title: str = "",
        message: str = "",
        source: str = "executor",
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "execution",
            source=source,
            step_id=step_id,
            status=status,
            title=title,
            message=message,
            raw=raw,
        )

    def log_decision(
        self,
        *,
        step_id: str = "",
        status: str = "",
        title: str = "",
        message: str = "",
        source: str = "planner",
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "decision",
            source=source,
            step_id=step_id,
            status=status,
            title=title,
            message=message,
            raw=raw,
        )

    def log_correction(
        self,
        *,
        step_id: str = "",
        status: str = "",
        title: str = "",
        message: str = "",
        source: str = "correction",
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "correction",
            source=source,
            step_id=step_id,
            status=status,
            title=title,
            message=message,
            raw=raw,
        )

    def log_verifier(
        self,
        *,
        step_id: str = "",
        status: str = "",
        title: str = "",
        message: str = "",
        source: str = "verifier",
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        return self.log(
            "verifier",
            source=source,
            step_id=step_id,
            status=status,
            title=title,
            message=message,
            raw=raw,
        )

    def log_error(
        self,
        *,
        event_type: str = "error",
        step_id: str = "",
        title: str = "",
        message: str = "",
        source: str = "system",
        error: Optional[BaseException] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        payload = dict(raw or {})
        if error is not None:
            payload["error_type"] = type(error).__name__
            payload["error_message"] = str(error)
            payload["traceback"] = traceback.format_exc()

        return self.log(
            event_type,
            source=source,
            step_id=step_id,
            status="error",
            title=title,
            message=message or (str(error) if error else ""),
            raw=payload,
        )


class NullTraceLogger:
    """
    沒接好之前可安全替代，不會讓主流程炸掉。
    """

    file_path = Path("")

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None

    def flush(self) -> None:
        return None

    def set_task(self, task_id: str) -> None:
        return None

    def mark_start(self, *args: Any, **kwargs: Any) -> None:
        return None

    def mark_end(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_execution(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_decision(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_correction(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_verifier(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_error(self, *args: Any, **kwargs: Any) -> None:
        return None


def create_trace_logger(
    *,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    source: str = "system",
    trace_dir: str | Path = DEFAULT_TRACE_DIR,
    auto_flush: bool = True,
) -> TraceLogger:
    return TraceLogger(
        trace_dir=trace_dir,
        run_id=run_id,
        task_id=task_id,
        source=source,
        auto_flush=auto_flush,
    )


def ensure_trace_logger(logger: Optional[Any]) -> Any:
    """
    外部如果沒傳 logger，就補一個 NullTraceLogger。
    """
    return logger if logger is not None else NullTraceLogger()