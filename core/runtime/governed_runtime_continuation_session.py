from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
import uuid


SESSION_ACTIVE = "active"
SESSION_SUSPENDED = "suspended"
SESSION_CONTINUED = "continued"
SESSION_CLOSED = "closed"


@dataclass(frozen=True)
class GovernedRuntimeContinuationRecord:
    continuation_id: str
    source_session_id: str
    target_session_id: str
    replay_session_id: str
    continuation_state: str
    lineage_chain: List[str]
    suspended_steps: List[Dict[str, Any]] = field(default_factory=list)
    replay_summary: Dict[str, Any] = field(default_factory=dict)
    continuation_metadata: Dict[str, Any] = field(default_factory=dict)


def build_governed_runtime_continuation_record(
    source_session_id: str,
    replay_session_id: str,
    suspended_steps: List[Dict[str, Any]] | None = None,
    replay_summary: Dict[str, Any] | None = None,
    continuation_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    suspended_steps = suspended_steps or []
    replay_summary = replay_summary or {}
    continuation_metadata = continuation_metadata or {}

    target_session_id = f"runtime-session-{uuid.uuid4().hex[:12]}"

    return {
        "continuation_id": f"runtime-continuation-{uuid.uuid4().hex[:12]}",
        "source_session_id": source_session_id,
        "target_session_id": target_session_id,
        "replay_session_id": replay_session_id,
        "continuation_state": SESSION_CONTINUED,
        "lineage_chain": [
            source_session_id,
            replay_session_id,
            target_session_id,
        ],
        "suspended_steps": suspended_steps,
        "replay_summary": replay_summary,
        "continuation_metadata": continuation_metadata,
        "data_only": True,
    }


def validate_governed_runtime_continuation_record(
    record: Dict[str, Any],
) -> Dict[str, Any]:
    issues: List[str] = []

    if not record.get("source_session_id"):
        issues.append("missing_source_session")

    if not record.get("target_session_id"):
        issues.append("missing_target_session")

    if not record.get("replay_session_id"):
        issues.append("missing_replay_session")

    lineage = record.get("lineage_chain") or []
    if len(lineage) < 3:
        issues.append("lineage_incomplete")

    if lineage and lineage[-1] != record.get("target_session_id"):
        issues.append("lineage_target_mismatch")

    continuation_valid = not issues

    return {
        "continuation_valid": continuation_valid,
        "continuation_state": (
            SESSION_CONTINUED if continuation_valid else SESSION_SUSPENDED
        ),
        "issues": issues,
        "lineage_depth": len(lineage),
        "data_only": True,
    }
