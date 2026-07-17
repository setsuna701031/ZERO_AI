from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlan, utc_timestamp


@dataclass(frozen=True)
class RuntimeRecoveryVerificationResult:
    verified: bool
    status: str
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    verified_at: str = field(default_factory=utc_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "status": self.status,
            "reason": self.reason,
            "checks": dict(self.checks),
            "findings": list(self.findings),
            "verified_at": self.verified_at,
            "metadata": copy.deepcopy(self.metadata),
        }


def verify_runtime_recovery_chain(
    *,
    recovery_id: str,
    plan: RuntimeRecoveryPlan | dict[str, Any],
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    audit_events: list[dict[str, Any]] | None = None,
    incident_summary: dict[str, Any] | None = None,
    source_state_before: dict[str, Any] | None = None,
    source_state_after: dict[str, Any] | None = None,
) -> RuntimeRecoveryVerificationResult:
    plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else copy.deepcopy(plan if isinstance(plan, dict) else {})
    source_failure = plan_dict.get("source_failure") if isinstance(plan_dict.get("source_failure"), dict) else {}
    replay_ref = copy.deepcopy(replay_reference or plan_dict.get("replay_reference") or {})
    rollback_ref = copy.deepcopy(rollback_reference or plan_dict.get("rollback_reference") or {})
    events = [copy.deepcopy(item) for item in (audit_events or []) if isinstance(item, dict)]
    incident = copy.deepcopy(incident_summary or {})

    checks = {
        "recovery_id_present": bool(str(recovery_id or plan_dict.get("recovery_id") or "").strip()),
        "source_failure_present": bool(source_failure),
        "recovery_plan_present": bool(plan_dict.get("plan_id")),
        "replay_reference_present": bool(replay_ref) if bool(plan_dict.get("replay_required", True)) else True,
        "rollback_represented": bool(rollback_ref) if bool(plan_dict.get("rollback_required", False)) else True,
        "incident_summary_present": bool(incident),
        "audit_events_present": bool(events),
        "source_state_not_mutated": True,
    }

    if source_state_before is not None and source_state_after is not None:
        checks["source_state_not_mutated"] = source_state_before == source_state_after

    findings = [name for name, ok in checks.items() if not ok]
    plan_status = str(plan_dict.get("status") or "planned").strip().lower()

    if plan_status == "unrecoverable":
        status = "unrecoverable"
        verified = checks["recovery_id_present"] and checks["source_failure_present"] and checks["audit_events_present"]
        reason = "recovery is intentionally blocked by policy" if verified else "unrecoverable chain missing required evidence"
    elif bool(plan_dict.get("rollback_required", False)):
        status = "rollback_required" if checks["rollback_represented"] else "verification_failed"
        verified = checks["recovery_id_present"] and checks["source_failure_present"] and checks["recovery_plan_present"] and checks["rollback_represented"] and checks["audit_events_present"] and checks["source_state_not_mutated"]
        reason = "rollback is required before recovery continuation" if verified else "rollback recovery chain missing required evidence"
    else:
        verified = all(checks.values())
        status = "verified" if verified else "verification_failed"
        reason = "runtime recovery chain verified" if verified else "runtime recovery chain failed verification"

    return RuntimeRecoveryVerificationResult(
        verified=bool(verified),
        status=status,
        reason=reason,
        checks=checks,
        findings=findings,
        metadata={
            "recovery_id": str(recovery_id or plan_dict.get("recovery_id") or ""),
            "plan_status": plan_status,
        },
    )


__all__ = ["RuntimeRecoveryVerificationResult", "verify_runtime_recovery_chain"]
