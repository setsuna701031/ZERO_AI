from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


OPERATOR_SESSION_CREATED = "created"
OPERATOR_SESSION_RUNNING = "running"
OPERATOR_SESSION_PAUSED = "paused"
OPERATOR_SESSION_FAILED = "failed"
OPERATOR_SESSION_RESUMABLE = "resumable"
OPERATOR_SESSION_COMPLETED = "completed"
OPERATOR_SESSION_ABORTED = "aborted"

OPERATOR_SESSION_STATUSES = {
    OPERATOR_SESSION_CREATED,
    OPERATOR_SESSION_RUNNING,
    OPERATOR_SESSION_PAUSED,
    OPERATOR_SESSION_FAILED,
    OPERATOR_SESSION_RESUMABLE,
    OPERATOR_SESSION_COMPLETED,
    OPERATOR_SESSION_ABORTED,
}

OPERATOR_SESSION_TERMINAL_STATUSES = {
    OPERATOR_SESSION_COMPLETED,
    OPERATOR_SESSION_ABORTED,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_operator_session_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if not value:
        return OPERATOR_SESSION_CREATED
    if value not in OPERATOR_SESSION_STATUSES:
        raise ValueError(f"invalid_operator_session_status:{value}")
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
class OperatorSession:
    session_id: str
    task_id: str
    status: str = OPERATOR_SESSION_CREATED
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    current_goal: str = ""
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None
    last_error: str = ""
    checkpoint_ids: list[str] = field(default_factory=list)
    resume_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.session_id = str(self.session_id or "").strip()
        self.task_id = str(self.task_id or "").strip()
        if not self.session_id:
            raise ValueError("operator_session_id_required")
        if not self.task_id:
            raise ValueError("operator_task_id_required")
        self.status = normalize_operator_session_status(self.status)
        self.completed_steps = _string_list(self.completed_steps)
        self.pending_steps = _string_list(self.pending_steps)
        self.checkpoint_ids = _string_list(self.checkpoint_ids)
        self.failed_step = str(self.failed_step).strip() if self.failed_step else None
        self.last_error = str(self.last_error or "")
        self.current_goal = str(self.current_goal or "")
        self.resume_count = int(self.resume_count or 0)
        self.metadata = copy.deepcopy(self.metadata if isinstance(self.metadata, dict) else {})

    @property
    def is_terminal(self) -> bool:
        return self.status in OPERATOR_SESSION_TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "operator_session",
            "session_id": self.session_id,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_goal": self.current_goal,
            "completed_steps": list(self.completed_steps),
            "pending_steps": list(self.pending_steps),
            "failed_step": self.failed_step,
            "last_error": self.last_error,
            "checkpoint_ids": list(self.checkpoint_ids),
            "resume_count": self.resume_count,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorSession":
        if not isinstance(payload, dict):
            raise TypeError("operator_session_payload_must_be_mapping")
        return cls(
            session_id=str(payload.get("session_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            status=str(payload.get("status") or OPERATOR_SESSION_CREATED),
            created_at=str(payload.get("created_at") or utc_timestamp()),
            updated_at=str(payload.get("updated_at") or utc_timestamp()),
            current_goal=str(payload.get("current_goal") or ""),
            completed_steps=_string_list(payload.get("completed_steps")),
            pending_steps=_string_list(payload.get("pending_steps")),
            failed_step=payload.get("failed_step"),
            last_error=str(payload.get("last_error") or ""),
            checkpoint_ids=_string_list(payload.get("checkpoint_ids")),
            resume_count=int(payload.get("resume_count") or 0),
            metadata=copy.deepcopy(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        )

    def copy(self) -> "OperatorSession":
        return OperatorSession.from_dict(self.to_dict())


__all__ = [
    "OPERATOR_SESSION_ABORTED",
    "OPERATOR_SESSION_COMPLETED",
    "OPERATOR_SESSION_CREATED",
    "OPERATOR_SESSION_FAILED",
    "OPERATOR_SESSION_PAUSED",
    "OPERATOR_SESSION_RESUMABLE",
    "OPERATOR_SESSION_RUNNING",
    "OPERATOR_SESSION_STATUSES",
    "OPERATOR_SESSION_TERMINAL_STATUSES",
    "OperatorSession",
    "normalize_operator_session_status",
    "utc_timestamp",
]
