from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_replay import RuntimeEventReplay


class RuntimeSnapshot:
    def __init__(self, path: str | Path) -> None:
        self.replay = RuntimeEventReplay(path)

    def build_snapshot(self) -> Dict[str, Any]:
        events = self.replay.events()
        latest = self.replay.latest()

        recent_events = self.replay.tail(10)

        failure_events = [
            event
            for event in events
            if str(event.get("event_type") or "").lower() in {"failure", "error", "guard_blocked"}
        ]

        active_task = ""
        for event in reversed(events):
            candidate = str(event.get("task_id") or "").strip()
            if candidate:
                active_task = candidate
                break

        runtime_status = self._derive_runtime_status(
            latest=latest,
            failure_events=failure_events,
        )

        return {
            "ok": True,
            "runtime_phase": "snapshot",
            "runtime_status": runtime_status,
            "active_task": active_task,
            "last_event": latest,
            "recent_events": recent_events,
            "failure_state": failure_events[-1] if failure_events else {},
            "event_count": len(events),
        }

    def _derive_runtime_status(
        self,
        *,
        latest: Dict[str, Any],
        failure_events: List[Dict[str, Any]],
    ) -> str:
        if failure_events:
            return "degraded"

        status = str(
            latest.get("status")
            or latest.get("payload", {}).get("status")
            or ""
        ).strip().lower()

        if status in {"running", "queued", "blocked"}:
            return status

        if latest:
            return "healthy"

        return "idle"
