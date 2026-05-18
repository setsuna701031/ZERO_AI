"""Runtime execution grant issuer contract.

RuntimeGrantIssuer v0 is the only execution grant creation point. It remains
default-deny and must not import scheduler, enqueue work, execute steps, mutate
state, recover, or replay.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_admission_policy import RuntimeAdmissionPolicyDecision
from core.runtime.runtime_admission_trace import RuntimeAdmissionTrace
from core.runtime.runtime_execution_grant import RuntimeExecutionGrant
from core.runtime.runtime_execution_lease import RuntimeExecutionLease
from core.runtime.runtime_grant_eligibility import RuntimeGrantEligibilityEvaluator


__all__ = ["RuntimeGrantIssuer"]


class RuntimeGrantIssuer:
    """Issue default-deny execution grants for governed runtime admission."""

    issuer_id = "runtime_grant_issuer_v0"

    def __init__(
        self,
        eligibility_evaluator: RuntimeGrantEligibilityEvaluator | None = None,
    ) -> None:
        self.eligibility_evaluator = (
            eligibility_evaluator or RuntimeGrantEligibilityEvaluator()
        )

    def issue_grant(
        self,
        policy_decision: RuntimeAdmissionPolicyDecision,
        admission_trace: RuntimeAdmissionTrace,
        lease: RuntimeExecutionLease,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionGrant:
        """Return a stable not-issued execution grant."""
        eligibility = self.eligibility_evaluator.evaluate(
            policy_decision,
            admission_trace,
            lease,
            metadata=metadata,
        )
        grant_metadata = dict(metadata or {})
        grant_metadata["eligibility"] = {
            "eligible": eligibility.eligible,
            "rule": eligibility.rule,
            "authority_scope": eligibility.authority_scope,
            "risk_level": eligibility.risk_level,
        }

        return RuntimeExecutionGrant(
            grant_id=(
                f"execution_grant:{lease.request_id}"
                if lease.request_id
                else "execution_grant:"
            ),
            request_id=lease.request_id,
            trace_id=admission_trace.trace_id,
            lease_id=lease.lease_id,
            granted=False,
            status="grant_not_issued",
            reason="execution_not_granted",
            authority_scope="none",
            risk_level="unknown",
            granted_by=self.issuer_id,
            expires_at=None,
            metadata=grant_metadata,
        )
