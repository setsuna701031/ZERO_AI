from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.goals.goal_lineage_contract import extract_runtime_identity
from core.runtime.runtime_recovery_queue import (
    RECOVERY_TICKET_STATUS_COMPLETED,
    RECOVERY_TICKET_STATUS_ESCALATED,
    RuntimeRecoveryQueue,
    RuntimeRecoveryTicket,
)
from core.runtime.runtime_recovery_lineage import RuntimeRecoveryLineage
from core.runtime.runtime_recovery_supervisor import RuntimeRecoverySupervisor


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_orchestrator_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeRecoveryBackoffPolicy:
    base_delay_ticks: int = 1
    multiplier: int = 2
    max_delay_ticks: int = 60

    def delay_for_attempt(self, attempt: int) -> int:
        attempt = max(1, int(attempt))
        delay = self.base_delay_ticks * (self.multiplier ** max(0, attempt - 1))
        return max(0, min(int(delay), int(self.max_delay_ticks)))


@dataclass(frozen=True)
class RuntimeRecoveryCooldownPolicy:
    cooldown_ticks: int = 0

    def next_allowed_tick(self, current_tick: int) -> int:
        return int(current_tick) + max(0, int(self.cooldown_ticks))


@dataclass(frozen=True)
class RuntimeRecoveryOrchestratorResult:
    ok: bool
    status: str
    ticket: dict[str, Any] = field(default_factory=dict)
    recovery_result: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    supervisor_handoff: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "ticket": copy.deepcopy(self.ticket),
            "recovery_result": copy.deepcopy(self.recovery_result),
            "lineage": copy.deepcopy(self.lineage),
            "supervisor_handoff": copy.deepcopy(self.supervisor_handoff),
            "audit_events": copy.deepcopy(self.audit_events),
            "message": self.message,
        }


class RuntimeRecoveryOrchestratorRejected(RuntimeError):
    def __init__(self, message: str, original_exception: BaseException | None = None) -> None:
        self.original_exception = original_exception
        super().__init__(message)


RecoveryRunner = Callable[[dict[str, Any]], Any]


class RuntimeRecoveryOrchestrator:
    """
    Runtime recovery lifecycle controller.

    Responsibilities:
    - convert incidents into recovery tickets
    - consume ready recovery tickets
    - call coordinator/executor without owning their internals
    - enforce bounded retry through queue attempts
    - apply backoff/cooldown
    - write audit/journal events when adapters are provided
    - connect recovery lineage
    - escalate exhausted/blocked recovery to supervisor

    Non-responsibilities:
    - no Scheduler branching
    - no StepExecutor handler logic
    - no TaskRuntime state-machine ownership
    """

    def __init__(
        self,
        *,
        queue: RuntimeRecoveryQueue | None = None,
        lineage: RuntimeRecoveryLineage | None = None,
        supervisor: RuntimeRecoverySupervisor | None = None,
        recovery_coordinator: Any = None,
        recovery_executor: Any = None,
        audit: Any = None,
        journal: Any = None,
        runner: RecoveryRunner | None = None,
        backoff_policy: RuntimeRecoveryBackoffPolicy | None = None,
        cooldown_policy: RuntimeRecoveryCooldownPolicy | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.queue = queue if queue is not None else RuntimeRecoveryQueue()
        self.lineage = lineage if lineage is not None else RuntimeRecoveryLineage()
        self.supervisor = supervisor if supervisor is not None else RuntimeRecoverySupervisor()
        self.recovery_coordinator = recovery_coordinator
        self.recovery_executor = recovery_executor
        self.audit = audit
        self.journal = journal
        self.runner = runner
        self.backoff_policy = backoff_policy if backoff_policy is not None else RuntimeRecoveryBackoffPolicy()
        self.cooldown_policy = cooldown_policy if cooldown_policy is not None else RuntimeRecoveryCooldownPolicy()
        self.max_attempts = max(1, int(max_attempts))

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeRecoveryOrchestrator":
        root = Path(workspace_root)
        recovery_dir = root / "runtime_recovery"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            queue=RuntimeRecoveryQueue(recovery_dir / "recovery_queue.json"),
            lineage=RuntimeRecoveryLineage(recovery_dir / "recovery_lineage.json"),
            supervisor=RuntimeRecoverySupervisor(recovery_dir / "recovery_supervisor.json"),
            **kwargs,
        )

    def submit_incident(
        self,
        incident: dict[str, Any],
        *,
        current_tick: int = 0,
        priority: int = 100,
        max_attempts: int | None = None,
    ) -> RuntimeRecoveryTicket:
        if not isinstance(incident, dict):
            raise RuntimeRecoveryOrchestratorRejected("runtime_recovery_incident_must_be_dict")

        incident_id = str(
            incident.get("incident_id")
            or incident.get("id")
            or incident.get("task_id")
            or "runtime-global"
        )
        runtime_identity = extract_runtime_identity(incident, reject_conflicts=True)
        source_session_id = str(runtime_identity.get("source_session_id") or "")
        task_id = str(incident.get("task_id") or "")
        recovery_id = str(incident.get("recovery_id") or "").strip()
        if not recovery_id:
            recovery_id = "runtime-recovery-" + stable_recovery_orchestrator_fingerprint(
                {
                    "incident_id": incident_id,
                    "source_session_id": source_session_id,
                    "task_id": task_id,
                    "root_event": incident.get("root_event"),
                    "latest_event": incident.get("latest_event"),
                }
            )[:16]

        ticket = self.queue.enqueue(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            incident_id=incident_id,
            task_id=task_id,
            payload={"incident": copy.deepcopy(incident)},
            metadata={"submitted_by": "runtime_recovery_orchestrator"},
            priority=priority,
            max_attempts=max_attempts if max_attempts is not None else self.max_attempts,
            current_tick=current_tick,
        )

        self.lineage.link_recovery_chain(
            source_session_id=source_session_id,
            incident_id=incident_id,
            ticket_id=ticket.ticket_id,
            recovery_id=recovery_id,
            metadata={"current_tick": current_tick},
        )
        self._record_event(
            event_type="runtime_recovery_ticket_queued",
            payload={"ticket": ticket.to_dict()},
        )
        return ticket

    def consume_ready(
        self,
        *,
        current_tick: int = 0,
        limit: int = 1,
    ) -> list[RuntimeRecoveryOrchestratorResult]:
        results: list[RuntimeRecoveryOrchestratorResult] = []
        ready = self.queue.peek_ready(current_tick=current_tick, limit=limit)
        for ticket in ready:
            results.append(self.run_ticket(ticket.ticket_id, current_tick=current_tick))
        return results

    def run_ticket(
        self,
        ticket_id: str,
        *,
        current_tick: int = 0,
    ) -> RuntimeRecoveryOrchestratorResult:
        audit_events: list[dict[str, Any]] = []
        running_ticket = self.queue.mark_running(ticket_id, current_tick=current_tick)
        self._append_event(
            audit_events,
            event_type="runtime_recovery_ticket_started",
            payload={"ticket": running_ticket.to_dict()},
        )

        try:
            recovery_result = self._run_recovery_for_ticket(running_ticket)
        except Exception as exc:
            next_tick = self._next_retry_tick(running_ticket, current_tick)
            failed_ticket = self.queue.mark_failed(
                ticket_id,
                current_tick=current_tick,
                error={"type": type(exc).__name__, "message": str(exc)},
                next_run_tick=next_tick,
            )
            self._append_event(
                audit_events,
                event_type="runtime_recovery_ticket_failed",
                payload={
                    "ticket": failed_ticket.to_dict(),
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "next_run_tick": next_tick,
                },
            )
            if failed_ticket.status == RECOVERY_TICKET_STATUS_ESCALATED:
                return self._escalate_ticket(
                    failed_ticket,
                    current_tick=current_tick,
                    reason="recovery retry depth exhausted",
                    audit_events=audit_events,
                )
            self._flush_events(audit_events)
            return RuntimeRecoveryOrchestratorResult(
                ok=False,
                status=failed_ticket.status,
                ticket=failed_ticket.to_dict(),
                audit_events=audit_events,
                message=str(exc),
            )

        normalized_result = self._normalize_result(recovery_result)
        ok = bool(normalized_result.get("ok", True))
        blocked = bool(normalized_result.get("blocked", False))
        failed = bool(normalized_result.get("failed", False))
        requires_review = bool(normalized_result.get("requires_review", False) or normalized_result.get("review_required", False))
        replay_id = str(
            normalized_result.get("replay_id")
            or normalized_result.get("runtime_replay_id")
            or normalized_result.get("recovery_replay_id")
            or ""
        )
        execution_id = str(
            normalized_result.get("execution_id")
            or normalized_result.get("recovery_execution_id")
            or normalized_result.get("id")
            or ""
        )

        lineage_payload = self.lineage.link_recovery_chain(
            source_session_id=running_ticket.source_session_id,
            incident_id=running_ticket.incident_id,
            ticket_id=running_ticket.ticket_id,
            recovery_id=running_ticket.recovery_id,
            execution_id=execution_id,
            replay_id=replay_id,
            metadata={"current_tick": current_tick},
        )

        if blocked or requires_review:
            self._append_event(
                audit_events,
                event_type="runtime_recovery_ticket_blocked",
                payload={"result": normalized_result},
            )
            escalated = self.queue.mark_escalated(
                ticket_id,
                current_tick=current_tick,
                reason="recovery requires supervisor review",
            )
            return self._escalate_ticket(
                escalated,
                current_tick=current_tick,
                reason="recovery requires supervisor review",
                audit_events=audit_events,
                lineage_payload=lineage_payload,
                recovery_result=normalized_result,
            )

        if failed or not ok:
            next_tick = self._next_retry_tick(running_ticket, current_tick)
            failed_ticket = self.queue.mark_failed(
                ticket_id,
                current_tick=current_tick,
                error=normalized_result,
                next_run_tick=next_tick,
            )
            self._append_event(
                audit_events,
                event_type="runtime_recovery_attempt_failed",
                payload={"ticket": failed_ticket.to_dict(), "result": normalized_result},
            )
            if failed_ticket.status == RECOVERY_TICKET_STATUS_ESCALATED:
                return self._escalate_ticket(
                    failed_ticket,
                    current_tick=current_tick,
                    reason="recovery retry depth exhausted",
                    audit_events=audit_events,
                    lineage_payload=lineage_payload,
                    recovery_result=normalized_result,
                )
            self._flush_events(audit_events)
            return RuntimeRecoveryOrchestratorResult(
                ok=False,
                status=failed_ticket.status,
                ticket=failed_ticket.to_dict(),
                recovery_result=normalized_result,
                lineage=lineage_payload,
                audit_events=audit_events,
                message="runtime recovery attempt failed; retry scheduled",
            )

        completed_ticket = self.queue.mark_completed(
            ticket_id,
            current_tick=current_tick,
            result=normalized_result,
        )
        self._append_event(
            audit_events,
            event_type="runtime_recovery_ticket_completed",
            payload={"ticket": completed_ticket.to_dict(), "result": normalized_result},
        )
        self._flush_events(audit_events)
        return RuntimeRecoveryOrchestratorResult(
            ok=True,
            status=RECOVERY_TICKET_STATUS_COMPLETED,
            ticket=completed_ticket.to_dict(),
            recovery_result=normalized_result,
            lineage=lineage_payload,
            audit_events=audit_events,
            message="runtime recovery completed",
        )

    def _run_recovery_for_ticket(self, ticket: RuntimeRecoveryTicket) -> Any:
        payload = {
            "ticket": ticket.to_dict(),
            "recovery_id": ticket.recovery_id,
            "source_session_id": ticket.source_session_id,
            "incident_id": ticket.incident_id,
            "task_id": ticket.task_id,
            "payload": copy.deepcopy(ticket.payload),
            "metadata": copy.deepcopy(ticket.metadata),
        }

        if self.runner is not None:
            return self.runner(payload)

        plan = None
        if self.recovery_coordinator is not None:
            if hasattr(self.recovery_coordinator, "create_recovery"):
                try:
                    plan = self.recovery_coordinator.create_recovery(
                        recovery_id=ticket.recovery_id,
                        source_session_id=ticket.source_session_id,
                        payload=copy.deepcopy(ticket.payload),
                        metadata=copy.deepcopy(ticket.metadata),
                    )
                except Exception as exc:
                    if "already exists" not in str(exc):
                        raise
            if hasattr(self.recovery_coordinator, "run_recovery"):
                return self.recovery_coordinator.run_recovery(ticket.recovery_id)

        if self.recovery_executor is not None and hasattr(self.recovery_executor, "execute_recovery"):
            chain = plan if plan is not None else payload
            return self.recovery_executor.execute_recovery(chain, metadata={"ticket": ticket.to_dict()})

        return {
            "ok": True,
            "status": "completed",
            "recovery_id": ticket.recovery_id,
            "message": "runtime recovery dry-run completed",
        }

    def _escalate_ticket(
        self,
        ticket: RuntimeRecoveryTicket,
        *,
        current_tick: int,
        reason: str,
        audit_events: list[dict[str, Any]],
        lineage_payload: dict[str, Any] | None = None,
        recovery_result: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryOrchestratorResult:
        handoff = self.supervisor.escalate(
            recovery_id=ticket.recovery_id,
            ticket_id=ticket.ticket_id,
            source_session_id=ticket.source_session_id,
            incident_id=ticket.incident_id,
            task_id=ticket.task_id,
            reason=reason,
            payload={
                "ticket": ticket.to_dict(),
                "recovery_result": copy.deepcopy(recovery_result or {}),
            },
            metadata={"current_tick": current_tick},
        )
        escalated_ticket = self.queue.mark_escalated(
            ticket.ticket_id,
            current_tick=current_tick,
            reason=reason,
            handoff=handoff.to_dict(),
        )
        lineage = self.lineage.link_recovery_chain(
            source_session_id=escalated_ticket.source_session_id,
            incident_id=escalated_ticket.incident_id,
            ticket_id=escalated_ticket.ticket_id,
            recovery_id=escalated_ticket.recovery_id,
            escalation_id=handoff.handoff_id,
            metadata={"current_tick": current_tick, "reason": reason},
        )
        if lineage_payload:
            lineage["previous_lineage"] = copy.deepcopy(lineage_payload)

        self._append_event(
            audit_events,
            event_type="runtime_recovery_supervisor_handoff_created",
            payload={"ticket": escalated_ticket.to_dict(), "handoff": handoff.to_dict(), "reason": reason},
        )
        self._flush_events(audit_events)
        return RuntimeRecoveryOrchestratorResult(
            ok=False,
            status=RECOVERY_TICKET_STATUS_ESCALATED,
            ticket=escalated_ticket.to_dict(),
            recovery_result=copy.deepcopy(recovery_result or {}),
            lineage=lineage,
            supervisor_handoff=handoff.to_dict(),
            audit_events=audit_events,
            message=reason,
        )

    def _next_retry_tick(self, ticket: RuntimeRecoveryTicket, current_tick: int) -> int:
        backoff_tick = int(current_tick) + self.backoff_policy.delay_for_attempt(ticket.attempt)
        cooldown_tick = self.cooldown_policy.next_allowed_tick(current_tick)
        return max(backoff_tick, cooldown_tick)

    def _normalize_result(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "to_dict") and callable(value.to_dict):
            converted = value.to_dict()
            return copy.deepcopy(converted if isinstance(converted, dict) else {"ok": True, "result": converted})
        if hasattr(value, "__dict__") and not isinstance(value, dict):
            return copy.deepcopy(dict(value.__dict__))
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return {"ok": True, "result": copy.deepcopy(value)}

    def _append_event(
        self,
        events: list[dict[str, Any]],
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        events.append(
            {
                "event_type": event_type,
                "payload": copy.deepcopy(payload),
                "timestamp": utc_timestamp(),
                "source": "runtime_recovery_orchestrator",
            }
        )

    def _record_event(self, *, event_type: str, payload: dict[str, Any]) -> None:
        self._flush_events(
            [
                {
                    "event_type": event_type,
                    "payload": copy.deepcopy(payload),
                    "timestamp": utc_timestamp(),
                    "source": "runtime_recovery_orchestrator",
                }
            ]
        )

    def _flush_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            if self.audit is not None:
                try:
                    if hasattr(self.audit, "append"):
                        self.audit.append(event)
                    elif hasattr(self.audit, "record_event"):
                        self.audit.record_event(event)
                except Exception:
                    pass

            if self.journal is not None:
                try:
                    if hasattr(self.journal, "append"):
                        self.journal.append(event)
                    elif hasattr(self.journal, "append_record"):
                        self.journal.append_record("runtime_recovery_orchestrator", event)
                    elif hasattr(self.journal, "record"):
                        self.journal.record(event)
                except Exception:
                    pass
