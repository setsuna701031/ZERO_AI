"""Runtime admission policy contract.

RuntimeAdmissionPolicy v0 is default-deny and only returns an admission policy
decision. It must not import scheduler, executor, mutation, recovery, or replay
runtime internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


__all__ = ["RuntimeAdmissionPolicy", "RuntimeAdmissionPolicyDecision"]


@dataclass(frozen=True)
class RuntimeAdmissionPolicyDecision:
    allowed: bool
    rule: str
    reason: str
    status: str
    risk_level: str
    authority_scope: str
    request_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAdmissionPolicy:
    """Default-deny admission policy for future governed runtime access."""

    def evaluate(self, request_envelope: Mapping[str, Any]) -> RuntimeAdmissionPolicyDecision:
        request = request_envelope.get("request")
        request_id = ""
        if isinstance(request, Mapping):
            raw_metadata = request.get("metadata")
            if isinstance(raw_metadata, Mapping):
                request_id = str(raw_metadata.get("request_id") or "")

        return RuntimeAdmissionPolicyDecision(
            allowed=False,
            rule="default_deny",
            reason="execution_not_granted",
            status="accepted_not_connected",
            risk_level="unknown",
            authority_scope="none",
            request_id=request_id,
            metadata={},
        )
