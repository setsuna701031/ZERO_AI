"""Runtime ownership admission gate contract.

RuntimeOwnershipGate v0 only returns an admission decision. It must not import
scheduler, enqueue work, execute steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from core.runtime.runtime_admission_policy import (
    RuntimeAdmissionPolicy,
    RuntimeAdmissionPolicyDecision,
)
from core.runtime.runtime_admission_trace import RuntimeAdmissionTrace
from core.runtime.runtime_execution_grant import RuntimeExecutionGrant
from core.runtime.runtime_execution_lease import RuntimeExecutionLease
from core.runtime.runtime_grant_issuer import RuntimeGrantIssuer


__all__ = ["RuntimeOwnershipDecision", "RuntimeOwnershipGate"]


@dataclass(frozen=True)
class RuntimeOwnershipDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    policy_decision: RuntimeAdmissionPolicyDecision
    lease: RuntimeExecutionLease
    execution_grant: RuntimeExecutionGrant
    admission_trace: RuntimeAdmissionTrace
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeOwnershipGate:
    """Contract-only admission gate for future runtime ownership checks."""

    def __init__(
        self,
        admission_policy: RuntimeAdmissionPolicy | None = None,
        grant_issuer: RuntimeGrantIssuer | None = None,
    ) -> None:
        self.admission_policy = admission_policy or RuntimeAdmissionPolicy()
        self.grant_issuer = grant_issuer or RuntimeGrantIssuer()

    def evaluate_request(self, request_envelope: Mapping[str, Any]) -> RuntimeOwnershipDecision:
        """Return a stable not-connected admission decision."""
        policy_decision = self.admission_policy.evaluate(request_envelope)
        request_id = policy_decision.request_id
        trace_id = f"admission_trace:{request_id}" if request_id else "admission_trace:"
        lease_id = f"execution_lease:{request_id}" if request_id else "execution_lease:"

        admission_trace = RuntimeAdmissionTrace(
            trace_id=trace_id,
            request_id=request_id,
            stage="ownership_gate",
            decision="denied",
            status=policy_decision.status,
            reason=policy_decision.reason,
            policy_rule=policy_decision.rule,
            risk_level=policy_decision.risk_level,
            authority_scope=policy_decision.authority_scope,
            lease_id=lease_id,
            grant_id=None,
            metadata={},
        )
        lease = RuntimeExecutionLease(
            lease_id=lease_id,
            request_id=request_id,
            granted=False,
            trace_id=admission_trace.trace_id,
            status="lease_not_granted",
            reason=policy_decision.reason,
            owner=None,
            metadata={},
        )
        execution_grant = self.grant_issuer.issue_grant(
            policy_decision,
            admission_trace,
            lease,
            metadata={},
        )
        admission_trace = replace(
            admission_trace,
            grant_id=execution_grant.grant_id,
        )

        return RuntimeOwnershipDecision(
            accepted=False,
            status=policy_decision.status,
            reason=policy_decision.reason,
            request_id=request_id,
            policy_decision=policy_decision,
            lease=lease,
            execution_grant=execution_grant,
            admission_trace=admission_trace,
            metadata={},
        )
