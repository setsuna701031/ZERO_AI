from __future__ import annotations

import copy
from typing import Any

from core.runtime.audit_log import AuditLogger
from core.runtime.runtime_recovery_audit_artifact import (
    build_runtime_recovery_audit_artifact,
)


class RuntimeRecoveryAuditLogBridge:
    """Bridge runtime recovery presentation artifacts into AuditLogger."""

    EVENT = "runtime_recovery_presentation"
    SOURCE = "runtime_recovery"

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.audit_logger = (
            audit_logger
            if audit_logger is not None
            else AuditLogger()
        )

    def log_artifact(
        self,
        *,
        payload: dict[str, Any],
        source: Any,
        audit_id: str = "",
        recovery_id: str = "",
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}

        artifact = build_runtime_recovery_audit_artifact(
            source,
            audit_id=audit_id,
            task_id=str(payload.get("task_id") or ""),
            recovery_id=recovery_id,
        )

        self.audit_logger.log_payload_event(
            payload,
            self.EVENT,
            data={
                "artifact": copy.deepcopy(artifact),
            },
            source=self.SOURCE,
        )

        return copy.deepcopy(artifact)


def log_runtime_recovery_audit_artifact(
    *,
    payload: dict[str, Any],
    source: Any,
    audit_id: str = "",
    recovery_id: str = "",
    audit_logger: AuditLogger | None = None,
) -> dict[str, Any]:
    return RuntimeRecoveryAuditLogBridge(
        audit_logger=audit_logger,
    ).log_artifact(
        payload=payload,
        source=source,
        audit_id=audit_id,
        recovery_id=recovery_id,
    )


__all__ = [
    "RuntimeRecoveryAuditLogBridge",
    "log_runtime_recovery_audit_artifact",
]
