from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.runtime.runtime_monitor import RuntimeMonitor
from core.runtime.runtime_recovery import RuntimeRecovery
from core.runtime.runtime_snapshot import RuntimeSnapshot
from core.runtime.runtime_state import RuntimeState


class RuntimeOrchestrator:
    def __init__(
        self,
        event_log_path: str | Path,
        *,
        stalled_timeout_seconds: float = 300.0,
        max_recovery_attempts: int = 3,
    ) -> None:
        self.event_log_path = Path(event_log_path)
        self.monitor = RuntimeMonitor(
            self.event_log_path,
            stalled_timeout_seconds=stalled_timeout_seconds,
        )
        self.recovery = RuntimeRecovery(max_recovery_attempts=max_recovery_attempts)
        self.snapshot = RuntimeSnapshot(self.event_log_path)
        self.state = RuntimeState(self.event_log_path)

    def evaluate_runtime(self) -> Dict[str, Any]:
        state = self.state.aggregate()
        monitor_result = self.monitor.poll()

        merged_state = {
            **state,
            "degraded": bool(monitor_result.get("degraded")),
            "stalled": bool(monitor_result.get("stalled")),
            "alerts": monitor_result.get("alerts", []),
        }

        recovery_result = self.recovery.evaluate(merged_state)
        snapshot = self.snapshot.build_snapshot()

        return {
            "ok": bool(monitor_result.get("ok", True)) and not bool(recovery_result.get("recovery_blocked")),
            "runtime_phase": "runtime_orchestrator",
            "runtime_status": merged_state.get("runtime_status", "unknown"),
            "monitor": monitor_result,
            "recovery": recovery_result,
            "snapshot": snapshot,
            "state": state,
        }

    def should_trigger_recovery(self) -> bool:
        result = self.evaluate_runtime()
        recovery = result.get("recovery")
        if not isinstance(recovery, dict):
            return False
        return str(recovery.get("action") or "") == "recover"
