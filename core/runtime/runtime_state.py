from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_snapshot import RuntimeSnapshot


class RuntimeState:
    def __init__(self, event_log_path: str | Path) -> None:
        self.snapshot = RuntimeSnapshot(event_log_path)

    def aggregate(self) -> Dict[str, Any]:
        snapshot = self.snapshot.build_snapshot()
        events = snapshot.get("recent_events", [])
        if not isinstance(events, list):
            events = []

        return {
            "ok": bool(snapshot.get("ok", True)),
            "runtime_phase": "runtime_state",
            "runtime_status": self.current_status(snapshot=snapshot),
            "active_runtime": self.active_runtime(events=events),
            "active_task": str(snapshot.get("active_task") or ""),
            "last_event": snapshot.get("last_event") if isinstance(snapshot.get("last_event"), dict) else {},
            "last_failure": self.last_failure(snapshot=snapshot),
            "health_report": self.health_report(snapshot=snapshot),
            "event_count": int(snapshot.get("event_count", 0) or 0),
            "recent_events": events,
        }

    def current_status(self, *, snapshot: Dict[str, Any] | None = None) -> str:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        return str(data.get("runtime_status") or "idle")

    def active_runtime(self, *, events: List[Dict[str, Any]] | None = None) -> str:
        source = events if isinstance(events, list) else self.snapshot.build_snapshot().get("recent_events", [])
        if not isinstance(source, list):
            return ""

        for event in reversed(source):
            if not isinstance(event, dict):
                continue
            phase = str(event.get("runtime_phase") or "").strip()
            if phase:
                return phase

        return ""

    def last_failure(self, *, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        failure = data.get("failure_state")
        return failure if isinstance(failure, dict) else {}

    def health_report(self, *, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        status = str(data.get("runtime_status") or "idle").strip().lower()
        failure = data.get("failure_state")

        degraded = bool(failure) or status in {"degraded", "failed", "error", "blocked"}

        return {
            "ok": not degraded,
            "status": status or "idle",
            "degraded": degraded,
            "event_count": int(data.get("event_count", 0) or 0),
            "active_task": str(data.get("active_task") or ""),
        }
