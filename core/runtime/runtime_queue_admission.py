"""Runtime queue admission contract.

RuntimeQueueAdmissionController v0 admits adapter-ready decisions to a queue
admission record only. It must not import scheduler, enqueue work, execute
steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_scheduler_adapter import RuntimeSchedulerAdapterDecision


__all__ = ["RuntimeQueueAdmissionDecision", "RuntimeQueueAdmissionController"]


QUEUE_ADMISSION_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeQueueAdmissionDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    authority_scope: str
    risk_level: str
    adapter_status: str
    queue_admission_id: str
    enqueued: bool
    executed: bool
    scheduler_touched: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeQueueAdmissionController:
    """Evaluate queue admission without queue mutation."""

    def evaluate(
        self,
        adapter_decision: RuntimeSchedulerAdapterDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeQueueAdmissionDecision:
        """Return queue admission without enqueueing or executing."""
        queue_admission_id = (
            f"queue_admission:{adapter_decision.request_id}"
            if adapter_decision.request_id
            else "queue_admission:"
        )

        if not adapter_decision.accepted:
            return RuntimeQueueAdmissionDecision(
                accepted=False,
                status="queue_admission_rejected",
                reason="adapter_not_ready",
                request_id=adapter_decision.request_id,
                trace_id=adapter_decision.trace_id,
                lease_id=adapter_decision.lease_id,
                grant_id=adapter_decision.grant_id,
                authority_scope=adapter_decision.authority_scope,
                risk_level=adapter_decision.risk_level,
                adapter_status=adapter_decision.status,
                queue_admission_id=queue_admission_id,
                enqueued=False,
                executed=False,
                scheduler_touched=False,
                metadata=dict(metadata or {}),
            )

        if adapter_decision.authority_scope not in QUEUE_ADMISSION_ALLOWED_SCOPES:
            return RuntimeQueueAdmissionDecision(
                accepted=False,
                status="queue_admission_rejected",
                reason="scope_not_allowed_for_queue_admission_v0",
                request_id=adapter_decision.request_id,
                trace_id=adapter_decision.trace_id,
                lease_id=adapter_decision.lease_id,
                grant_id=adapter_decision.grant_id,
                authority_scope=adapter_decision.authority_scope,
                risk_level=adapter_decision.risk_level,
                adapter_status=adapter_decision.status,
                queue_admission_id=queue_admission_id,
                enqueued=False,
                executed=False,
                scheduler_touched=False,
                metadata=dict(metadata or {}),
            )

        return RuntimeQueueAdmissionDecision(
            accepted=True,
            status="queue_admission_accepted",
            reason="adapter_ready_for_non_executing_scope",
            request_id=adapter_decision.request_id,
            trace_id=adapter_decision.trace_id,
            lease_id=adapter_decision.lease_id,
            grant_id=adapter_decision.grant_id,
            authority_scope=adapter_decision.authority_scope,
            risk_level=adapter_decision.risk_level,
            adapter_status=adapter_decision.status,
            queue_admission_id=queue_admission_id,
            enqueued=False,
            executed=False,
            scheduler_touched=False,
            metadata=dict(metadata or {}),
        )
