from __future__ import annotations

from collections import defaultdict
from typing import Any


class RuntimeIncidentLayer:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def attach_event(self, event: dict[str, Any]) -> None:
        self._events.append(dict(event))

    def build_incidents(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for event in self._events:
            incident_id = (
                event.get("incident_id")
                or event.get("task_id")
                or "runtime-global"
            )

            grouped[str(incident_id)].append(event)

        incidents: list[dict[str, Any]] = []

        for incident_id, events in grouped.items():
            incidents.append(
                {
                    "incident_id": incident_id,
                    "runtime_phase": "runtime_incident",
                    "event_count": len(events),
                    "events": list(events),
                    "root_event": events[0] if events else {},
                    "latest_event": events[-1] if events else {},
                    "has_failure": any(
                        event.get("event_type") == "failure"
                        for event in events
                    ),
                    "has_recovery": any(
                        event.get("event_type") == "recovery"
                        for event in events
                    ),
                }
            )

        incidents.sort(key=lambda item: item["incident_id"])
        return incidents

    def incident_summary(self) -> dict[str, Any]:
        incidents = self.build_incidents()

        return {
            "runtime_phase": "runtime_incident_summary",
            "incident_count": len(incidents),
            "failure_incidents": sum(
                1 for item in incidents if item["has_failure"]
            ),
            "recovered_incidents": sum(
                1 for item in incidents if item["has_recovery"]
            ),
            "incidents": incidents,
        }
