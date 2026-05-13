from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeMonitorContractTest(unittest.TestCase):
    def test_monitor_detects_healthy_runtime(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_monitor import RuntimeMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "status": "running",
                "task_id": "task-1",
                "timestamp": time.time(),
            })

            monitor = RuntimeMonitor(path)
            result = monitor.poll()

        self.assertTrue(result["ok"])
        self.assertFalse(result["degraded"])
        self.assertFalse(result["stalled"])

    def test_monitor_detects_degraded_runtime(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_monitor import RuntimeMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "failure",
                "runtime_mode": "repo_state",
                "timestamp": time.time(),
            })

            monitor = RuntimeMonitor(path)
            result = monitor.poll()

        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])
        self.assertEqual(result["alerts"][0]["alert_type"], "runtime_degraded")

    def test_monitor_detects_stalled_runtime(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_monitor import RuntimeMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "status": "running",
                "runtime_mode": "execute",
                "timestamp": time.time() - 9999,
            })

            monitor = RuntimeMonitor(path, stalled_timeout_seconds=10)
            result = monitor.poll()

        self.assertFalse(result["ok"])
        self.assertTrue(result["stalled"])
        self.assertEqual(result["alerts"][0]["alert_type"], "runtime_stalled")


if __name__ == "__main__":
    unittest.main()
