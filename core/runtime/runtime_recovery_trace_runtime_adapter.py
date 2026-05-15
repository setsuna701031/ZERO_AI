from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_recovery_trace_adapter import (
    build_runtime_recovery_trace_event,
)
from core.tools.execution_trace import ExecutionTrace


class RuntimeRecoveryTraceRuntimeAdapter:
    """Attach runtime recovery presentation events into ExecutionTrace."""

    EVENT_TYPE = "runtime_recovery"

    def append_to_trace(
        self,
        *,
        trace: ExecutionTrace,
        source: Any,
    ) -> dict[str, Any]:
        if not isinstance(trace, ExecutionTrace):
            raise TypeError("trace must be an ExecutionTrace")

        event = build_runtime_recovery_trace_event(source)

        payload = {
            "schema": str(event.get("schema") or ""),
            "event_type": str(event.get("event_type") or ""),
            "readiness": str(event.get("readiness") or ""),
            "status": str(event.get("status") or ""),
            "summary": str(event.get("summary") or ""),
            "blockers": copy.deepcopy(event.get("blockers") or []),
            "operator_summary": copy.deepcopy(
                event.get("operator_summary") or {}
            ),
            "raw_event": copy.deepcopy(event),
        }

        trace_event = trace.add_event(
            self.EVENT_TYPE,
            payload,
        )

        return copy.deepcopy(trace_event)


def append_runtime_recovery_trace_event(
    *,
    trace: ExecutionTrace,
    source: Any,
) -> dict[str, Any]:
    return RuntimeRecoveryTraceRuntimeAdapter().append_to_trace(
        trace=trace,
        source=source,
    )


__all__ = [
    "RuntimeRecoveryTraceRuntimeAdapter",
    "append_runtime_recovery_trace_event",
]
