from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.operator_session import utc_timestamp


OPERATOR_CHECKPOINT_PENDING = "pending"
OPERATOR_CHECKPOINT_RUNNING = "running"
OPERATOR_CHECKPOINT_COMPLETED = "completed"
OPERATOR_CHECKPOINT_FAILED = "failed"
OPERATOR_CHECKPOINT_SKIPPED = "skipped"

OPERATOR_CHECKPOINT_STATUSES = {
    OPERATOR_CHECKPOINT_PENDING,
    OPERATOR_CHECKPOINT_RUNNING,
    OPERATOR_CHECKPOINT_COMPLETED,
    OPERATOR_CHECKPOINT_FAILED,
    OPERATOR_CHECKPOINT_SKIPPED,
}


def normalize_operator_checkpoint_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if not value:
        return OPERATOR_CHECKPOINT_PENDING
    if value not in OPERATOR_CHECKPOINT_STATUSES:
        raise ValueError(f"invalid_operator_checkpoint_status:{value}")
    return value


def _string_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values] if values else []
    if not isinstance(values, (list, tuple, set)):
        return [str(values)]
    return [str(item) for item in values if str(item or "").strip()]


@dataclass
class OperatorCheckpoint:
    checkpoint_id: str
    session_id: str
    task_id: str
    step_id: str
    step_type: str
    status: str = OPERATOR_CHECKPOINT_PENDING
    created_at: str = field(default_factory=utc_timestamp)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    error_summary: str = ""
    resume_hint: str = ""

    def __post_init__(self) -> None:
        self.checkpoint_id = str(self.checkpoint_id or "").strip()
        self.session_id = str(self.session_id or "").strip()
        self.task_id = str(self.task_id or "").strip()
        self.step_id = str(self.step_id or "").strip()
        self.step_type = str(self.step_type or "").strip()
        if not self.checkpoint_id:
            raise ValueError("operator_checkpoint_id_required")
        if not self.session_id:
            raise ValueError("operator_checkpoint_session_id_required")
        if not self.task_id:
            raise ValueError("operator_checkpoint_task_id_required")
        if not self.step_id:
            raise ValueError("operator_checkpoint_step_id_required")
        self.status = normalize_operator_checkpoint_status(self.status)
        self.state_snapshot = copy.deepcopy(
            self.state_snapshot if isinstance(self.state_snapshot, dict) else {}
        )
        self.evidence_refs = _string_list(self.evidence_refs)
        self.error_summary = str(self.error_summary or "")
        self.resume_hint = str(self.resume_hint or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "operator_checkpoint",
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "step_type": self.step_type,
            "status": self.status,
            "created_at": self.created_at,
            "state_snapshot": copy.deepcopy(self.state_snapshot),
            "evidence_refs": list(self.evidence_refs),
            "error_summary": self.error_summary,
            "resume_hint": self.resume_hint,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorCheckpoint":
        if not isinstance(payload, dict):
            raise TypeError("operator_checkpoint_payload_must_be_mapping")
        return cls(
            checkpoint_id=str(payload.get("checkpoint_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            step_id=str(payload.get("step_id") or ""),
            step_type=str(payload.get("step_type") or ""),
            status=str(payload.get("status") or OPERATOR_CHECKPOINT_PENDING),
            created_at=str(payload.get("created_at") or utc_timestamp()),
            state_snapshot=copy.deepcopy(payload.get("state_snapshot") if isinstance(payload.get("state_snapshot"), dict) else {}),
            evidence_refs=_string_list(payload.get("evidence_refs")),
            error_summary=str(payload.get("error_summary") or ""),
            resume_hint=str(payload.get("resume_hint") or ""),
        )

    def copy(self) -> "OperatorCheckpoint":
        return OperatorCheckpoint.from_dict(self.to_dict())


__all__ = [
    "OPERATOR_CHECKPOINT_COMPLETED",
    "OPERATOR_CHECKPOINT_FAILED",
    "OPERATOR_CHECKPOINT_PENDING",
    "OPERATOR_CHECKPOINT_RUNNING",
    "OPERATOR_CHECKPOINT_SKIPPED",
    "OPERATOR_CHECKPOINT_STATUSES",
    "OperatorCheckpoint",
    "normalize_operator_checkpoint_status",
]
