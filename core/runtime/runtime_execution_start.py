"""Runtime execution start contract.

RuntimeExecutionStartController v0 can mark accepted pending execution as
started for non-executing scopes only. Its ``executed`` flag is a lifecycle
marker, not real task execution. It must not import executor, import scheduler,
run commands, mutate state, recover, replay, or call scheduler enqueue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


__all__ = [
    "RuntimeExecutionStartRequest",
    "RuntimeExecutionStartDecision",
    "RuntimeExecutionStartController",
]


EXECUTION_START_ALLOWED_SCOPES = frozenset({"dry_run", "read_only"})


@dataclass(frozen=True)
class RuntimeExecutionStartRequest:
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    queue_admission_id: str
    enqueue_id: str
    execution_token_id: str
    authority_scope: str
    risk_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeExecutionStartDecision:
    accepted: bool
    status: str
    reason: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    queue_admission_id: str
    enqueue_id: str
    execution_token_id: str
    execution_start_id: str
    authority_scope: str
    risk_level: str
    execution_pending: bool
    enqueued: bool
    scheduler_touched: bool
    executed: bool
    revoked: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeExecutionStartController:
    """Evaluate execution start lifecycle state without running work."""

    def evaluate(
        self,
        request: RuntimeExecutionStartRequest,
        *,
        execution_pending: bool,
        revoked: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionStartDecision:
        """Return execution start state without executor or scheduler behavior."""
        merged_metadata = dict(request.metadata)
        merged_metadata.update(dict(metadata or {}))
        execution_start_id = (
            f"execution_start:{request.request_id}"
            if request.request_id
            else "execution_start:"
        )

        if not execution_pending:
            return RuntimeExecutionStartDecision(
                accepted=False,
                status="execution_start_rejected",
                reason="execution_not_pending",
                request_id=request.request_id,
                trace_id=request.trace_id,
                lease_id=request.lease_id,
                grant_id=request.grant_id,
                queue_admission_id=request.queue_admission_id,
                enqueue_id=request.enqueue_id,
                execution_token_id=request.execution_token_id,
                execution_start_id=execution_start_id,
                authority_scope=request.authority_scope,
                risk_level=request.risk_level,
                execution_pending=False,
                enqueued=True,
                scheduler_touched=True,
                executed=False,
                revoked=revoked,
                metadata=merged_metadata,
            )

        if revoked:
            return RuntimeExecutionStartDecision(
                accepted=False,
                status="execution_start_rejected",
                reason="execution_token_revoked",
                request_id=request.request_id,
                trace_id=request.trace_id,
                lease_id=request.lease_id,
                grant_id=request.grant_id,
                queue_admission_id=request.queue_admission_id,
                enqueue_id=request.enqueue_id,
                execution_token_id=request.execution_token_id,
                execution_start_id=execution_start_id,
                authority_scope=request.authority_scope,
                risk_level=request.risk_level,
                execution_pending=True,
                enqueued=True,
                scheduler_touched=True,
                executed=False,
                revoked=True,
                metadata=merged_metadata,
            )

        if (
            request.authority_scope not in EXECUTION_START_ALLOWED_SCOPES
            or request.risk_level != "low"
        ):
            return RuntimeExecutionStartDecision(
                accepted=False,
                status="execution_start_rejected",
                reason="scope_or_risk_not_allowed_for_execution_start_v0",
                request_id=request.request_id,
                trace_id=request.trace_id,
                lease_id=request.lease_id,
                grant_id=request.grant_id,
                queue_admission_id=request.queue_admission_id,
                enqueue_id=request.enqueue_id,
                execution_token_id=request.execution_token_id,
                execution_start_id=execution_start_id,
                authority_scope=request.authority_scope,
                risk_level=request.risk_level,
                execution_pending=True,
                enqueued=True,
                scheduler_touched=True,
                executed=False,
                revoked=False,
                metadata=merged_metadata,
            )

        return RuntimeExecutionStartDecision(
            accepted=True,
            status="execution_started",
            reason="non_executing_scope_started",
            request_id=request.request_id,
            trace_id=request.trace_id,
            lease_id=request.lease_id,
            grant_id=request.grant_id,
            queue_admission_id=request.queue_admission_id,
            enqueue_id=request.enqueue_id,
            execution_token_id=request.execution_token_id,
            execution_start_id=execution_start_id,
            authority_scope=request.authority_scope,
            risk_level=request.risk_level,
            execution_pending=False,
            enqueued=True,
            scheduler_touched=True,
            executed=True,
            revoked=False,
            metadata=merged_metadata,
        )
