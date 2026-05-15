from __future__ import annotations

import copy
import json
from typing import Any


class RuntimeRecoveryTraceAdapter:
    """Convert runtime recovery observer reports into trace-safe events."""

    SCHEMA = "zero.runtime.recovery_trace_event.v1"
    EVENT_TYPE = "runtime.recovery.operator_summary"

    def to_trace_event(
        self,
        source: Any,
        *,
        event_id: str = "",
        task_id: str = "",
        recovery_id: str = "",
    ) -> dict[str, Any]:
        payload = self._payload(source)
        observer_report = self._observer_report(payload)
        operator_summary = self._safe_mapping(
            observer_report.get("operator_summary")
            or payload.get("operator_summary")
        )

        event = {
            "ok": bool(observer_report.get("ok", operator_summary.get("ok", False))),
            "schema": self.SCHEMA,
            "event_type": self.EVENT_TYPE,
            "event_id": self._safe_text(event_id),
            "task_id": self._safe_text(task_id),
            "recovery_id": self._safe_text(recovery_id),
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "invokes_scheduler": False,
            "adds_persistence": False,
            "uses_network": False,
            "readiness": self._safe_text(
                observer_report.get("readiness")
                or operator_summary.get("readiness")
            ),
            "status": self._safe_text(
                observer_report.get("status")
                or operator_summary.get("status")
            ),
            "summary": self._safe_text(
                observer_report.get("summary")
                or operator_summary.get("summary")
            ),
            "blockers": self._safe_list(
                observer_report.get("blockers")
                or operator_summary.get("blockers")
            ),
            "operator_summary": operator_summary,
        }
        return self._json_safe(event)

    def _observer_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._safe_text(payload.get("schema")) == "zero.runtime.recovery_observer.v1":
            return copy.deepcopy(payload)
        return {}

    def _payload(self, source: Any) -> dict[str, Any]:
        if isinstance(source, dict):
            return copy.deepcopy(source)

        payload = getattr(source, "payload", None)
        if isinstance(payload, dict):
            return copy.deepcopy(payload)

        return {}

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item) for item in value if str(item).strip()]
        text = str(value).strip() if value is not None else ""
        return [text] if text else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


def build_runtime_recovery_trace_event(
    source: Any,
    *,
    event_id: str = "",
    task_id: str = "",
    recovery_id: str = "",
) -> dict[str, Any]:
    return RuntimeRecoveryTraceAdapter().to_trace_event(
        source,
        event_id=event_id,
        task_id=task_id,
        recovery_id=recovery_id,
    )


__all__ = [
    "RuntimeRecoveryTraceAdapter",
    "build_runtime_recovery_trace_event",
]
