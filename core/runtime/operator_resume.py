from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.operator_checkpoint import OperatorCheckpoint
from core.runtime.operator_session import OperatorSession, utc_timestamp


@dataclass
class OperatorResumePlan:
    plan_id: str
    session_id: str
    task_id: str
    status: str
    resume_from_checkpoint_id: str | None
    resume_from_step_id: str | None
    failed_step: str | None
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""
    resume_hint: str = ""
    created_at: str = field(default_factory=utc_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "operator_resume_plan",
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "status": self.status,
            "resume_from_checkpoint_id": self.resume_from_checkpoint_id,
            "resume_from_step_id": self.resume_from_step_id,
            "failed_step": self.failed_step,
            "completed_steps": list(self.completed_steps),
            "pending_steps": list(self.pending_steps),
            "evidence_refs": list(self.evidence_refs),
            "state_snapshot": copy.deepcopy(self.state_snapshot),
            "last_error": self.last_error,
            "resume_hint": self.resume_hint,
            "created_at": self.created_at,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorResumePlan":
        if not isinstance(payload, dict):
            raise TypeError("operator_resume_plan_payload_must_be_mapping")
        return cls(
            plan_id=str(payload.get("plan_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            status=str(payload.get("status") or ""),
            resume_from_checkpoint_id=payload.get("resume_from_checkpoint_id"),
            resume_from_step_id=payload.get("resume_from_step_id"),
            failed_step=payload.get("failed_step"),
            completed_steps=[str(item) for item in payload.get("completed_steps") or []],
            pending_steps=[str(item) for item in payload.get("pending_steps") or []],
            evidence_refs=[str(item) for item in payload.get("evidence_refs") or []],
            state_snapshot=copy.deepcopy(payload.get("state_snapshot") if isinstance(payload.get("state_snapshot"), dict) else {}),
            last_error=str(payload.get("last_error") or ""),
            resume_hint=str(payload.get("resume_hint") or ""),
            created_at=str(payload.get("created_at") or utc_timestamp()),
            metadata=copy.deepcopy(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        )


def build_operator_resume_plan(
    *,
    session: OperatorSession,
    checkpoints: list[OperatorCheckpoint],
    metadata: dict[str, Any] | None = None,
) -> OperatorResumePlan:
    ordered = list(checkpoints)
    last_checkpoint = ordered[-1] if ordered else None
    evidence_refs: list[str] = []
    for checkpoint in ordered:
        for evidence_ref in checkpoint.evidence_refs:
            if evidence_ref not in evidence_refs:
                evidence_refs.append(evidence_ref)

    state_snapshot = (
        copy.deepcopy(last_checkpoint.state_snapshot)
        if last_checkpoint is not None
        else {}
    )
    resume_hint = (
        last_checkpoint.resume_hint
        if last_checkpoint is not None and last_checkpoint.resume_hint
        else "resume_from_last_operator_checkpoint"
    )
    failed_step = session.failed_step or (
        last_checkpoint.step_id if last_checkpoint is not None and last_checkpoint.status == "failed" else None
    )

    return OperatorResumePlan(
        plan_id=f"operator-resume-plan:{session.session_id}:{session.resume_count + 1}",
        session_id=session.session_id,
        task_id=session.task_id,
        status="ready" if failed_step or session.pending_steps else "blocked",
        resume_from_checkpoint_id=last_checkpoint.checkpoint_id if last_checkpoint is not None else None,
        resume_from_step_id=failed_step or (session.pending_steps[0] if session.pending_steps else None),
        failed_step=failed_step,
        completed_steps=list(session.completed_steps),
        pending_steps=list(session.pending_steps),
        evidence_refs=evidence_refs,
        state_snapshot=state_snapshot,
        last_error=session.last_error,
        resume_hint=resume_hint,
        metadata=copy.deepcopy(metadata or {}),
    )


def checkpoint_evidence_reference(checkpoint: OperatorCheckpoint) -> dict[str, Any]:
    return {
        "kind": "operator_checkpoint",
        "checkpoint_id": checkpoint.checkpoint_id,
        "session_id": checkpoint.session_id,
        "task_id": checkpoint.task_id,
        "step_id": checkpoint.step_id,
        "status": checkpoint.status,
        "evidence_refs": list(checkpoint.evidence_refs),
    }


__all__ = [
    "OperatorResumePlan",
    "build_operator_resume_plan",
    "checkpoint_evidence_reference",
]
