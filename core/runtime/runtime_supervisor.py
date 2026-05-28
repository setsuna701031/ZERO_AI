from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPERVISOR_SEVERITY_INFO = "info"
SUPERVISOR_SEVERITY_WARNING = "warning"
SUPERVISOR_SEVERITY_ERROR = "error"
SUPERVISOR_SEVERITY_CRITICAL = "critical"

SUPERVISOR_DECISION_RECOVER = "recover"
SUPERVISOR_DECISION_ESCALATE = "escalate"
SUPERVISOR_DECISION_TAKEOVER = "takeover"
SUPERVISOR_DECISION_FREEZE = "freeze"
SUPERVISOR_DECISION_ISOLATE = "isolate"
SUPERVISOR_DECISION_IGNORE = "ignore"

SUPERVISOR_CASE_STATUS_OPEN = "open"
SUPERVISOR_CASE_STATUS_RECOVERY_QUEUED = "recovery_queued"
SUPERVISOR_CASE_STATUS_TAKEOVER_COMPLETED = "takeover_completed"
SUPERVISOR_CASE_STATUS_FROZEN = "frozen"
SUPERVISOR_CASE_STATUS_ISOLATED = "isolated"
SUPERVISOR_CASE_STATUS_ESCALATED = "escalated"
SUPERVISOR_CASE_STATUS_IGNORED = "ignored"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_supervisor_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class RuntimeSupervisorPolicy:
    """
    Declarative supervisor policy.

    critical_incident_types:
      decision = freeze + escalate

    takeover_incident_types:
      decision = takeover

    recoverable_incident_types:
      decision = recover

    ignored_incident_types:
      decision = ignore
    """

    critical_incident_types: set[str] = field(default_factory=lambda: {
        "runtime_integrity_mismatch",
        "runtime_freeze_required",
        "unsafe_action_blocked",
        "policy_blocked",
    })
    takeover_incident_types: set[str] = field(default_factory=lambda: {
        "runtime_session_zombie",
        "runtime_session_dead",
        "runtime_session_ownership_mismatch",
    })
    recoverable_incident_types: set[str] = field(default_factory=lambda: {
        "runtime_session_stalled",
        "runtime_session_lease_expired",
        "runtime_session_frozen",
        "runtime_watchdog_failure",
    })
    ignored_incident_types: set[str] = field(default_factory=set)
    auto_recover: bool = True
    auto_takeover: bool = True
    auto_freeze_critical: bool = True
    supervisor_owner_id: str = "runtime-supervisor"

    def classify(self, incident: dict[str, Any]) -> dict[str, Any]:
        incident_type = str(incident.get("incident_type") or incident.get("type") or "").strip()
        if not incident_type:
            incident_type = "runtime_unknown_incident"

        if incident_type in self.ignored_incident_types:
            return {
                "severity": SUPERVISOR_SEVERITY_INFO,
                "decision": SUPERVISOR_DECISION_IGNORE,
                "reason": "incident type ignored by supervisor policy",
            }

        if incident_type in self.critical_incident_types:
            return {
                "severity": SUPERVISOR_SEVERITY_CRITICAL,
                "decision": SUPERVISOR_DECISION_FREEZE if self.auto_freeze_critical else SUPERVISOR_DECISION_ESCALATE,
                "reason": "critical incident requires runtime freeze/escalation",
            }

        if incident_type in self.takeover_incident_types:
            return {
                "severity": SUPERVISOR_SEVERITY_ERROR,
                "decision": SUPERVISOR_DECISION_TAKEOVER if self.auto_takeover else SUPERVISOR_DECISION_ESCALATE,
                "reason": "incident requires runtime ownership takeover",
            }

        if incident_type in self.recoverable_incident_types:
            return {
                "severity": SUPERVISOR_SEVERITY_WARNING,
                "decision": SUPERVISOR_DECISION_RECOVER if self.auto_recover else SUPERVISOR_DECISION_ESCALATE,
                "reason": "incident is recoverable under supervisor policy",
            }

        return {
            "severity": SUPERVISOR_SEVERITY_WARNING,
            "decision": SUPERVISOR_DECISION_ESCALATE,
            "reason": "incident type is not classified as safely recoverable",
        }


@dataclass(frozen=True)
class RuntimeSupervisorCase:
    case_id: str
    incident_id: str
    incident_type: str
    source_session_id: str = ""
    task_id: str = ""
    status: str = SUPERVISOR_CASE_STATUS_OPEN
    severity: str = SUPERVISOR_SEVERITY_WARNING
    decision: str = SUPERVISOR_DECISION_ESCALATE
    reason: str = ""
    recovery_ticket: dict[str, Any] = field(default_factory=dict)
    takeover_lease: dict[str, Any] = field(default_factory=dict)
    freeze_record: dict[str, Any] = field(default_factory=dict)
    isolation_record: dict[str, Any] = field(default_factory=dict)
    incident: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "status": self.status,
            "severity": self.severity,
            "decision": self.decision,
            "reason": self.reason,
            "recovery_ticket": copy.deepcopy(self.recovery_ticket),
            "takeover_lease": copy.deepcopy(self.takeover_lease),
            "freeze_record": copy.deepcopy(self.freeze_record),
            "isolation_record": copy.deepcopy(self.isolation_record),
            "incident": copy.deepcopy(self.incident),
            "metadata": copy.deepcopy(self.metadata),
            "sequence": self.sequence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSupervisorCase":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            case_id=str(data.get("case_id") or ""),
            incident_id=str(data.get("incident_id") or ""),
            incident_type=str(data.get("incident_type") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or SUPERVISOR_CASE_STATUS_OPEN),
            severity=str(data.get("severity") or SUPERVISOR_SEVERITY_WARNING),
            decision=str(data.get("decision") or SUPERVISOR_DECISION_ESCALATE),
            reason=str(data.get("reason") or ""),
            recovery_ticket=_copy_dict(data.get("recovery_ticket")),
            takeover_lease=_copy_dict(data.get("takeover_lease")),
            freeze_record=_copy_dict(data.get("freeze_record")),
            isolation_record=_copy_dict(data.get("isolation_record")),
            incident=_copy_dict(data.get("incident")),
            metadata=_copy_dict(data.get("metadata")),
            sequence=_safe_int(data.get("sequence"), 0),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeSupervisorEvent:
    event_id: str
    event_type: str
    case_id: str = ""
    incident_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "case_id": self.case_id,
            "incident_id": self.incident_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_supervisor",
        }


class RuntimeSupervisorRejected(RuntimeError):
    pass


class RuntimeSupervisor:
    """
    Governed runtime supervisor.

    Responsibilities:
    - incident intake
    - severity classification
    - escalation policy
    - recovery permission routing
    - lease takeover authorization
    - freeze/isolation records
    - supervisor audit events

    Non-responsibilities:
    - no direct step execution
    - no scheduler queue logic
    - no mutation execution
    """

    def __init__(
        self,
        *,
        policy: RuntimeSupervisorPolicy | None = None,
        orchestrator: Any = None,
        lease_registry: Any = None,
        storage_path: str | Path | None = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.policy = policy if policy is not None else RuntimeSupervisorPolicy()
        self.orchestrator = orchestrator
        self.lease_registry = lease_registry
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.journal = journal
        self.audit = audit
        self._cases: dict[str, RuntimeSupervisorCase] = {}
        self._case_order: list[str] = []
        self._events: list[RuntimeSupervisorEvent] = []
        self._sequence = 0
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeSupervisor":
        root = Path(workspace_root)
        supervisor_dir = root / "runtime_supervisor"
        supervisor_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=supervisor_dir / "runtime_supervisor.json", **kwargs)

    def intake_incident(
        self,
        incident: dict[str, Any],
        *,
        current_tick: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorCase:
        if not isinstance(incident, dict):
            raise RuntimeSupervisorRejected("runtime_supervisor_incident_must_be_dict")

        incident_id = str(incident.get("incident_id") or incident.get("id") or "").strip()
        if not incident_id:
            incident_id = "runtime-supervisor-incident-" + stable_supervisor_fingerprint(incident)[:16]

        incident_type = str(incident.get("incident_type") or incident.get("type") or "runtime_unknown_incident")
        source_session_id = str(
            incident.get("source_session_id")
            or incident.get("runtime_session_id")
            or incident.get("session_id")
            or ""
        )
        task_id = str(incident.get("task_id") or "")
        classification = self.policy.classify(incident)

        case_id = "runtime-supervisor-case-" + stable_supervisor_fingerprint(
            {
                "incident_id": incident_id,
                "incident_type": incident_type,
                "source_session_id": source_session_id,
                "task_id": task_id,
            }
        )[:16]

        existing = self._cases.get(case_id)
        if existing is not None:
            return copy.deepcopy(existing)

        self._sequence += 1
        case = RuntimeSupervisorCase(
            case_id=case_id,
            incident_id=incident_id,
            incident_type=incident_type,
            source_session_id=source_session_id,
            task_id=task_id,
            severity=str(classification["severity"]),
            decision=str(classification["decision"]),
            reason=str(classification["reason"]),
            incident=copy.deepcopy(incident),
            metadata=copy.deepcopy(metadata or {}),
            sequence=self._sequence,
        )
        self._cases[case_id] = case
        self._case_order.append(case_id)
        self._append_event(
            "runtime_supervisor_case_opened",
            case_id=case_id,
            incident_id=incident_id,
            payload={"case": case.to_dict()},
        )
        self.save()
        return copy.deepcopy(case)

    def process_incident(
        self,
        incident: dict[str, Any],
        *,
        current_tick: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorCase:
        case = self.intake_incident(incident, current_tick=current_tick, metadata=metadata)

        if case.decision == SUPERVISOR_DECISION_IGNORE:
            return self._update_case(case, status=SUPERVISOR_CASE_STATUS_IGNORED)

        if case.decision == SUPERVISOR_DECISION_RECOVER:
            return self._queue_recovery(case, current_tick=current_tick)

        if case.decision == SUPERVISOR_DECISION_TAKEOVER:
            return self._takeover(case, current_tick=current_tick)

        if case.decision == SUPERVISOR_DECISION_FREEZE:
            frozen = self._freeze(case, current_tick=current_tick)
            return self._escalate(frozen, current_tick=current_tick, reason="critical incident frozen and escalated")

        if case.decision == SUPERVISOR_DECISION_ISOLATE:
            return self._isolate(case, current_tick=current_tick)

        return self._escalate(case, current_tick=current_tick, reason=case.reason)

    def process_many(
        self,
        incidents: list[dict[str, Any]],
        *,
        current_tick: int = 0,
    ) -> list[RuntimeSupervisorCase]:
        results = []
        for incident in incidents:
            if isinstance(incident, dict):
                results.append(self.process_incident(incident, current_tick=current_tick))
        return results

    def freeze_case(
        self,
        case_id: str,
        *,
        current_tick: int = 0,
        reason: str = "manual supervisor freeze",
    ) -> RuntimeSupervisorCase:
        return self._freeze(self.get_case(case_id), current_tick=current_tick, reason=reason)

    def isolate_case(
        self,
        case_id: str,
        *,
        current_tick: int = 0,
        reason: str = "manual supervisor isolation",
    ) -> RuntimeSupervisorCase:
        return self._isolate(self.get_case(case_id), current_tick=current_tick, reason=reason)

    def escalate_case(
        self,
        case_id: str,
        *,
        current_tick: int = 0,
        reason: str = "manual supervisor escalation",
    ) -> RuntimeSupervisorCase:
        return self._escalate(self.get_case(case_id), current_tick=current_tick, reason=reason)

    def get_case(self, case_id: str) -> RuntimeSupervisorCase:
        case_id = self._validate_text("case_id", case_id)
        case = self._cases.get(case_id)
        if case is None:
            raise RuntimeSupervisorRejected(f"runtime supervisor case does not exist: {case_id!r}")
        return copy.deepcopy(case)

    def list_cases(self, *, status: str | None = None) -> list[RuntimeSupervisorCase]:
        cases = []
        for case_id in self._case_order:
            case = self._cases.get(case_id)
            if case is None:
                continue
            if status is not None and case.status != status:
                continue
            cases.append(copy.deepcopy(case))
        return cases

    def list_events(self) -> list[RuntimeSupervisorEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_supervisor",
            "cases": [
                self._cases[case_id].to_dict()
                for case_id in self._case_order
                if case_id in self._cases
            ],
            "events": [event.to_dict() for event in self._events[-500:]],
            "sequence": self._sequence,
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._cases = {}
            self._case_order = []
            self._events = []
            self._sequence = 0
            return

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._cases = {}
        self._case_order = []
        self._events = []
        self._sequence = _safe_int(payload.get("sequence"), 0) if isinstance(payload, dict) else 0

        if isinstance(payload, dict):
            for item in payload.get("cases") or []:
                if isinstance(item, dict):
                    case = RuntimeSupervisorCase.from_dict(item)
                    if case.case_id:
                        self._cases[case.case_id] = case
                        self._case_order.append(case.case_id)
            for item in payload.get("events") or []:
                if isinstance(item, dict):
                    event = RuntimeSupervisorEvent(
                        event_id=str(item.get("event_id") or ""),
                        event_type=str(item.get("event_type") or ""),
                        case_id=str(item.get("case_id") or ""),
                        incident_id=str(item.get("incident_id") or ""),
                        payload=_copy_dict(item.get("payload")),
                        metadata=_copy_dict(item.get("metadata")),
                        timestamp=str(item.get("timestamp") or utc_timestamp()),
                    )
                    if event.event_id:
                        self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _queue_recovery(self, case: RuntimeSupervisorCase, *, current_tick: int) -> RuntimeSupervisorCase:
        if self.orchestrator is None or not hasattr(self.orchestrator, "submit_incident"):
            return self._escalate(
                case,
                current_tick=current_tick,
                reason="recoverable incident has no recovery orchestrator",
            )

        ticket = self.orchestrator.submit_incident(case.incident, current_tick=current_tick)
        ticket_payload = ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket)
        updated = self._update_case(
            case,
            status=SUPERVISOR_CASE_STATUS_RECOVERY_QUEUED,
            recovery_ticket=ticket_payload,
        )
        self._append_event(
            "runtime_supervisor_recovery_queued",
            case_id=updated.case_id,
            incident_id=updated.incident_id,
            payload={"case": updated.to_dict(), "ticket": ticket_payload},
        )
        self.save()
        return updated

    def _takeover(self, case: RuntimeSupervisorCase, *, current_tick: int) -> RuntimeSupervisorCase:
        if not case.source_session_id:
            return self._escalate(
                case,
                current_tick=current_tick,
                reason="takeover incident has no source_session_id",
            )
        if self.lease_registry is None or not hasattr(self.lease_registry, "takeover_session"):
            return self._escalate(
                case,
                current_tick=current_tick,
                reason="takeover incident has no lease registry",
            )

        lease = self.lease_registry.takeover_session(
            case.source_session_id,
            self.policy.supervisor_owner_id,
            current_tick=current_tick,
            reason=f"runtime supervisor takeover for {case.incident_type}",
        )
        lease_payload = lease.to_dict() if hasattr(lease, "to_dict") else copy.deepcopy(lease)
        updated = self._update_case(
            case,
            status=SUPERVISOR_CASE_STATUS_TAKEOVER_COMPLETED,
            takeover_lease=lease_payload,
        )
        self._append_event(
            "runtime_supervisor_takeover_completed",
            case_id=updated.case_id,
            incident_id=updated.incident_id,
            payload={"case": updated.to_dict(), "takeover_lease": lease_payload},
        )
        self.save()
        return updated

    def _freeze(
        self,
        case: RuntimeSupervisorCase,
        *,
        current_tick: int,
        reason: str | None = None,
    ) -> RuntimeSupervisorCase:
        freeze_record = {
            "freeze_id": "runtime-freeze-" + stable_supervisor_fingerprint(
                {
                    "case_id": case.case_id,
                    "incident_id": case.incident_id,
                    "current_tick": current_tick,
                }
            )[:16],
            "case_id": case.case_id,
            "incident_id": case.incident_id,
            "source_session_id": case.source_session_id,
            "task_id": case.task_id,
            "reason": reason or case.reason or "runtime supervisor freeze",
            "current_tick": int(current_tick),
            "created_at": utc_timestamp(),
            "source": "runtime_supervisor",
        }
        updated = self._update_case(
            case,
            status=SUPERVISOR_CASE_STATUS_FROZEN,
            freeze_record=freeze_record,
        )
        self._append_event(
            "runtime_supervisor_runtime_frozen",
            case_id=updated.case_id,
            incident_id=updated.incident_id,
            payload={"case": updated.to_dict(), "freeze_record": freeze_record},
        )
        self.save()
        return updated

    def _isolate(
        self,
        case: RuntimeSupervisorCase,
        *,
        current_tick: int,
        reason: str | None = None,
    ) -> RuntimeSupervisorCase:
        isolation_record = {
            "isolation_id": "runtime-isolation-" + stable_supervisor_fingerprint(
                {
                    "case_id": case.case_id,
                    "incident_id": case.incident_id,
                    "current_tick": current_tick,
                }
            )[:16],
            "case_id": case.case_id,
            "incident_id": case.incident_id,
            "source_session_id": case.source_session_id,
            "task_id": case.task_id,
            "reason": reason or case.reason or "runtime supervisor isolation",
            "current_tick": int(current_tick),
            "created_at": utc_timestamp(),
            "source": "runtime_supervisor",
        }
        updated = self._update_case(
            case,
            status=SUPERVISOR_CASE_STATUS_ISOLATED,
            isolation_record=isolation_record,
        )
        self._append_event(
            "runtime_supervisor_runtime_isolated",
            case_id=updated.case_id,
            incident_id=updated.incident_id,
            payload={"case": updated.to_dict(), "isolation_record": isolation_record},
        )
        self.save()
        return updated

    def _escalate(
        self,
        case: RuntimeSupervisorCase,
        *,
        current_tick: int,
        reason: str,
    ) -> RuntimeSupervisorCase:
        updated = self._update_case(
            case,
            status=SUPERVISOR_CASE_STATUS_ESCALATED,
            reason=reason or case.reason,
            metadata={
                **copy.deepcopy(case.metadata),
                "escalated_tick": int(current_tick),
                "escalated_at": utc_timestamp(),
            },
        )
        self._append_event(
            "runtime_supervisor_case_escalated",
            case_id=updated.case_id,
            incident_id=updated.incident_id,
            payload={"case": updated.to_dict(), "reason": reason},
        )
        self.save()
        return updated

    def _update_case(self, case: RuntimeSupervisorCase, **updates: Any) -> RuntimeSupervisorCase:
        payload = case.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeSupervisorCase.from_dict(payload)
        self._cases[updated.case_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(
        self,
        event_type: str,
        *,
        case_id: str = "",
        incident_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-supervisor-event-" + stable_supervisor_fingerprint(
            {
                "event_type": event_type,
                "case_id": case_id,
                "incident_id": incident_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeSupervisorEvent(
            event_id=event_id,
            event_type=event_type,
            case_id=str(case_id or ""),
            incident_id=str(incident_id or ""),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._events.append(event)

        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(event.to_dict())
                elif hasattr(target, "record_event"):
                    target.record_event(event.to_dict())
                elif hasattr(target, "record"):
                    target.record(event.to_dict())
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_supervisor", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeSupervisorRejected(f"{field_name}_required")
        return text
