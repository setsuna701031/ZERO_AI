from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional


class ExecutionTrace:
    """
    結構化執行追蹤器

    目標：
    1. 把 step / error / replan / final 統一記成事件
    2. 可輸出成 JSON 檔
    3. 可被 scheduler / replanner / fix_engine 重用
    """

    def __init__(self, trace_file: Optional[str] = None) -> None:
        self.trace_file = trace_file
        self.events: List[Dict[str, Any]] = []

    # ------------------------------------------------------------
    # 基本事件
    # ------------------------------------------------------------

    def add_event(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "ts": time.time(),
            "event_type": str(event_type or "").strip(),
            "data": copy.deepcopy(data) if isinstance(data, dict) else {},
        }
        self.events.append(payload)
        return payload

    def add_step_event(
        self,
        task_id: str,
        step_index: int,
        step: Dict[str, Any],
        ok: bool,
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
        tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.add_event(
            "step",
            {
                "task_id": str(task_id or ""),
                "tick": tick,
                "step_index": int(step_index),
                "step": copy.deepcopy(step),
                "ok": bool(ok),
                "result": copy.deepcopy(result) if isinstance(result, dict) else {},
                "error": str(error or ""),
            },
        )

    def add_replan_event(
        self,
        task_id: str,
        failed_step_index: int,
        failed_step_type: str,
        error_type: str,
        failed_error: str,
        repair_mode: str,
        replan_count: int,
        max_replans: int,
        new_steps: Optional[List[Dict[str, Any]]] = None,
        tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.add_event(
            "replan",
            {
                "task_id": str(task_id or ""),
                "tick": tick,
                "failed_step_index": int(failed_step_index),
                "failed_step_type": str(failed_step_type or ""),
                "error_type": str(error_type or ""),
                "failed_error": str(failed_error or ""),
                "repair_mode": str(repair_mode or ""),
                "replan_count": int(replan_count),
                "max_replans": int(max_replans),
                "new_steps": copy.deepcopy(new_steps) if isinstance(new_steps, list) else [],
            },
        )

    def add_status_event(
        self,
        task_id: str,
        status: str,
        tick: Optional[int] = None,
        final_answer: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "task_id": str(task_id or ""),
            "tick": tick,
            "status": str(status or ""),
            "final_answer": str(final_answer or ""),
        }
        if isinstance(extra, dict):
            payload.update(copy.deepcopy(extra))
        return self.add_event("status", payload)

    def add_summary_event(
        self,
        task_id: str,
        summary: str,
        tick: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "task_id": str(task_id or ""),
            "tick": tick,
            "summary": str(summary or ""),
        }
        if isinstance(extra, dict):
            payload.update(copy.deepcopy(extra))
        return self.add_event("summary", payload)

    # ------------------------------------------------------------
    # 讀寫
    # ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_version": 1,
            "event_count": len(self.events),
            "events": copy.deepcopy(self.events),
        }

    def save(self, trace_file: Optional[str] = None) -> Optional[str]:
        path = str(trace_file or self.trace_file or "").strip()
        if not path:
            return None

        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        self.trace_file = path
        return path

    def load(self, trace_file: Optional[str] = None) -> Dict[str, Any]:
        path = str(trace_file or self.trace_file or "").strip()
        if not path or not os.path.exists(path):
            return self.to_dict()

        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
            self.events = payload["events"]
        else:
            self.events = []

        self.trace_file = path
        return self.to_dict()

    # ------------------------------------------------------------
    # helper
    # ------------------------------------------------------------

    def clear(self) -> None:
        self.events = []

    def extend_from_events(self, events: List[Dict[str, Any]]) -> None:
        if not isinstance(events, list):
            return
        for item in events:
            if isinstance(item, dict):
                self.events.append(copy.deepcopy(item))