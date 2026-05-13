from __future__ import annotations

import time
from typing import Any, Dict, List


class RuntimeRecovery:
    TERMINAL_RUNTIME_STATUSES = {
        "finished",
        "failed",
        "blocked",
    }

    def __init__(
        self,
        *,
        max_recovery_attempts: int = 3,
    ) -> None:
        self.max_recovery_attempts = int(max_recovery_attempts)

    def evaluate(
        self,
        runtime_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        degraded = bool(runtime_state.get("degraded"))
        stalled = bool(runtime_state.get("stalled"))

        recovery_history = runtime_state.get("recovery_history")
        if not isinstance(recovery_history, list):
            recovery_history = []

        attempts = len(recovery_history)

        recovery_required = degraded or stalled

        recovery_blocked = attempts >= self.max_recovery_attempts

        action = "none"

        if recovery_required and not recovery_blocked:
            action = "recover"

        if recovery_required and recovery_blocked:
            action = "halt"

        return {
            "runtime_phase": "runtime_recovery",
            "runtime_status": runtime_state.get("runtime_status", "unknown"),
            "recovery_required": recovery_required,
            "recovery_blocked": recovery_blocked,
            "recovery_attempts": attempts,
            "action": action,
        }

    def create_recovery_event(
        self,
        *,
        reason: str,
        action: str,
    ) -> Dict[str, Any]:
        return {
            "event_type": "runtime_recovery",
            "runtime_phase": "runtime_recovery",
            "runtime_status": action,
            "reason": str(reason or ""),
            "timestamp": time.time(),
        }

    def append_recovery_history(
        self,
        runtime_state: Dict[str, Any],
        *,
        reason: str,
        action: str,
    ) -> Dict[str, Any]:
        history = runtime_state.get("recovery_history")

        if not isinstance(history, list):
            history = []

        event = self.create_recovery_event(
            reason=reason,
            action=action,
        )

        history.append(event)

        runtime_state["recovery_history"] = history

        return runtime_state
