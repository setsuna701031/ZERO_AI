from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_recovery_coordinator import (
    RuntimeRecoveryCoordinator,
    RuntimeRecoveryStep,
)


@dataclass(frozen=True)
class RuntimeRecoveryAuditRecord:
    audit_id: str
    recovery_id: str
    source_session_id: str
    repair_session_id: str
    replay_id: str
    status: str
    verified: bool
    steps: list[RuntimeRecoveryStep]
    payload: Any
    metadata: Any
    sequence: int


class RuntimeRecoveryAuditRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeRecoveryAudit:
    def __init__(
        self,
        recovery_coordinator: RuntimeRecoveryCoordinator | None = None,
    ) -> None:
        self.recovery_coordinator = (
            recovery_coordinator
            if recovery_coordinator is not None
            else RuntimeRecoveryCoordinator()
        )
        self._audits: dict[str, RuntimeRecoveryAuditRecord] = {}
        self._sequence = 0

    def record_recovery(
        self,
        audit_id: str,
        recovery_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeRecoveryAuditRecord:
        audit_id = self._validate_audit_id(audit_id)
        if audit_id in self._audits:
            raise RuntimeRecoveryAuditRejected(
                f"runtime recovery audit already exists: {audit_id!r}"
            )

        plan = self._get_recovery_plan(recovery_id)
        self._sequence += 1
        audit = RuntimeRecoveryAuditRecord(
            audit_id=audit_id,
            recovery_id=plan.recovery_id,
            source_session_id=plan.source_session_id,
            repair_session_id=plan.repair_session_id,
            replay_id=plan.replay_id,
            status=plan.status,
            verified=plan.verified,
            steps=list(plan.steps),
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._audits[audit_id] = audit
        return self._copy_audit(audit)

    def get_audit(self, audit_id: str) -> RuntimeRecoveryAuditRecord | None:
        audit = self._audits.get(audit_id)
        if audit is None:
            return None

        return self._copy_audit(audit)

    def get_audits(
        self,
        recovery_id: str | None = None,
    ) -> list[RuntimeRecoveryAuditRecord]:
        audits = list(self._audits.values())
        if recovery_id is not None:
            audits = [
                audit
                for audit in audits
                if audit.recovery_id == recovery_id
            ]

        return [self._copy_audit(audit) for audit in audits]

    def clear(self) -> None:
        self._audits.clear()
        self._sequence = 0

    def _get_recovery_plan(self, recovery_id: str):
        try:
            plan = self.recovery_coordinator.get_recovery(recovery_id)
        except Exception as exc:
            raise RuntimeRecoveryAuditRejected(
                "runtime recovery audit coordinator lookup failed",
                original_exception=exc,
            ) from exc

        if plan is None:
            raise RuntimeRecoveryAuditRejected(
                "runtime recovery audit recovery does not exist: "
                f"{recovery_id!r}"
            )

        return plan

    def _validate_audit_id(self, audit_id: str) -> str:
        if not str(audit_id or "").strip():
            raise RuntimeRecoveryAuditRejected(
                "runtime recovery audit_id is required"
            )

        return audit_id

    def _copy_audit(
        self,
        audit: RuntimeRecoveryAuditRecord,
    ) -> RuntimeRecoveryAuditRecord:
        return replace(audit, steps=list(audit.steps))
