from __future__ import annotations

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
