from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FailureObservabilityEnvelopeContractTest(unittest.TestCase):
    def test_build_failure_observability_event_failed(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "task_id": "task-1",
            "status": "failed",
            "failure_type": "execution_failed",
            "last_error": "boom",
            "retry_count": 1,
            "replan_count": 2,
            "repair_fingerprint": "fp-1",
        }

        event = build_failure_observability_event(
            event_type="repo_task_failed",
            task=copy.deepcopy(task),
            task_id="task-1",
            error_text="boom",
            status="failed",
        )

        self.assertEqual(event.get("event_type"), "repo_task_failed")
        self.assertIs(event.get("ok"), False)
        self.assertEqual(event.get("task_id"), "task-1")
        self.assertEqual(event.get("status"), "failed")
        self.assertEqual(event.get("failure_type"), "execution_failed")
        self.assertEqual(event.get("error_text"), "boom")
        self.assertEqual(event.get("runtime_mode"), "repo_state")
        self.assertEqual(event.get("retry_count"), 1)
        self.assertEqual(event.get("replan_count"), 2)
        self.assertEqual(event.get("repair_fingerprint"), "fp-1")

    def test_build_failure_observability_event_requeued(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "task_id": "task-2",
            "status": "queued",
            "failure_message": "retry later",
        }

        event = build_failure_observability_event(
            event_type="repo_task_requeued",
            task=copy.deepcopy(task),
            task_id="task-2",
            error_text="retry later",
            status="queued",
        )

        self.assertEqual(event.get("event_type"), "repo_task_requeued")
        self.assertIs(event.get("ok"), True)
        self.assertEqual(event.get("task_id"), "task-2")
        self.assertEqual(event.get("status"), "queued")
        self.assertEqual(event.get("error_text"), "retry later")
        self.assertEqual(event.get("runtime_mode"), "repo_state")

    def test_failure_observability_event_defaults_task_id_from_task(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "id": "fallback-id",
            "status": "failed",
            "last_error": "fallback error",
        }

        event = build_failure_observability_event(
            event_type="repo_task_failed",
            task=copy.deepcopy(task),
        )

        self.assertEqual(event.get("task_id"), "fallback-id")
        self.assertEqual(event.get("error_text"), "fallback error")
        self.assertEqual(event.get("status"), "failed")


if __name__ == "__main__":
    unittest.main()
