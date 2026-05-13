from __future__ import annotations

from pathlib import Path


MONITOR_PATH = Path("core/runtime/runtime_monitor.py")
TEST_PATH = Path("tests/test_runtime_monitor_contract.py")


MONITOR_CONTENT = r'''from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_state import RuntimeState


class RuntimeMonitor:
    def __init__(
        self,
        event_log_path: str | Path,
        *,
        stalled_timeout_seconds: float = 300.0,
    ) -> None:
        self.state = RuntimeState(event_log_path)
        self.stalled_timeout_seconds = float(stalled_timeout_seconds)

    def poll(self) -> Dict[str, Any]:
        aggregate = self.state.aggregate()

        degraded = self.detect_degraded_state(aggregate=aggregate)
        stalled = self.detect_stalled_runtime(aggregate=aggregate)

        alerts: List[Dict[str, Any]] = []

        if degraded:
            alerts.append(
                self.raise_alert(
                    alert_type="runtime_degraded",
                    message="runtime entered degraded state",
                )
            )

        if stalled:
            alerts.append(
                self.raise_alert(
                    alert_type="runtime_stalled",
                    message="runtime appears stalled",
                )
            )

        return {
            "ok": not degraded and not stalled,
            "runtime_phase": "runtime_monitor",
            "runtime_status": aggregate.get("runtime_status", "idle"),
            "degraded": degraded,
            "stalled": stalled,
            "alerts": alerts,
            "state": aggregate,
        }

    def runtime_summary(self) -> Dict[str, Any]:
        aggregate = self.state.aggregate()

        return {
            "runtime_status": aggregate.get("runtime_status", "idle"),
            "active_runtime": aggregate.get("active_runtime", ""),
            "active_task": aggregate.get("active_task", ""),
            "event_count": aggregate.get("event_count", 0),
            "health_report": aggregate.get("health_report", {}),
        }

    def detect_degraded_state(
        self,
        *,
        aggregate: Dict[str, Any] | None = None,
    ) -> bool:
        data = aggregate if isinstance(aggregate, dict) else self.state.aggregate()

        report = data.get("health_report")
        if isinstance(report, dict):
            return bool(report.get("degraded"))

        status = str(data.get("runtime_status") or "").strip().lower()

        return status in {"degraded", "failed", "error", "blocked"}

    def detect_stalled_runtime(
        self,
        *,
        aggregate: Dict[str, Any] | None = None,
    ) -> bool:
        data = aggregate if isinstance(aggregate, dict) else self.state.aggregate()

        last_event = data.get("last_event")
        if not isinstance(last_event, dict):
            return False

        timestamp = last_event.get("timestamp")

        try:
            ts = float(timestamp)
        except Exception:
            return False

        age = max(0.0, time.time() - ts)

        status = str(data.get("runtime_status") or "").strip().lower()

        return status in {"running", "queued"} and age > self.stalled_timeout_seconds

    def raise_alert(
        self,
        *,
        alert_type: str,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "alert_type": str(alert_type or "runtime_alert"),
            "message": str(message or ""),
            "timestamp": time.time(),
        }
'''


TEST_CONTENT = r'''from __future__ import annotations

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
'''


def main() -> None:
    MONITOR_PATH.write_text(MONITOR_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-monitor-v1] created core/runtime/runtime_monitor.py")
    print("[runtime-monitor-v1] created tests/test_runtime_monitor_contract.py")


if __name__ == "__main__":
    main()