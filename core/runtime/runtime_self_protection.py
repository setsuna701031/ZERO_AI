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
]
