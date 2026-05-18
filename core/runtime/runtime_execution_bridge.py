"""Runtime execution bridge contract.

RuntimeExecutionBridge v0 admits granted execution authority into the bridge
only. It must not import scheduler, enqueue work, execute steps, mutate state,
recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_execution_grant import RuntimeExecutionGrant


__all__ = ["RuntimeExecutionBridgeDecision", "RuntimeExecutionBridge"]


BRIDGE_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeExecutionBridgeDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    authority_scope: str
    risk_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeExecutionBridge:
    """Evaluate whether a grant can enter future bridge handoff."""

    def evaluate_handoff(
        self,
        execution_grant: RuntimeExecutionGrant,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionBridgeDecision:
        """Return bridge admission without scheduler handoff."""
        if not execution_grant.granted:
            return RuntimeExecutionBridgeDecision(
                accepted=False,
                status="bridge_rejected",
                reason="grant_not_issued",
                request_id=execution_grant.request_id,
                trace_id=execution_grant.trace_id,
                lease_id=execution_grant.lease_id,
                grant_id=execution_grant.grant_id,
                authority_scope=execution_grant.authority_scope,
                risk_level=execution_grant.risk_level,
                metadata=dict(metadata or {}),
            )

        if execution_grant.authority_scope not in BRIDGE_ALLOWED_SCOPES:
            return RuntimeExecutionBridgeDecision(
                accepted=False,
                status="bridge_rejected",
                reason="scope_not_allowed_for_bridge_v0",
                request_id=execution_grant.request_id,
                trace_id=execution_grant.trace_id,
                lease_id=execution_grant.lease_id,
                grant_id=execution_grant.grant_id,
                authority_scope=execution_grant.authority_scope,
                risk_level=execution_grant.risk_level,
                metadata=dict(metadata or {}),
            )

        return RuntimeExecutionBridgeDecision(
            accepted=True,
            status="bridge_accepted",
            reason="grant_accepted_for_non_executing_scope",
            request_id=execution_grant.request_id,
            trace_id=execution_grant.trace_id,
            lease_id=execution_grant.lease_id,
            grant_id=execution_grant.grant_id,
            authority_scope=execution_grant.authority_scope,
            risk_level=execution_grant.risk_level,
            metadata=dict(metadata or {}),
        )
