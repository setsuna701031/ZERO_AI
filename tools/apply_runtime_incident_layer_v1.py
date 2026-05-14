from __future__ import annotations

from pathlib import Path


RUNTIME_INCIDENT_PATH = Path("core/runtime/runtime_incident.py")
TEST_PATH = Path("tests/test_runtime_incident_contract.py")


RUNTIME_INCIDENT_CONTENT = r'''from __future__ import annotations

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
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeIncidentContractTest(unittest.TestCase):
    def test_build_runtime_incident_chain(self) -> None:
        from core.runtime.runtime_incident import RuntimeIncidentLayer

        layer = RuntimeIncidentLayer()

        layer.attach_event(
            {
                "event_type": "status",
                "task_id": "task-1",
                "status": "running",
            }
        )

        layer.attach_event(
            {
                "event_type": "failure",
                "task_id": "task-1",
                "message": "runtime exploded",
            }
        )

        layer.attach_event(
            {
                "event_type": "recovery",
                "task_id": "task-1",
                "message": "runtime recovered",
            }
        )

        incidents = layer.build_incidents()

        self.assertEqual(len(incidents), 1)

        incident = incidents[0]

        self.assertEqual(
            incident["runtime_phase"],
            "runtime_incident",
        )

        self.assertEqual(
            incident["incident_id"],
            "task-1",
        )

        self.assertEqual(
            incident["event_count"],
            3,
        )

        self.assertTrue(incident["has_failure"])
        self.assertTrue(incident["has_recovery"])

    def test_runtime_incident_summary(self) -> None:
        from core.runtime.runtime_incident import RuntimeIncidentLayer

        layer = RuntimeIncidentLayer()

        layer.attach_event(
            {
                "event_type": "failure",
                "task_id": "task-A",
            }
        )

        layer.attach_event(
            {
                "event_type": "recovery",
                "task_id": "task-A",
            }
        )

        layer.attach_event(
            {
                "event_type": "status",
                "task_id": "task-B",
            }
        )

        summary = layer.incident_summary()

        self.assertEqual(
            summary["runtime_phase"],
            "runtime_incident_summary",
        )

        self.assertEqual(summary["incident_count"], 2)
        self.assertEqual(summary["failure_incidents"], 1)
        self.assertEqual(summary["recovered_incidents"], 1)

    def test_runtime_incident_root_and_latest_event(self) -> None:
        from core.runtime.runtime_incident import RuntimeIncidentLayer

        layer = RuntimeIncidentLayer()

        layer.attach_event(
            {
                "event_type": "status",
                "task_id": "timeline-task",
                "step": 1,
            }
        )

        layer.attach_event(
            {
                "event_type": "status",
                "task_id": "timeline-task",
                "step": 2,
            }
        )

        incidents = layer.build_incidents()

        incident = incidents[0]

        self.assertEqual(
            incident["root_event"]["step"],
            1,
        )

        self.assertEqual(
            incident["latest_event"]["step"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    RUNTIME_INCIDENT_PATH.parent.mkdir(parents=True, exist_ok=True)

    RUNTIME_INCIDENT_PATH.write_text(
        RUNTIME_INCIDENT_CONTENT,
        encoding="utf-8",
    )

    TEST_PATH.write_text(
        TEST_CONTENT,
        encoding="utf-8",
    )

    print(
        "[runtime-incident-layer-v1] "
        "created core/runtime/runtime_incident.py"
    )

    print(
        "[runtime-incident-layer-v1] "
        "created tests/test_runtime_incident_contract.py"
    )


if __name__ == "__main__":
    main()