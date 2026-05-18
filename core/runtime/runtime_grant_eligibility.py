"""Runtime grant eligibility contract.

RuntimeGrantEligibility v0 evaluates whether a request is theoretically
eligible for an execution grant. It remains default-deny and must not import
scheduler, enqueue work, execute steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_admission_policy import RuntimeAdmissionPolicyDecision
from core.runtime.runtime_admission_trace import RuntimeAdmissionTrace
from core.runtime.runtime_execution_lease import RuntimeExecutionLease


__all__ = ["RuntimeGrantEligibility", "RuntimeGrantEligibilityEvaluator"]


@dataclass(frozen=True)
class RuntimeGrantEligibility:
    eligible: bool
    rule: str
    reason: str
    authority_scope: str
    risk_level: str
    request_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeGrantEligibilityEvaluator:
    """Evaluate grant eligibility without issuing execution authority."""

    def evaluate(
        self,
        policy_decision: RuntimeAdmissionPolicyDecision,
        admission_trace: RuntimeAdmissionTrace,
        lease: RuntimeExecutionLease,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeGrantEligibility:
        """Return a stable default-deny eligibility result."""
        return RuntimeGrantEligibility(
            eligible=False,
            rule="default_deny",
            reason="execution_not_granted",
            authority_scope="none",
            risk_level="unknown",
            request_id=lease.request_id,
            metadata=dict(metadata or {}),
        )
