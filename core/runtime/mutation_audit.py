from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.mutation_approval import MutationApprovalResult
from core.runtime.mutation_patch_apply import MutationPatchApplyResult, MutationPatchPlan
from core.runtime.mutation_session import MutationSession
from core.runtime.mutation_verification import MutationVerificationResult


@dataclass(frozen=True)
class MutationAuditEvent:
    event_type: str
    session_id: str
    created_at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationAuditRecord:
    session_id: str
    created_at: str
    events: tuple[MutationAuditEvent, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "events": [event.to_dict() for event in self.events],
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def create_audit_event(
    *,
    event_type: str,
    session_id: str,
    payload: dict[str, Any] | None = None,
) -> MutationAuditEvent:
    if not event_type.strip():
        raise ValueError("Audit event_type must be non-empty.")

    if not session_id.strip():
        raise ValueError("Audit session_id must be non-empty.")

    return MutationAuditEvent(
        event_type=event_type.strip(),
        session_id=session_id.strip(),
        created_at=_utc_now(),
        payload=dict(payload or {}),
    )


def build_mutation_audit_record(
    *,
    session: MutationSession,
    patch_plan: MutationPatchPlan | None = None,
    verification: MutationVerificationResult | None = None,
    approval: MutationApprovalResult | None = None,
    apply_result: MutationPatchApplyResult | None = None,
    extra_events: list[MutationAuditEvent] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MutationAuditRecord:
    events: list[MutationAuditEvent] = []

    events.append(
        create_audit_event(
            event_type="mutation.session.created",
            session_id=session.session_id,
            payload=session.to_dict(),
        )
    )

    if patch_plan is not None:
        _assert_same_session(session.session_id, patch_plan.session_id, "patch_plan")
        events.append(
            create_audit_event(
                event_type="mutation.patch_plan.created",
                session_id=session.session_id,
                payload=patch_plan.to_dict(),
            )
        )

    if verification is not None:
        _assert_same_session(session.session_id, verification.session_id, "verification")
        events.append(
            create_audit_event(
                event_type="mutation.verification.completed",
                session_id=session.session_id,
                payload=verification.to_dict(),
            )
        )

    if approval is not None:
        _assert_same_session(session.session_id, approval.session_id, "approval")
        events.append(
            create_audit_event(
                event_type="mutation.approval.completed",
                session_id=session.session_id,
                payload=approval.to_dict(),
            )
        )

    if apply_result is not None:
        _assert_same_session(session.session_id, apply_result.session_id, "apply_result")
        events.append(
            create_audit_event(
                event_type="mutation.apply.completed",
                session_id=session.session_id,
                payload=apply_result.to_dict(),
            )
        )

    for event in extra_events or []:
        _assert_same_session(session.session_id, event.session_id, "extra_event")
        events.append(event)

    return MutationAuditRecord(
        session_id=session.session_id,
        created_at=_utc_now(),
        events=tuple(events),
        metadata=dict(metadata or {}),
    )


def write_audit_record(
    record: MutationAuditRecord,
    directory: str | Path,
    filename: str = "mutation_audit_record.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_text(record.to_json(), encoding="utf-8")
    return target_path


def read_audit_record(path: str | Path) -> MutationAuditRecord:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    events = tuple(
        MutationAuditEvent(
            event_type=str(item["event_type"]),
            session_id=str(item["session_id"]),
            created_at=str(item["created_at"]),
            payload=dict(item.get("payload") or {}),
        )
        for item in data.get("events", [])
    )

    return MutationAuditRecord(
        session_id=str(data["session_id"]),
        created_at=str(data["created_at"]),
        events=events,
        metadata=dict(data.get("metadata") or {}),
    )


def event_types(record: MutationAuditRecord) -> tuple[str, ...]:
    return tuple(event.event_type for event in record.events)


def _assert_same_session(expected: str, actual: str, label: str) -> None:
    if expected != actual:
        raise ValueError(f"Audit {label} session mismatch: expected {expected}, got {actual}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()