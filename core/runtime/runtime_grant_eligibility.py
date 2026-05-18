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


LOW_RISK_SCOPES = frozenset({"dry_run", "read_only"})


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

    def _authority_scope_from_metadata(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> str:
        if not metadata:
            return "none"

        direct_scope = metadata.get("authority_scope")
        if isinstance(direct_scope, str):
            return direct_scope

        request = metadata.get("request")
        if not isinstance(request, Mapping):
            return "none"

        request_scope = request.get("authority_scope")
        if isinstance(request_scope, str):
            return request_scope

        request_metadata = request.get("metadata")
        if isinstance(request_metadata, Mapping):
            nested_scope = request_metadata.get("authority_scope")
            if isinstance(nested_scope, str):
                return nested_scope

        return "none"

    def evaluate(
        self,
        policy_decision: RuntimeAdmissionPolicyDecision,
        admission_trace: RuntimeAdmissionTrace,
        lease: RuntimeExecutionLease,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeGrantEligibility:
        """Return eligibility for non-executing scopes only."""
        requested_scope = self._authority_scope_from_metadata(metadata)
        if requested_scope in LOW_RISK_SCOPES:
            return RuntimeGrantEligibility(
                eligible=True,
                rule="scoped_low_risk",
                reason="eligible_for_non_executing_scope",
                authority_scope=requested_scope,
                risk_level="low",
                request_id=lease.request_id,
                metadata=dict(metadata or {}),
            )

        return RuntimeGrantEligibility(
            eligible=False,
            rule="default_deny",
            reason="execution_not_granted",
            authority_scope="none",
            risk_level="unknown",
            request_id=lease.request_id,
            metadata=dict(metadata or {}),
        )
