from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RuntimeRecoveryAuditRecord:
    recovery_id: str
    audit_id: str = ""
    source_session_id: str = ""
    repair_session_id: str = ""
    replay_id: str = ""
    status: str = ""
    verified: bool = False
    steps: list[Any] = field(default_factory=list)
    payload: Any = None
    metadata: Any = None
    sequence: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


class RuntimeRecoveryAuditRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeRecoveryAudit:
    """Compatibility recorder for recovery audit records.

    The recorder keeps the old import path and ABI while remaining in-memory
    and read-only with respect to recovery plans from the coordinator.
    """

    def __init__(self, recovery_coordinator: Any = None) -> None:
        self.recovery_coordinator = recovery_coordinator
        self._records: dict[str, RuntimeRecoveryAuditRecord] = {}
        self._order: list[str] = []
        self._sequence = 0

    def record_recovery(
        self,
        audit_id: str,
        recovery_id: str,
        *,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeRecoveryAuditRecord:
        audit_id = self._validate_text("audit_id", audit_id)
        recovery_id = self._validate_text("recovery_id", recovery_id)
        if audit_id in self._records:
            raise RuntimeRecoveryAuditRejected(
                f"runtime recovery audit already exists: {audit_id!r}"
            )

        plan = self._get_recovery(recovery_id)
        if plan is None:
            raise RuntimeRecoveryAuditRejected(
                f"runtime recovery does not exist: {recovery_id!r}"
            )

        self._sequence += 1
        record = RuntimeRecoveryAuditRecord(
            recovery_id=str(getattr(plan, "recovery_id", recovery_id) or recovery_id),
            audit_id=audit_id,
            source_session_id=str(getattr(plan, "source_session_id", "") or ""),
            repair_session_id=str(getattr(plan, "repair_session_id", "") or ""),
            replay_id=str(getattr(plan, "replay_id", "") or ""),
            status=str(getattr(plan, "status", "") or ""),
            verified=bool(getattr(plan, "verified", False)),
            steps=copy.deepcopy(getattr(plan, "steps", []) or []),
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            events=[],
        )
        self._records[audit_id] = copy.deepcopy(record)
        self._order.append(audit_id)
        return record

    def get_audit(self, audit_id: str) -> RuntimeRecoveryAuditRecord:
        audit_id = self._validate_text("audit_id", audit_id)
        record = self._records.get(audit_id)
        if record is None:
            raise RuntimeRecoveryAuditRejected(
                f"runtime recovery audit does not exist: {audit_id!r}"
            )
        return copy.deepcopy(record)

    def get_audits(self, recovery_id: str | None = None) -> list[RuntimeRecoveryAuditRecord]:
        records = [
            copy.deepcopy(self._records[audit_id])
            for audit_id in self._order
            if audit_id in self._records
        ]
        if recovery_id is None:
            return records
        recovery_id = str(recovery_id or "")
        return [record for record in records if record.recovery_id == recovery_id]

    def clear(self) -> None:
        self._records.clear()
        self._order.clear()
        self._sequence = 0

    def _get_recovery(self, recovery_id: str) -> Any:
        coordinator = self.recovery_coordinator
        if coordinator is None:
            return None
        get_recovery = getattr(coordinator, "get_recovery", None)
        if not callable(get_recovery):
            return None
        try:
            return get_recovery(recovery_id)
        except RuntimeRecoveryAuditRejected:
            raise
        except Exception as exc:
            raise RuntimeRecoveryAuditRejected(
                "runtime recovery audit could not read recovery",
                original_exception=exc,
            ) from exc

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeRecoveryAuditRejected(
                f"runtime recovery audit requires {field_name}"
            )
        return text


__all__ = [
    "RuntimeRecoveryAudit",
    "RuntimeRecoveryAuditRecord",
    "RuntimeRecoveryAuditRejected",
]
