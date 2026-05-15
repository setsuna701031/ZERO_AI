from __future__ import annotations

import copy
import json
from typing import Any


class RuntimeRecoveryObserver:
    """Read-only observer for runtime recovery operator-facing summaries."""

    SCHEMA = "zero.runtime.recovery_observer.v1"

    def observe(self, source: Any) -> dict[str, Any]:
        payload = self._payload(source)
        operator_summary = self._safe_mapping(payload.get("operator_summary"))

        result = {
            "ok": bool(operator_summary.get("ok", False)),
            "schema": self.SCHEMA,
            "mode": "observer_report_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "invokes_scheduler": False,
            "adds_persistence": False,
            "uses_network": False,
            "readiness": self._safe_text(operator_summary.get("readiness")),
            "status": self._safe_text(operator_summary.get("status")),
            "summary": self._safe_text(operator_summary.get("summary")),
            "blockers": self._safe_list(operator_summary.get("blockers")),
            "operator_summary": operator_summary,
        }
        return self._json_safe(result)

    def render_text(self, source: Any) -> str:
        report = self.observe(source)
        summary = self._safe_text(report.get("summary"))
        readiness = self._safe_text(report.get("readiness")) or "unknown"
        blockers = self._safe_list(report.get("blockers"))

        lines = [
            f"Recovery readiness: {readiness}",
            f"Summary: {summary}" if summary else "Summary: ",
        ]

        if blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item}" for item in blockers)

        return "\n".join(lines)

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


def observe_runtime_recovery(source: Any) -> dict[str, Any]:
    return RuntimeRecoveryObserver().observe(source)


def render_runtime_recovery_observation(source: Any) -> str:
    return RuntimeRecoveryObserver().render_text(source)


__all__ = [
    "RuntimeRecoveryObserver",
    "observe_runtime_recovery",
    "render_runtime_recovery_observation",
]
