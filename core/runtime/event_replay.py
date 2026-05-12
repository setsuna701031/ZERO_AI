from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_normalizer import normalize_runtime_event_stream_envelope
from core.runtime.event_sink import RuntimeEventSink


class RuntimeEventReplay:
    def __init__(self, path: str | Path) -> None:
        self.sink = RuntimeEventSink(path)

    def events(self) -> List[Dict[str, Any]]:
        return normalize_runtime_event_stream_envelope(self.sink.read_events(), source="event_replay")

    def latest(self) -> Dict[str, Any]:
        events = self.events()
        return events[-1] if events else {}

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            n = max(0, int(limit))
        except Exception:
            n = 20
        return self.events()[-n:] if n else []

    def filter_by_phase(self, runtime_phase: str) -> List[Dict[str, Any]]:
        phase = str(runtime_phase or "").strip()
        return [event for event in self.events() if str(event.get("runtime_phase") or "") == phase]

    def filter_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        target = str(task_id or "").strip()
        return [event for event in self.events() if str(event.get("task_id") or "") == target]

    def timeline(self) -> Dict[str, Any]:
        events = sorted(self.events(), key=lambda item: float(item.get("timestamp") or 0))
        return {
            "ok": True,
            "runtime_phase": "event_replay",
            "event_count": len(events),
            "events": events,
        }
