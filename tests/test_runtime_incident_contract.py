from __future__ import annotations

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
