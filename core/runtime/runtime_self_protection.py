from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.runtime_integrity import RuntimeIntegrityReport


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeProtectionDecision:
    blocked: bool
    reason: str
    action: str
    quarantined: bool = False
    frozen: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "reason": self.reason,
            "action": self.action,
            "quarantined": self.quarantined,
            "frozen": self.frozen,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RuntimeSelfProtectionState:
    recursive_repair_count: int = 0
    recursive_self_edit_count: int = 0
    rollback_recovery_count: int = 0
    quarantined_mutations: tuple[str, ...] = ()
    mutation_frozen: bool = False


class RuntimeSelfProtectionController:
    def __init__(
        self,
        *,
        max_recursive_repair: int = 1,
        max_recursive_self_edit: int = 0,
        max_rollback_recovery: int = 2,
    ) -> None:
        self.max_recursive_repair = max_recursive_repair
        self.max_recursive_self_edit = max_recursive_self_edit
        self.max_rollback_recovery = max_rollback_recovery
        self.state = RuntimeSelfProtectionState()

    def observe_intent(self, *, category: str, mutation_id: str = "") -> RuntimeProtectionDecision:
        state = self.state
        if category == "recursive repair":
            state = replace(state, recursive_repair_count=state.recursive_repair_count + 1)
            self.state = state
            if state.recursive_repair_count > self.max_recursive_repair:
                return self._freeze("recursive_repair_brake", mutation_id=mutation_id)
        if category == "self-edit":
            state = replace(state, recursive_self_edit_count=state.recursive_self_edit_count + 1)
            self.state = state
            if state.recursive_self_edit_count > self.max_recursive_self_edit:
                return self._freeze("recursive_self_edit_brake", mutation_id=mutation_id)
        return RuntimeProtectionDecision(False, "runtime_pattern_allowed", "continue")

    def observe_rollback_recovery(self, *, mutation_id: str = "") -> RuntimeProtectionDecision:
        state = replace(
            self.state,
            rollback_recovery_count=self.state.rollback_recovery_count + 1,
        )
        self.state = state
        if state.rollback_recovery_count > self.max_rollback_recovery:
            return self._freeze("rollback_recovery_loop_brake", mutation_id=mutation_id)
        return RuntimeProtectionDecision(False, "rollback_recovery_within_budget", "continue")

    def enforce_integrity(
        self,
        reports: tuple[RuntimeIntegrityReport, ...],
        *,
        mutation_id: str = "",
    ) -> RuntimeProtectionDecision:
        failed = [report.to_dict() for report in reports if not report.verified]
        if not failed:
            return RuntimeProtectionDecision(False, "integrity_verified", "continue")
        return self._freeze(
            "integrity_failure_freeze",
            mutation_id=mutation_id,
            evidence={"integrity_failures": failed},
        )

    def quarantine(self, mutation_id: str, *, reason: str, evidence: dict[str, Any] | None = None) -> RuntimeProtectionDecision:
        state = self.state
        cleaned = str(mutation_id or "unknown-mutation")
        quarantined = tuple(sorted(set(state.quarantined_mutations) | {cleaned}))
        self.state = replace(state, quarantined_mutations=quarantined, mutation_frozen=True)
        return RuntimeProtectionDecision(
            blocked=True,
            reason=reason,
            action="quarantine_mutation",
            quarantined=True,
            frozen=True,
            evidence={"mutation_id": cleaned, **dict(evidence or {})},
        )

    def blocked_result(
        self,
        decision: RuntimeProtectionDecision,
        *,
        execution_id: str,
        execution_start_id: str = "",
        execution_type: str = "runtime_self_protection",
    ) -> RuntimeExecutionResult:
        now = _utc_now()
        return RuntimeExecutionResult(
            execution_id=execution_id,
            execution_start_id=execution_start_id or f"execution_start:{execution_id}",
            execution_type=execution_type,
            status="blocked",
            started_at=now,
            finished_at=now,
            stdout="",
            stderr=decision.reason,
            return_code=1,
            side_effects=(),
            artifacts=(),
            verified=False,
            blocked=True,
            rollback_required=False,
            lineage={"source": "runtime_self_protection"},
            replay_id=None,
            repair_session_id=None,
            risk_level="CRITICAL",
            risk_metadata=decision.to_dict(),
            metadata={"protection_decision": decision.to_dict()},
            executed=False,
            failed=True,
            evidence={"protection": decision.to_dict()},
        )

    def _freeze(
        self,
        reason: str,
        *,
        mutation_id: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> RuntimeProtectionDecision:
        return self.quarantine(
            mutation_id or "runtime-mutation",
            reason=reason,
            evidence=evidence,
        )


__all__ = [
    "RuntimeProtectionDecision",
    "RuntimeSelfProtectionController",
    "RuntimeSelfProtectionState",
    "RuntimeUnlockAuthority",
    "RuntimeUnlockDecision",
    "RuntimeUnlockRejected",
    "RuntimeExecutionRestoration",
    "restore_runtime_execution",
]



class RuntimeUnlockRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeUnlockDecision:
    unlock_approved: bool
    sovereign_locked: bool
    reason: str
    execution_restored: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unlock_approved": self.unlock_approved,
            "sovereign_locked": self.sovereign_locked,
            "reason": self.reason,
            "execution_restored": self.execution_restored,
            "evidence": dict(self.evidence),
        }


class RuntimeUnlockAuthority:
    def evaluate_unlock(
        self,
        *,
        seal_verified: bool,
        integrity_restored: bool,
        rollback_stable: bool,
        governance_valid: bool,
        constitution_valid: bool,
        protection_state: RuntimeSelfProtectionState | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeUnlockDecision:
        sovereign_locked = not all(
            [
                seal_verified,
                integrity_restored,
                rollback_stable,
                governance_valid,
                constitution_valid,
            ]
        )

        protection_state = protection_state or RuntimeSelfProtectionState()

        if protection_state.mutation_frozen:
            sovereign_locked = True

        evidence = {
            "seal_verified": seal_verified,
            "integrity_restored": integrity_restored,
            "rollback_stable": rollback_stable,
            "governance_valid": governance_valid,
            "constitution_valid": constitution_valid,
            "mutation_frozen": protection_state.mutation_frozen,
            "quarantined_mutations": list(protection_state.quarantined_mutations),
            "metadata": dict(metadata or {}),
        }

        if sovereign_locked:
            return RuntimeUnlockDecision(
                unlock_approved=False,
                sovereign_locked=True,
                reason="runtime unlock denied",
                execution_restored=False,
                evidence=evidence,
            )

        return RuntimeUnlockDecision(
            unlock_approved=True,
            sovereign_locked=False,
            reason="runtime unlock approved",
            execution_restored=True,
            evidence=evidence,
        )

    def enforce_unlock(self, **kwargs: Any) -> RuntimeUnlockDecision:
        decision = self.evaluate_unlock(**kwargs)

        if not decision.unlock_approved:
            raise RuntimeUnlockRejected(decision.reason)

        return decision



@dataclass(frozen=True)
class RuntimeExecutionRestoration:
    restored: bool
    executed: bool
    runtime_resumed: bool
    reason: str
    unlock_decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "restored": self.restored,
            "executed": self.executed,
            "runtime_resumed": self.runtime_resumed,
            "reason": self.reason,
            "unlock_decision": dict(self.unlock_decision),
        }


def restore_runtime_execution(
    *,
    unlock_authority: RuntimeUnlockAuthority,
    seal_verified: bool,
    integrity_restored: bool,
    rollback_stable: bool,
    governance_valid: bool,
    constitution_valid: bool,
    protection_state: RuntimeSelfProtectionState | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeExecutionRestoration:
    decision = unlock_authority.enforce_unlock(
        seal_verified=seal_verified,
        integrity_restored=integrity_restored,
        rollback_stable=rollback_stable,
        governance_valid=governance_valid,
        constitution_valid=constitution_valid,
        protection_state=protection_state,
        metadata=metadata,
    )

    return RuntimeExecutionRestoration(
        restored=True,
        executed=True,
        runtime_resumed=True,
        reason="controlled_runtime_execution_restored",
        unlock_decision=decision.to_dict(),
    )
