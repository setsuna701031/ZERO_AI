from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.runtime.mutation_patch_apply import MutationPatchPlan
from core.runtime.mutation_session import (
    MutationSession,
    MutationVerificationRequirement,
)


class MutationVerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class MutationVerificationCheck:
    name: str
    passed: bool
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationVerificationResult:
    session_id: str
    verification_requirement: str
    status: MutationVerificationStatus
    created_at: str
    checks: tuple[MutationVerificationCheck, ...]
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "verification_requirement": self.verification_requirement,
            "status": self.status.value,
            "created_at": self.created_at,
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def verify_patch_plan(
    *,
    session: MutationSession,
    plan: MutationPatchPlan,
    checks: list[MutationVerificationCheck] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MutationVerificationResult:
    if plan.session_id != session.session_id:
        raise ValueError("Verification plan session mismatch.")

    verification_requirement = session.verification.value

    checks = list(checks or [])

    if session.verification == MutationVerificationRequirement.NONE:
        status = MutationVerificationStatus.PASSED

    elif session.verification == MutationVerificationRequirement.MANUAL_REVIEW:
        status = MutationVerificationStatus.BLOCKED

    else:
        if not checks:
            status = MutationVerificationStatus.FAILED
        elif all(check.passed for check in checks):
            status = MutationVerificationStatus.PASSED
        else:
            status = MutationVerificationStatus.FAILED

    summary = _build_summary(status, checks)

    return MutationVerificationResult(
        session_id=session.session_id,
        verification_requirement=verification_requirement,
        status=status,
        created_at=datetime.now(timezone.utc).isoformat(),
        checks=tuple(checks),
        summary=summary,
        metadata=dict(metadata or {}),
    )


def enforce_verification_result(
    result: MutationVerificationResult,
) -> None:
    if result.status != MutationVerificationStatus.PASSED:
        raise ValueError(
            f"Mutation verification did not pass: {result.status.value}"
        )


def write_verification_result(
    result: MutationVerificationResult,
    directory: str | Path,
    filename: str = "mutation_verification_result.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_text(result.to_json(), encoding="utf-8")
    return target_path


def read_verification_result(
    path: str | Path,
) -> MutationVerificationResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    checks = tuple(
        MutationVerificationCheck(
            name=str(item["name"]),
            passed=bool(item["passed"]),
            details=str(item.get("details", "")),
        )
        for item in data.get("checks", [])
    )

    return MutationVerificationResult(
        session_id=str(data["session_id"]),
        verification_requirement=str(data["verification_requirement"]),
        status=MutationVerificationStatus(str(data["status"])),
        created_at=str(data["created_at"]),
        checks=checks,
        summary=str(data.get("summary", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _build_summary(
    status: MutationVerificationStatus,
    checks: list[MutationVerificationCheck],
) -> str:
    if status == MutationVerificationStatus.PASSED:
        return f"Verification passed ({len(checks)} checks)."

    if status == MutationVerificationStatus.BLOCKED:
        return "Verification blocked pending manual review."

    if not checks:
        return "Verification failed because no checks were provided."

    failed_checks = [check.name for check in checks if not check.passed]

    return (
        "Verification failed: "
        + ", ".join(failed_checks)
    )