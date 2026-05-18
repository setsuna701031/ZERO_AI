"""Runtime scheduler adapter admission contract.

RuntimeSchedulerAdapter v0 only admits accepted bridge decisions to an adapter
ready state. It must not import scheduler, enqueue work, execute steps, mutate
state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

from core.runtime.runtime_execution_bridge import RuntimeExecutionBridgeDecision

if TYPE_CHECKING:
    from core.runtime.runtime_controlled_enqueue import RuntimeControlledEnqueueDecision
    from core.runtime.runtime_queue_admission import RuntimeQueueAdmissionDecision


__all__ = ["RuntimeSchedulerAdapterDecision", "RuntimeSchedulerAdapter"]


ADAPTER_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeSchedulerAdapterDecision:
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


class RuntimeSchedulerAdapter:
    """Evaluate adapter readiness without scheduler handoff."""

    def evaluate_bridge_decision(
        self,
        bridge_decision: RuntimeExecutionBridgeDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeSchedulerAdapterDecision:
        """Return adapter admission without enqueueing or executing."""
        if (
            bridge_decision.accepted
            and bridge_decision.status == "bridge_accepted"
            and bridge_decision.authority_scope in ADAPTER_ALLOWED_SCOPES
        ):
            return RuntimeSchedulerAdapterDecision(
                accepted=True,
                status="adapter_ready",
                reason="bridge_accepted_for_non_executing_scope",
                request_id=bridge_decision.request_id,
                trace_id=bridge_decision.trace_id,
                lease_id=bridge_decision.lease_id,
                grant_id=bridge_decision.grant_id,
                authority_scope=bridge_decision.authority_scope,
                risk_level=bridge_decision.risk_level,
                metadata=dict(metadata or {}),
            )

        return RuntimeSchedulerAdapterDecision(
            accepted=False,
            status="adapter_rejected",
            reason="bridge_not_accepted_for_adapter_v0",
            request_id=bridge_decision.request_id,
            trace_id=bridge_decision.trace_id,
            lease_id=bridge_decision.lease_id,
            grant_id=bridge_decision.grant_id,
            authority_scope=bridge_decision.authority_scope,
            risk_level=bridge_decision.risk_level,
            metadata=dict(metadata or {}),
        )

    def evaluate_queue_admission(
        self,
        adapter_decision: RuntimeSchedulerAdapterDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RuntimeQueueAdmissionDecision":
        """Expose queue admission without enqueueing or executing."""
        from core.runtime.runtime_queue_admission import RuntimeQueueAdmissionController

        return RuntimeQueueAdmissionController().evaluate(
            adapter_decision,
            metadata=metadata,
        )

    def evaluate_controlled_enqueue(
        self,
        queue_admission: "RuntimeQueueAdmissionDecision",
        metadata: Mapping[str, Any] | None = None,
    ) -> "RuntimeControlledEnqueueDecision":
        """Expose controlled queue placeholder admission without running work."""
        from core.runtime.runtime_controlled_enqueue import (
            RuntimeControlledEnqueueController,
        )

        return RuntimeControlledEnqueueController().evaluate(
            queue_admission,
            metadata=metadata,
        )
