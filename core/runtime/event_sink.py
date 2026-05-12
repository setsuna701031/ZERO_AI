from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_normalizer import normalize_runtime_event_envelope


class RuntimeEventSink:
    """
    Append-only JSONL runtime event sink.

    This is the persistence layer for normalized runtime events.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append_event(self, event: Any, *, source: str = "runtime") -> Dict[str, Any]:
        normalized = normalize_runtime_event_envelope(event, source=source)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")

        return normalized

    def append_events(self, events: Any, *, source: str = "runtime") -> List[Dict[str, Any]]:
        if isinstance(events, dict):
            if isinstance(events.get("runtime_event_stream"), list):
                events = events.get("runtime_event_stream")
            elif isinstance(events.get("events"), list):
                events = events.get("events")
            else:
                events = [events]

        if not isinstance(events, list):
            return []

        appended: List[Dict[str, Any]] = []
        for event in events:
            if isinstance(event, dict):
                appended.append(self.append_event(event, source=source))
        return appended

    def read_events(self, *, limit: int | None = None) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        events: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except Exception:
                    continue
                if isinstance(item, dict):
                    events.append(item)

        if isinstance(limit, int) and limit >= 0:
            return events[-limit:]
        return events

    def snapshot(self, *, limit: int | None = None) -> Dict[str, Any]:
        events = self.read_events(limit=limit)
        return {
            "ok": True,
            "runtime_phase": "event_sink",
            "path": str(self.path),
            "event_count": len(events),
            "events": events,
        }

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
