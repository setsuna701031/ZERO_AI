from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStateMachine:
    """
    ZERO Task State Machine v2

    目標：
    - 管理 task state
    - 寫入 state.json
    - 寫入 timeline.jsonl
    - 支援 initialize / transition / patch_state
    - 不強制覆蓋舊 state/timeline
    """

    VALID_STATES = {
        "created",
        "planning",
        "running",
        "reflecting",
        "finished",
        "failed",
    }

    def __init__(self, task_dir: Path | str) -> None:
        self.task_dir = Path(task_dir)
        self.task_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.task_dir / "state.json"
        self.timeline_file = self.task_dir / "timeline.jsonl"

        if not self.state_file.exists():
            self._write_state(
                {
                    "current_state": "created",
                    "history": [],
                    "updated_at": self._now_iso(),
                }
            )

    # =========================================================
    # Public
    # =========================================================

    def initialize(
        self,
        task_name: str,
        goal: str,
        task_type: str,
        force_new_run: bool = False,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        force_new_run=False:
            - 若已存在 state，保留既有 state，只 patch 欄位
        force_new_run=True:
            - 建立新的 lifecycle history 起點
        """
        now = self._now_iso()
        existing = self.read_state()

        if force_new_run or not existing.get("history"):
            state = {
                "task_name": task_name,
                "goal": goal,
                "task_type": task_type,
                "current_state": "created",
                "history": [
                    {
                        "state": "created",
                        "at": now,
                    }
                ],
                "updated_at": now,
            }
            if isinstance(extra_fields, dict):
                state.update(extra_fields)

            self._write_state(state)
            self.append_event(
                event_type="task_created",
                message="Task created.",
                data={
                    "task_name": task_name,
                    "goal": goal,
                    "task_type": task_type,
                    **(extra_fields or {}),
                },
            )
            return state

        # patch existing without resetting history
        existing["task_name"] = task_name
        existing["goal"] = goal
        existing["task_type"] = task_type
        existing["updated_at"] = now

        if isinstance(extra_fields, dict):
            existing.update(extra_fields)

        self._write_state(existing)
        self.append_event(
            event_type="task_initialized",
            message="Task state initialized from existing state.",
            data={
                "task_name": task_name,
                "goal": goal,
                "task_type": task_type,
                **(extra_fields or {}),
            },
        )
        return existing

    def transition(
        self,
        new_state: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_state = str(new_state).strip().lower()
        if clean_state not in self.VALID_STATES:
            raise ValueError(f"Invalid task state: {new_state}")

        state = self.read_state()

        now = self._now_iso()
        state["current_state"] = clean_state
        state["updated_at"] = now

        history = state.get("history", [])
        if not isinstance(history, list):
            history = []

        history.append(
            {
                "state": clean_state,
                "at": now,
            }
        )
        state["history"] = history

        if isinstance(data, dict):
            for key, value in data.items():
                if key not in {"history"}:
                    state[key] = value

        self._write_state(state)

        self.append_event(
            event_type="state_transition",
            message=message,
            data={
                "new_state": clean_state,
                **(data or {}),
            },
        )
        return state

    def patch_state(self, updates: Dict[str, Any], message: str = "State patched.") -> Dict[str, Any]:
        if not isinstance(updates, dict):
            raise TypeError("updates must be a dict.")

        state = self.read_state()
        for key, value in updates.items():
            if key == "history":
                continue
            state[key] = value

        state["updated_at"] = self._now_iso()
        self._write_state(state)

        self.append_event(
            event_type="state_patched",
            message=message,
            data=updates,
        )
        return state

    def append_event(
        self,
        event_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "at": self._now_iso(),
            "event_type": str(event_type).strip(),
            "message": str(message).strip(),
            "data": data or {},
        }

        with open(self.timeline_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        return event

    def read_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {
                "current_state": "created",
                "history": [],
                "updated_at": self._now_iso(),
            }

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return {
            "current_state": "created",
            "history": [],
            "updated_at": self._now_iso(),
        }

    def read_timeline(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        if not self.timeline_file.exists():
            return events

        with open(self.timeline_file, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue

                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if isinstance(item, dict):
                    events.append(item)

        return events

    # =========================================================
    # Internal
    # =========================================================

    def _write_state(self, data: Dict[str, Any]) -> None:
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()