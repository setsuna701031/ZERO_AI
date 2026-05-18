"""Runtime execution pending contract.

RuntimeExecutionPendingController v0 can mark accepted controlled enqueue as
pending execution and issue an execution token. It has no executor import,
scheduler import, execution, mutation, recovery, or replay behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_controlled_enqueue import RuntimeControlledEnqueueDecision
from core.runtime.runtime_execution_token import RuntimeExecutionToken


__all__ = [
    "RuntimeExecutionPendingDecision",
    "RuntimeExecutionPendingController",
]


EXECUTION_PENDING_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeExecutionPendingDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    enqueue_id: str
    execution_token_id: str
    authority_scope: str
    risk_level: str
    execution_pending: bool
    enqueued: bool
    scheduler_touched: bool
    executed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeExecutionPendingController:
    """Evaluate execution pending state without executing work."""

    def issue_token(
        self,
        controlled_enqueue: RuntimeControlledEnqueueDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionToken:
        """Issue a token only for accepted non-executing controlled enqueue."""
        execution_pending = (
            controlled_enqueue.accepted
            and controlled_enqueue.authority_scope in EXECUTION_PENDING_ALLOWED_SCOPES
        )
        return RuntimeExecutionToken(
            execution_token_id=(
                f"execution_token:{controlled_enqueue.request_id}"
                if controlled_enqueue.request_id
                else "execution_token:"
            ),
            request_id=controlled_enqueue.request_id,
            trace_id=controlled_enqueue.trace_id,
            lease_id=controlled_enqueue.lease_id,
            grant_id=controlled_enqueue.grant_id,
            queue_admission_id=controlled_enqueue.queue_admission_id,
            enqueue_id=controlled_enqueue.enqueue_id,
            authority_scope=controlled_enqueue.authority_scope,
            risk_level=controlled_enqueue.risk_level,
            execution_pending=execution_pending,
            executed=False,
            revoked=False,
            metadata=dict(metadata or {}),
        )

    def evaluate(
        self,
        controlled_enqueue: RuntimeControlledEnqueueDecision,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionPendingDecision:
        """Return pending execution state without executing."""
        token = self.issue_token(controlled_enqueue, metadata=metadata)

        if not controlled_enqueue.accepted:
            return RuntimeExecutionPendingDecision(
                accepted=False,
                status="execution_pending_rejected",
                reason="controlled_enqueue_not_accepted",
                request_id=controlled_enqueue.request_id,
                trace_id=controlled_enqueue.trace_id,
                lease_id=controlled_enqueue.lease_id,
                grant_id=controlled_enqueue.grant_id,
                enqueue_id=controlled_enqueue.enqueue_id,
                execution_token_id=token.execution_token_id,
                authority_scope=controlled_enqueue.authority_scope,
                risk_level=controlled_enqueue.risk_level,
                execution_pending=False,
                enqueued=controlled_enqueue.enqueued,
                scheduler_touched=controlled_enqueue.scheduler_touched,
                executed=False,
                metadata=dict(metadata or {}),
            )

        if controlled_enqueue.authority_scope not in EXECUTION_PENDING_ALLOWED_SCOPES:
            return RuntimeExecutionPendingDecision(
                accepted=False,
                status="execution_pending_rejected",
                reason="scope_not_allowed_for_execution_pending_v0",
                request_id=controlled_enqueue.request_id,
                trace_id=controlled_enqueue.trace_id,
                lease_id=controlled_enqueue.lease_id,
                grant_id=controlled_enqueue.grant_id,
                enqueue_id=controlled_enqueue.enqueue_id,
                execution_token_id=token.execution_token_id,
                authority_scope=controlled_enqueue.authority_scope,
                risk_level=controlled_enqueue.risk_level,
                execution_pending=False,
                enqueued=controlled_enqueue.enqueued,
                scheduler_touched=controlled_enqueue.scheduler_touched,
                executed=False,
                metadata=dict(metadata or {}),
            )

        return RuntimeExecutionPendingDecision(
            accepted=True,
            status="execution_pending",
            reason="controlled_enqueue_accepted",
            request_id=controlled_enqueue.request_id,
            trace_id=controlled_enqueue.trace_id,
            lease_id=controlled_enqueue.lease_id,
            grant_id=controlled_enqueue.grant_id,
            enqueue_id=controlled_enqueue.enqueue_id,
            execution_token_id=token.execution_token_id,
            authority_scope=controlled_enqueue.authority_scope,
            risk_level=controlled_enqueue.risk_level,
            execution_pending=True,
            enqueued=True,
            scheduler_touched=True,
            executed=False,
            metadata=dict(metadata or {}),
        )
