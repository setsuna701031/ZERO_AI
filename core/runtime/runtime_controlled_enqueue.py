"""Runtime controlled enqueue contract.

RuntimeControlledEnqueueController v0 can mark a non-executing queue
placeholder as enqueued. It must not import scheduler, call scheduler enqueue,
execute steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_queue_admission import RuntimeQueueAdmissionDecision


__all__ = [
    "RuntimeControlledEnqueueRequest",
    "RuntimeControlledEnqueueDecision",
    "RuntimeControlledEnqueueController",
]


CONTROLLED_ENQUEUE_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeControlledEnqueueRequest:
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    queue_admission_id: str
    authority_scope: str
    risk_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeControlledEnqueueDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    queue_admission_id: str
    enqueue_id: str
    authority_scope: str
    risk_level: str
    enqueued: bool
    executed: bool
    scheduler_touched: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeControlledEnqueueController:
    """Evaluate controlled queue placeholder admission."""

    def evaluate(
        self,
        queue_admission: RuntimeQueueAdmissionDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeControlledEnqueueDecision:
        """Return a controlled enqueue decision without running work."""
        enqueue_id = (
            f"controlled_enqueue:{queue_admission.request_id}"
            if queue_admission.request_id
            else "controlled_enqueue:"
        )

        if not queue_admission.accepted:
            return RuntimeControlledEnqueueDecision(
                accepted=False,
                status="controlled_enqueue_rejected",
                reason="queue_admission_not_accepted",
                request_id=queue_admission.request_id,
                trace_id=queue_admission.trace_id,
                lease_id=queue_admission.lease_id,
                grant_id=queue_admission.grant_id,
                queue_admission_id=queue_admission.queue_admission_id,
                enqueue_id=enqueue_id,
                authority_scope=queue_admission.authority_scope,
                risk_level=queue_admission.risk_level,
                enqueued=False,
                executed=False,
                scheduler_touched=False,
                metadata=dict(metadata or {}),
            )

        if queue_admission.authority_scope not in CONTROLLED_ENQUEUE_ALLOWED_SCOPES:
            return RuntimeControlledEnqueueDecision(
                accepted=False,
                status="controlled_enqueue_rejected",
                reason="scope_not_allowed_for_controlled_enqueue_v0",
                request_id=queue_admission.request_id,
                trace_id=queue_admission.trace_id,
                lease_id=queue_admission.lease_id,
                grant_id=queue_admission.grant_id,
                queue_admission_id=queue_admission.queue_admission_id,
                enqueue_id=enqueue_id,
                authority_scope=queue_admission.authority_scope,
                risk_level=queue_admission.risk_level,
                enqueued=False,
                executed=False,
                scheduler_touched=False,
                metadata=dict(metadata or {}),
            )

        return RuntimeControlledEnqueueDecision(
            accepted=True,
            status="controlled_enqueue_accepted",
            reason="queue_admission_accepted_for_non_executing_scope",
            request_id=queue_admission.request_id,
            trace_id=queue_admission.trace_id,
            lease_id=queue_admission.lease_id,
            grant_id=queue_admission.grant_id,
            queue_admission_id=queue_admission.queue_admission_id,
            enqueue_id=enqueue_id,
            authority_scope=queue_admission.authority_scope,
            risk_level=queue_admission.risk_level,
            enqueued=True,
            executed=False,
            scheduler_touched=True,
            metadata=dict(metadata or {}),
        )
