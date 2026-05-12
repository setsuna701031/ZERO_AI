from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventNormalizerContractTest(unittest.TestCase):
    def test_normalizes_flat_event_into_envelope(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope(
            {
                "event_type": "execution_guard",
                "runtime_mode": "guard",
                "task_id": "task-1",
                "ok": False,
                "error_text": "blocked",
                "guard_mode": "path_blocked",
            },
            source="test",
        )

        self.assertEqual(event["event_type"], "execution_guard")
        self.assertEqual(event["runtime_phase"], "guard")
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["source"], "test")
        self.assertIs(event["ok"], False)
        self.assertEqual(event["payload"]["error_text"], "blocked")
        self.assertEqual(event["payload"]["guard_mode"], "path_blocked")

    def test_normalizes_trace_event_data_payload(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope(
            {
                "ts": 123,
                "event_type": "status",
                "data": {
                    "task_id": "task-2",
                    "status": "running",
                    "ok": True,
                },
            },
            source="trace",
        )

        self.assertEqual(event["event_type"], "status")
        self.assertEqual(event["runtime_phase"], "runtime")
        self.assertEqual(event["task_id"], "task-2")
        self.assertEqual(event["timestamp"], 123)
        self.assertEqual(event["payload"]["status"], "running")
        self.assertIs(event["ok"], True)

    def test_normalizes_stream_dict(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_stream_envelope

        stream = normalize_runtime_event_stream_envelope(
            {
                "runtime_event_stream": [
                    {"event_type": "first", "ts": 1},
                    {"event_type": "second", "ts": 2},
                ]
            },
            source="stream",
        )

        self.assertEqual(len(stream), 2)
        self.assertEqual(stream[0]["event_type"], "first")
        self.assertEqual(stream[1]["event_type"], "second")
        self.assertEqual(stream[0]["source"], "stream")

    def test_non_dict_event_becomes_unknown_payload(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope("bad-event", source="test")

        self.assertEqual(event["event_type"], "unknown")
        self.assertEqual(event["runtime_phase"], "unknown")
        self.assertEqual(event["payload"]["raw"], "bad-event")


if __name__ == "__main__":
    unittest.main()
