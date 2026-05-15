from __future__ import annotations

import copy
import json
from typing import Any

from core.runtime.runtime_recovery_event_schema import build_runtime_recovery_event


class RuntimeRecoveryAuditArtifactBuilder:
    """Build audit-safe artifacts from runtime recovery presentation events."""

    SCHEMA = "zero.runtime.recovery_audit_artifact.v1"
    ARTIFACT_TYPE = "runtime.recovery.presentation_audit"

    def build(
        self,
        source: Any,
        *,
        audit_id: str = "",
        task_id: str = "",
        recovery_id: str = "",
    ) -> dict[str, Any]:
        event = build_runtime_recovery_event(
            source=source,
            task_id=task_id,
            recovery_id=recovery_id,
        )

        artifact = {
            "ok": bool(event.get("ok", False)),
            "schema": self.SCHEMA,
            "artifact_type": self.ARTIFACT_TYPE,
            "audit_id": str(audit_id or ""),
            "task_id": str(event.get("task_id") or task_id or ""),
            "recovery_id": str(event.get("recovery_id") or recovery_id or ""),
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "invokes_scheduler": False,
            "adds_persistence": False,
            "uses_network": False,
            "readiness": str(event.get("readiness") or ""),
            "status": str(event.get("status") or ""),
            "summary": str(event.get("summary") or ""),
            "blockers": self._safe_list(event.get("blockers")),
            "operator_summary": copy.deepcopy(event.get("operator_summary") or {}),
            "source_event": copy.deepcopy(event),
        }
        return self._json_safe(artifact)

    def _safe_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item) for item in value if str(item).strip()]
        text = str(value).strip() if value is not None else ""
        return [text] if text else []

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


def build_runtime_recovery_audit_artifact(
    source: Any,
    *,
    audit_id: str = "",
    task_id: str = "",
    recovery_id: str = "",
) -> dict[str, Any]:
    return RuntimeRecoveryAuditArtifactBuilder().build(
        source,
        audit_id=audit_id,
        task_id=task_id,
        recovery_id=recovery_id,
    )


__all__ = [
    "RuntimeRecoveryAuditArtifactBuilder",
    "build_runtime_recovery_audit_artifact",
]
