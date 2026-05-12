from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventStreamAdapterContractTest(unittest.TestCase):
    def test_event_stream_from_execution_trace(self) -> None:
        from core.runtime.event_stream import runtime_event_stream_from_trace
        from core.tools.execution_trace import ExecutionTrace

        trace = ExecutionTrace()
        trace.add_status_event(
            task_id="task-1",
            status="running",
            tick=1,
            final_answer="",
            extra={"ok": True},
        )

        stream = runtime_event_stream_from_trace(trace)

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "status")
        self.assertEqual(stream[0]["task_id"], "task-1")
        self.assertEqual(stream[0]["payload"]["status"], "running")
        self.assertIs(stream[0]["ok"], True)

    def test_event_stream_from_observability_event(self) -> None:
        from core.runtime.event_stream import runtime_event_stream_from_adapter_payload

        payload: Dict[str, Any] = {
            "observability_event": {
                "event_type": "execution_guard",
                "ok": False,
                "runtime_mode": "guard",
                "error_text": "blocked path",
            }
        }

        stream = runtime_event_stream_from_adapter_payload(payload)

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "execution_guard")
        self.assertIs(stream[0]["ok"], False)
        self.assertEqual(stream[0]["runtime_phase"], "guard")
        self.assertEqual(stream[0]["payload"]["error_text"], "blocked path")

    def test_attach_runtime_event_stream_from_adapter_payload_trace(self) -> None:
        from core.runtime.event_stream import attach_runtime_event_stream

        payload: Dict[str, Any] = {
            "adapter_payload": {
                "ok": True,
                "runtime_mode": "execute",
                "execution_trace": [
                    {
                        "event_type": "step",
                        "task_id": "task-2",
                        "ok": True,
                        "runtime_mode": "execute",
                    }
                ],
            }
        }

        adapted = attach_runtime_event_stream(payload, source="adapter_payload")
        stream = adapted.get("runtime_event_stream")

        self.assertIsInstance(stream, list)
        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "step")
        self.assertEqual(stream[0]["task_id"], "task-2")
        self.assertEqual(stream[0]["runtime_phase"], "execute")

    def test_merge_runtime_event_streams_sorts_by_timestamp(self) -> None:
        from core.runtime.event_stream import merge_runtime_event_streams

        stream = merge_runtime_event_streams(
            [{"timestamp": 3, "event_type": "third"}],
            [{"timestamp": 1, "event_type": "first"}],
            [{"timestamp": 2, "event_type": "second"}],
        )

        self.assertEqual([item["event_type"] for item in stream], ["first", "second", "third"])


if __name__ == "__main__":
    unittest.main()