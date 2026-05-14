from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationSession,
)
from core.runtime.mutation_verification import (
    MutationVerificationResult,
    MutationVerificationStatus,
)


class MutationApprovalStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    PENDING = "pending"


@dataclass(frozen=True)
class MutationApprovalDecision:
    actor: str
    decision: MutationApprovalStatus
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationApprovalResult:
    session_id: str
    approval_mode: str
    status: MutationApprovalStatus
    created_at: str
    decisions: tuple[MutationApprovalDecision, ...]
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "approval_mode": self.approval_mode,
            "status": self.status.value,
            "created_at": self.created_at,
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": self.summary,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
        )


def evaluate_approval(
    *,
    session: MutationSession,
    verification: MutationVerificationResult,
    decisions: list[MutationApprovalDecision] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MutationApprovalResult:
    if verification.session_id != session.session_id:
        raise ValueError(
            "Approval verification session mismatch."
        )

    if verification.status != MutationVerificationStatus.PASSED:
        status = MutationApprovalStatus.BLOCKED

        return MutationApprovalResult(
            session_id=session.session_id,
            approval_mode=session.approval_mode.value,
            status=status,
            created_at=_utc_now(),
            decisions=tuple(decisions or []),
            summary="Approval blocked because verification did not pass.",
            metadata=dict(metadata or {}),
        )

    mode = session.approval_mode
    decisions = list(decisions or [])

    if mode == MutationApprovalMode.AUTO:
        status = MutationApprovalStatus.APPROVED

    elif mode == MutationApprovalMode.BLOCKED:
        status = MutationApprovalStatus.BLOCKED

    elif mode == MutationApprovalMode.REVIEW_REQUIRED:
        if not decisions:
            status = MutationApprovalStatus.PENDING
        elif any(
            d.decision == MutationApprovalStatus.REJECTED
            for d in decisions
        ):
            status = MutationApprovalStatus.REJECTED
        elif any(
            d.decision == MutationApprovalStatus.APPROVED
            for d in decisions
        ):
            status = MutationApprovalStatus.APPROVED
        else:
            status = MutationApprovalStatus.PENDING

    elif mode == MutationApprovalMode.HUMAN_REQUIRED:
        if not decisions:
            status = MutationApprovalStatus.PENDING
        elif any(
            d.decision == MutationApprovalStatus.REJECTED
            for d in decisions
        ):
            status = MutationApprovalStatus.REJECTED
        elif any(
            d.actor.startswith("human:")
            and d.decision == MutationApprovalStatus.APPROVED
            for d in decisions
        ):
            status = MutationApprovalStatus.APPROVED
        else:
            status = MutationApprovalStatus.PENDING

    else:
        raise ValueError(
            f"Unsupported approval mode: {mode}"
        )

    summary = _build_summary(status, decisions)

    return MutationApprovalResult(
        session_id=session.session_id,
        approval_mode=mode.value,
        status=status,
        created_at=_utc_now(),
        decisions=tuple(decisions),
        summary=summary,
        metadata=dict(metadata or {}),
    )


def enforce_approval_result(
    result: MutationApprovalResult,
) -> None:
    if result.status != MutationApprovalStatus.APPROVED:
        raise ValueError(
            f"Mutation approval did not pass: {result.status.value}"
        )


def write_approval_result(
    result: MutationApprovalResult,
    directory: str | Path,
    filename: str = "mutation_approval_result.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    target_path = target_dir / filename

    target_path.write_text(
        result.to_json(),
        encoding="utf-8",
    )

    return target_path


def read_approval_result(
    path: str | Path,
) -> MutationApprovalResult:
    data = json.loads(
        Path(path).read_text(encoding="utf-8")
    )

    decisions = tuple(
        MutationApprovalDecision(
            actor=str(item["actor"]),
            decision=MutationApprovalStatus(
                str(item["decision"])
            ),
            reason=str(item.get("reason", "")),
        )
        for item in data.get("decisions", [])
    )

    return MutationApprovalResult(
        session_id=str(data["session_id"]),
        approval_mode=str(data["approval_mode"]),
        status=MutationApprovalStatus(
            str(data["status"])
        ),
        created_at=str(data["created_at"]),
        decisions=decisions,
        summary=str(data.get("summary", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _build_summary(
    status: MutationApprovalStatus,
    decisions: list[MutationApprovalDecision],
) -> str:
    if status == MutationApprovalStatus.APPROVED:
        return "Mutation approved."

    if status == MutationApprovalStatus.REJECTED:
        return "Mutation rejected."

    if status == MutationApprovalStatus.BLOCKED:
        return "Mutation approval blocked."

    if not decisions:
        return "Mutation approval pending review."

    return "Mutation approval pending."


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()