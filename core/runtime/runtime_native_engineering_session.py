from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.runtime.runtime_persistence_service import RuntimePersistenceService


SESSION_STATUS_OPEN = "open"
SESSION_STATUS_RUNNING = "running"
SESSION_STATUS_BLOCKED = "blocked"
SESSION_STATUS_COMPLETED = "completed"
SESSION_STATUS_FAILED = "failed"
SESSION_STATUS_RESUMED = "resumed"

EVENT_SESSION_OPENED = "engineering_session_opened"
EVENT_REPO_CONTEXT_CAPTURED = "repo_context_captured"
EVENT_TASK_PLANNED = "engineering_task_planned"
EVENT_MUTATION_RECORDED = "mutation_recorded"
EVENT_VERIFICATION_RECORDED = "verification_recorded"
EVENT_FAILURE_RECORDED = "failure_recorded"
EVENT_RESUME_POINT_CREATED = "resume_point_created"
EVENT_OPERATOR_HANDOFF = "operator_handoff"
EVENT_SESSION_COMPLETED = "engineering_session_completed"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_session_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimeEngineeringSessionEvent:
    event_id: str
    event_type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_engineering_session",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeEngineeringSessionEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            session_id=str(data.get("session_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeEngineeringSessionRecord:
    session_id: str
    goal: str
    workspace_root: str
    status: str = SESSION_STATUS_OPEN
    repo_context: dict[str, Any] = field(default_factory=dict)
    engineering_task: dict[str, Any] = field(default_factory=dict)
    mutation_history: list[dict[str, Any]] = field(default_factory=list)
    verification_history: list[dict[str, Any]] = field(default_factory=list)
    failure_history: list[dict[str, Any]] = field(default_factory=list)
    resume_points: list[dict[str, Any]] = field(default_factory=list)
    operator_handoffs: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "status": self.status,
            "repo_context": copy.deepcopy(self.repo_context),
            "engineering_task": copy.deepcopy(self.engineering_task),
            "mutation_history": copy.deepcopy(self.mutation_history),
            "verification_history": copy.deepcopy(self.verification_history),
            "failure_history": copy.deepcopy(self.failure_history),
            "resume_points": copy.deepcopy(self.resume_points),
            "operator_handoffs": copy.deepcopy(self.operator_handoffs),
            "timeline": copy.deepcopy(self.timeline),
            "final_result": copy.deepcopy(self.final_result),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeEngineeringSessionRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            goal=str(data.get("goal") or ""),
            workspace_root=str(data.get("workspace_root") or "."),
            status=str(data.get("status") or SESSION_STATUS_OPEN),
            repo_context=_copy_dict(data.get("repo_context")),
            engineering_task=_copy_dict(data.get("engineering_task")),
            mutation_history=_copy_list(data.get("mutation_history")),
            verification_history=_copy_list(data.get("verification_history")),
            failure_history=_copy_list(data.get("failure_history")),
            resume_points=_copy_list(data.get("resume_points")),
            operator_handoffs=_copy_list(data.get("operator_handoffs")),
            timeline=_copy_list(data.get("timeline")),
            final_result=_copy_dict(data.get("final_result")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeNativeEngineeringSessionRejected(RuntimeError):
    pass


PlanFn = Callable[[str, dict[str, Any]], dict[str, Any]]
VerifyFn = Callable[[Any], dict[str, Any]]
RepairFn = Callable[[Any, dict[str, Any]], dict[str, Any]]


class RuntimeNativeEngineeringSession:
    """
    Persistent runtime-native engineering session.

    One package:
      - persistent engineering session
      - repo context memory
      - mutation transaction history
      - verification history
      - failure replay
      - resume after crash
      - engineering timeline
      - operator handoff
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        storage_path: str | Path | None = None,
        repo_surface: Any = None,
        mutation_loop: Any = None,
        mainline: Any = None,
        scheduler: Any = None,
        dispatch: Any = None,
        coordination: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_engineering_session.json"
        self.repo_surface = repo_surface
        self.mutation_loop = mutation_loop
        self.mainline = mainline
        self.scheduler = scheduler
        self.dispatch = dispatch
        self.coordination = coordination
        self.journal = journal
        self.audit = audit
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_native_engineering_session",
        )
        self._sessions: dict[str, RuntimeEngineeringSessionRecord] = {}
        self._order: list[str] = []
        self._events: list[RuntimeEngineeringSessionEvent] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeNativeEngineeringSession":
        return cls(workspace_root=workspace_root, **kwargs)

    def open_session(
        self,
        *,
        goal: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeEngineeringSessionRecord:
        goal = self._validate_text("goal", goal)
        if session_id is None:
            session_id = "runtime-engineering-session-" + stable_session_fingerprint(
                {"goal": goal, "workspace_root": str(self.workspace_root), "sequence": len(self._order) + 1}
            )[:16]
        session_id = self._validate_text("session_id", session_id)
        if session_id in self._sessions:
            raise RuntimeNativeEngineeringSessionRejected(f"session already exists: {session_id!r}")

        record = RuntimeEngineeringSessionRecord(
            session_id=session_id,
            goal=goal,
            workspace_root=str(self.workspace_root),
            metadata=_copy_dict(metadata),
        )
        self._sessions[session_id] = record
        self._order.append(session_id)
        self._append_event(EVENT_SESSION_OPENED, session_id, {"session": record.to_dict()})
        self.save()
        return copy.deepcopy(record)

    def capture_repo_context(self, session_id: str, *, keywords: list[str] | None = None) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        if self.repo_surface is None:
            raise RuntimeNativeEngineeringSessionRejected("repo_surface_required")

        scanned = self.repo_surface.scan_repository()
        task = self.repo_surface.create_engineering_task(
            goal=record.goal,
            keywords=keywords,
        )

        repo_context = {
            "repo_files": len(scanned),
            "keywords": keywords or [],
            "impacted_files": task.impacted_files,
            "test_targets": task.test_targets,
            "task_id": task.task_id,
        }

        updated = self._replace_session(
            record,
            status=SESSION_STATUS_RUNNING,
            repo_context=repo_context,
            engineering_task=task.to_dict(),
        )
        self._append_event(EVENT_REPO_CONTEXT_CAPTURED, session_id, {"repo_context": repo_context})
        self._append_event(EVENT_TASK_PLANNED, session_id, {"engineering_task": task.to_dict()})
        return updated

    def run_mutation(
        self,
        session_id: str,
        *,
        plan_fn: PlanFn,
        verify_fn: VerifyFn | None = None,
        repair_fn: RepairFn | None = None,
        max_retries: int = 1,
    ) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        if self.mutation_loop is None:
            raise RuntimeNativeEngineeringSessionRejected("mutation_loop_required")

        mutation = self.mutation_loop.run_mutation(
            goal=record.goal,
            plan_fn=plan_fn,
            verify_fn=verify_fn,
            repair_fn=repair_fn,
            max_retries=max_retries,
            metadata={
                "engineering_session_id": session_id,
                "engineering_task": record.engineering_task,
            },
        )

        mutation_payload = mutation.to_dict() if hasattr(mutation, "to_dict") else copy.deepcopy(mutation)
        verification_history = list(record.verification_history)
        for verification in mutation_payload.get("verifications") or []:
            verification_history.append({
                "session_id": session_id,
                "mutation_id": mutation_payload.get("mutation_id"),
                "verification": copy.deepcopy(verification),
            })

        failure_history = list(record.failure_history)
        if mutation_payload.get("status") not in {"finalized", "verified"}:
            failure_history.append({
                "session_id": session_id,
                "mutation_id": mutation_payload.get("mutation_id"),
                "result": copy.deepcopy(mutation_payload.get("final_result")),
            })

        updated = self._replace_session(
            record,
            status=SESSION_STATUS_COMPLETED if mutation_payload.get("status") == "finalized" else SESSION_STATUS_FAILED,
            mutation_history=list(record.mutation_history) + [mutation_payload],
            verification_history=verification_history,
            failure_history=failure_history,
            final_result={
                "ok": mutation_payload.get("status") == "finalized",
                "mutation": mutation_payload,
            },
        )
        self._append_event(EVENT_MUTATION_RECORDED, session_id, {"mutation": mutation_payload})
        for item in verification_history[len(record.verification_history):]:
            self._append_event(EVENT_VERIFICATION_RECORDED, session_id, item)
        if failure_history and len(failure_history) > len(record.failure_history):
            self._append_event(EVENT_FAILURE_RECORDED, session_id, failure_history[-1])

        return self.get_session(session_id)

    def create_resume_point(self, session_id: str, *, reason: str, payload: dict[str, Any] | None = None) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        resume_point = {
            "resume_id": "engineering-resume-" + stable_session_fingerprint(
                {"session_id": session_id, "reason": reason, "sequence": len(record.resume_points) + 1}
            )[:16],
            "reason": reason,
            "payload": _copy_dict(payload),
            "timestamp": utc_timestamp(),
        }
        updated = self._replace_session(
            record,
            status=SESSION_STATUS_RESUMED,
            resume_points=list(record.resume_points) + [resume_point],
        )
        self._append_event(EVENT_RESUME_POINT_CREATED, session_id, {"resume_point": resume_point})
        return updated

    def operator_handoff(self, session_id: str, *, reason: str, next_action: str, payload: dict[str, Any] | None = None) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        handoff = {
            "handoff_id": "engineering-handoff-" + stable_session_fingerprint(
                {"session_id": session_id, "reason": reason, "next_action": next_action, "sequence": len(record.operator_handoffs) + 1}
            )[:16],
            "reason": reason,
            "next_action": next_action,
            "payload": _copy_dict(payload),
            "timestamp": utc_timestamp(),
        }
        updated = self._replace_session(
            record,
            status=SESSION_STATUS_BLOCKED,
            operator_handoffs=list(record.operator_handoffs) + [handoff],
        )
        self._append_event(EVENT_OPERATOR_HANDOFF, session_id, {"handoff": handoff})
        return updated

    def complete_session(self, session_id: str, *, result: dict[str, Any] | None = None) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        final_result = _copy_dict(result) if result is not None else record.final_result
        updated = self._replace_session(
            record,
            status=SESSION_STATUS_COMPLETED,
            final_result=final_result,
        )
        self._append_event(EVENT_SESSION_COMPLETED, session_id, {"result": final_result})
        return updated

    def resume_session(self, session_id: str) -> RuntimeEngineeringSessionRecord:
        record = self.get_session(session_id)
        return self._replace_session(record, status=SESSION_STATUS_RESUMED)

    def get_session(self, session_id: str) -> RuntimeEngineeringSessionRecord:
        session_id = self._validate_text("session_id", session_id)
        record = self._sessions.get(session_id)
        if record is None:
            raise RuntimeNativeEngineeringSessionRejected(f"session does not exist: {session_id!r}")
        return copy.deepcopy(record)

    def list_sessions(self) -> list[RuntimeEngineeringSessionRecord]:
        return [copy.deepcopy(self._sessions[item_id]) for item_id in self._order if item_id in self._sessions]

    def list_events(self) -> list[RuntimeEngineeringSessionEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def engineering_timeline(self, session_id: str) -> list[dict[str, Any]]:
        record = self.get_session(session_id)
        return copy.deepcopy(record.timeline)

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self._sessions.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_engineering_session_health",
            "sessions": len(self._sessions),
            "counts": counts,
            "events": len(self._events),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_engineering_session",
            "sessions": [self._sessions[item_id].to_dict() for item_id in self._order if item_id in self._sessions],
            "events": [event.to_dict() for event in self._events[-1000:]],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        if not isinstance(payload, dict):
            return
        self._sessions = {}
        self._order = []
        self._events = []
        for item in payload.get("sessions") or []:
            if isinstance(item, dict):
                record = RuntimeEngineeringSessionRecord.from_dict(item)
                if record.session_id:
                    self._sessions[record.session_id] = record
                    self._order.append(record.session_id)
        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeEngineeringSessionEvent.from_dict(item)
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_native_engineering_session_save",
            metadata={"runtime_native_engineering_session": True},
        )

    def _replace_session(self, record: RuntimeEngineeringSessionRecord, **updates: Any) -> RuntimeEngineeringSessionRecord:
        latest = self._sessions.get(record.session_id, record)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeEngineeringSessionRecord.from_dict(payload)
        self._sessions[updated.session_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(self, event_type: str, session_id: str, payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        event = RuntimeEngineeringSessionEvent(
            event_id="engineering-session-event-" + stable_session_fingerprint(
                {"event_type": event_type, "session_id": session_id, "sequence": len(self._events) + 1}
            )[:16],
            event_type=event_type,
            session_id=session_id,
            payload=_copy_dict(payload),
            metadata=_copy_dict(metadata),
        )
        self._events.append(event)

        record = self._sessions.get(session_id)
        if record is not None:
            entry = event.to_dict()
            updated_payload = record.to_dict()
            updated_payload["timeline"] = _copy_list(updated_payload.get("timeline")) + [entry]
            updated_payload["updated_at"] = utc_timestamp()
            self._sessions[session_id] = RuntimeEngineeringSessionRecord.from_dict(updated_payload)

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
                    target.append_record("runtime_native_engineering_session", event.to_dict())
            except Exception:
                pass

        self.save()

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeEngineeringSessionRejected(f"{field_name}_required")
        return text
