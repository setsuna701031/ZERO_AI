from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any


class MutationRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MutationApprovalMode(str, Enum):
    AUTO = "auto"
    REVIEW_REQUIRED = "review_required"
    HUMAN_REQUIRED = "human_required"
    BLOCKED = "blocked"


class MutationVerificationRequirement(str, Enum):
    NONE = "none"
    TARGETED_TESTS = "targeted_tests"
    FULL_TEST_SUITE = "full_test_suite"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class MutationScope:
    allowed_paths: tuple[str, ...]
    denied_paths: tuple[str, ...] = ()
    max_files_changed: int | None = None
    allow_new_files: bool = True
    allow_delete_files: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationSession:
    session_id: str
    created_at: str
    intent: str
    initiator: str
    reason: str
    scope: MutationScope
    risk_level: MutationRiskLevel
    approval_mode: MutationApprovalMode
    verification: MutationVerificationRequirement
    sandbox_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk_level"] = self.risk_level.value
        data["approval_mode"] = self.approval_mode.value
        data["verification"] = self.verification.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def create_mutation_session(
    *,
    intent: str,
    initiator: str,
    reason: str,
    scope: MutationScope,
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    sandbox_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MutationSession:
    _require_text(intent, "intent")
    _require_text(initiator, "initiator")
    _require_text(reason, "reason")
    _validate_scope(scope)

    session_id = f"mutation-session-{_utc_timestamp()}-{uuid.uuid4().hex[:8]}"

    return MutationSession(
        session_id=session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        intent=intent.strip(),
        initiator=initiator.strip(),
        reason=reason.strip(),
        scope=scope,
        risk_level=risk_level,
        approval_mode=approval_mode,
        verification=verification,
        sandbox_run_id=sandbox_run_id,
        metadata=dict(metadata or {}),
    )


def write_mutation_session(
    session: MutationSession,
    directory: str | Path,
    filename: str = "mutation_session.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_text(session.to_json(), encoding="utf-8")
    return target_path


def read_mutation_session(path: str | Path) -> MutationSession:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    scope_data = data.get("scope")
    if not isinstance(scope_data, dict):
        raise ValueError("Mutation session file is missing scope object.")

    scope = MutationScope(
        allowed_paths=tuple(scope_data.get("allowed_paths") or ()),
        denied_paths=tuple(scope_data.get("denied_paths") or ()),
        max_files_changed=scope_data.get("max_files_changed"),
        allow_new_files=bool(scope_data.get("allow_new_files", True)),
        allow_delete_files=bool(scope_data.get("allow_delete_files", False)),
    )

    return MutationSession(
        session_id=str(data["session_id"]),
        created_at=str(data["created_at"]),
        intent=str(data["intent"]),
        initiator=str(data["initiator"]),
        reason=str(data["reason"]),
        scope=scope,
        risk_level=MutationRiskLevel(str(data["risk_level"])),
        approval_mode=MutationApprovalMode(str(data["approval_mode"])),
        verification=MutationVerificationRequirement(str(data["verification"])),
        sandbox_run_id=data.get("sandbox_run_id"),
        metadata=dict(data.get("metadata") or {}),
    )


def validate_mutation_path(
    relative_path: str,
    scope: MutationScope,
) -> bool:
    normalized = _normalize_relative_path(relative_path)

    if any(_path_matches(normalized, denied) for denied in scope.denied_paths):
        return False

    if not scope.allowed_paths:
        return False

    return any(_path_matches(normalized, allowed) for allowed in scope.allowed_paths)


def validate_mutation_file_count(
    changed_paths: list[str],
    scope: MutationScope,
) -> bool:
    if scope.max_files_changed is None:
        return True
    return len(set(changed_paths)) <= scope.max_files_changed


def _validate_scope(scope: MutationScope) -> None:
    if not scope.allowed_paths:
        raise ValueError("Mutation scope must include at least one allowed path.")

    for path in scope.allowed_paths + scope.denied_paths:
        _normalize_relative_path(path)


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Mutation session {name} must be non-empty text.")


def _normalize_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Mutation path must be non-empty text.")

    normalized = path.replace("\\", "/").strip()

    while normalized.startswith("./"):
        normalized = normalized[2:]

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise ValueError(f"Mutation path must be relative: {path}")

    if any(part == ".." for part in pure_path.parts):
        raise ValueError(f"Mutation path escapes workspace: {path}")

    normalized_text = str(pure_path).rstrip("/")

    if normalized_text in ("", "."):
        raise ValueError("Mutation path must be non-empty text.")

    return normalized_text


def _path_matches(path: str, rule: str) -> bool:
    normalized_rule = _normalize_relative_path(rule)

    if normalized_rule.endswith("*"):
        prefix = normalized_rule[:-1].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")

    return path == normalized_rule or path.startswith(normalized_rule + "/")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")