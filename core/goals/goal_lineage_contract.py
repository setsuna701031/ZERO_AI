from __future__ import annotations

"""Canonical identity and scope contract for a goal and all of its branches."""

import copy
import hashlib
import json
from typing import Any, Mapping


GOAL_LINEAGE_SCHEMA = "zero.goal_lineage.v1"
RUNTIME_IDENTITY_SCHEMA = "zero.runtime_identity.v1"

GOAL_LINEAGE_FIELDS = (
    "root_goal_id",
    "source_goal_id",
    "goal_id",
    "goal_lineage_id",
    "branch_type",
    "branch_id",
    "session_id",
    "runtime_session_id",
)

RUNTIME_IDENTITY_FIELDS = (
    "session_id",
    "runtime_session_id",
)

SESSION_IDENTITY_FIELDS = (
    "session_id",
    "runtime_session_id",
    "source_session_id",
)

_NESTED_KEYS = (
    "goal_lineage",
    "runtime_identity",
    "lineage",
    "metadata",
    "payload",
    "task",
    "runtime_queue_item",
    "continuation_work_item",
    "replan_record",
    "replan_request",
    "next_runtime_request",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sources(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources: list[Mapping[str, Any]] = [value]
    for key in _NESTED_KEYS:
        nested = value.get(key)
        if isinstance(nested, Mapping):
            sources.extend(_sources(nested))
    return sources


def _first(sources: list[Mapping[str, Any]], *fields: str) -> str:
    for source in sources:
        for field in fields:
            value = _text(source.get(field))
            if value:
                return value
    return ""


def build_goal_lineage_id(*, root_goal_id: str, session_id: str = "", runtime_session_id: str = "") -> str:
    root = _text(root_goal_id)
    if not root:
        raise ValueError("goal_lineage_requires_root_goal_id")
    canonical = json.dumps(
        {"root_goal_id": root, "runtime_session_id": _text(runtime_session_id), "session_id": _text(session_id)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "goal-lineage-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def extract_runtime_identity(
    value: Mapping[str, Any] | None,
    *,
    require_complete: bool = False,
    reject_conflicts: bool = False,
) -> dict[str, str]:
    """Extract strict runtime identity without manufacturing runtime_session_id.

    This helper is the Runtime Identity Authority V2 staging boundary.

    A missing ``runtime_session_id`` remains missing and can be rejected by
    authority boundaries that opt into strict runtime identity.
    """

    if not isinstance(value, Mapping):
        if require_complete:
            raise ValueError("runtime_identity_requires_mapping")
        return {}

    sources = _sources(value)
    if reject_conflicts:
        conflicts = [
            field
            for field in SESSION_IDENTITY_FIELDS
            if len(list(dict.fromkeys(
                _text(source.get(field))
                for source in sources
                if _text(source.get(field))
            ))) > 1
        ]
        if conflicts:
            raise ValueError("session_identity_conflicting_fields:" + ",".join(conflicts))
    identity = {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "session_id": _first(sources, "session_id", "operator_session_id", "persistent_operator_session_id"),
        "runtime_session_id": _first(sources, "runtime_session_id"),
        "source_session_id": _first(sources, "source_session_id"),
    }
    result = {key: copy.deepcopy(item) for key, item in identity.items() if _text(item)}
    if require_complete:
        missing = [field for field in RUNTIME_IDENTITY_FIELDS if not _text(result.get(field))]
        if missing:
            raise ValueError("runtime_identity_missing_fields:" + ",".join(missing))
    return result


def extract_goal_lineage(
    value: Mapping[str, Any] | None,
    *,
    require_complete: bool = False,
    reject_conflicts: bool = False,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        if require_complete:
            raise ValueError("goal_lineage_requires_mapping")
        return {}
    sources = _sources(value)
    if reject_conflicts:
        conflicts: list[str] = []
        nested_lineage = value.get("goal_lineage")
        conflict_sources = [value]
        if isinstance(nested_lineage, Mapping):
            conflict_sources.append(nested_lineage)
        for field in GOAL_LINEAGE_FIELDS:
            values = list(
                dict.fromkeys(
                    _text(source.get(field))
                    for source in conflict_sources
                    if _text(source.get(field))
                )
            )
            if len(values) > 1:
                conflicts.append(field)
        if conflicts:
            raise ValueError("goal_lineage_conflicting_fields:" + ",".join(conflicts))
    goal_id = _first(sources, "goal_id", "child_goal_id")
    source_goal_id = _first(sources, "source_goal_id", "continuation_source_goal_id")
    root_goal_id = _first(sources, "root_goal_id") or source_goal_id or goal_id
    session_id = _first(sources, "session_id", "operator_session_id", "persistent_operator_session_id")
    runtime_session_id = _first(sources, "runtime_session_id")
    branch_type = _first(sources, "branch_type")
    continuation_id = _first(sources, "continuation_id", "continuation_task_id", "continuation_goal_id")
    replan_id = _first(sources, "replan_id", "replan_request_id")
    branch_id = _first(sources, "branch_id")
    if not branch_type:
        branch_type = "continuation" if continuation_id else "replan" if replan_id else "root"
    if not branch_id:
        branch_id = continuation_id if branch_type == "continuation" else replan_id if branch_type == "replan" else root_goal_id
    lineage_id = _first(sources, "goal_lineage_id")
    if not lineage_id and root_goal_id:
        lineage_id = build_goal_lineage_id(
            root_goal_id=root_goal_id,
            session_id=session_id,
            runtime_session_id=runtime_session_id,
        )
    lineage = {
        "schema": GOAL_LINEAGE_SCHEMA,
        "root_goal_id": root_goal_id,
        "source_goal_id": source_goal_id or root_goal_id,
        "goal_id": goal_id or source_goal_id or root_goal_id,
        "goal_lineage_id": lineage_id,
        "branch_type": branch_type,
        "branch_id": branch_id,
        "session_id": session_id,
        "runtime_session_id": runtime_session_id,
    }
    result = {key: copy.deepcopy(item) for key, item in lineage.items() if _text(item)}
    if require_complete:
        missing = [field for field in GOAL_LINEAGE_FIELDS if not _text(result.get(field))]
        if missing:
            raise ValueError("goal_lineage_missing_fields:" + ",".join(missing))
    return result


def lineage_scope_matches(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    lhs = extract_goal_lineage(left)
    rhs = extract_goal_lineage(right)
    return bool(
        lhs.get("goal_lineage_id")
        and lhs.get("goal_lineage_id") == rhs.get("goal_lineage_id")
        and lhs.get("root_goal_id") == rhs.get("root_goal_id")
        and lhs.get("session_id") == rhs.get("session_id")
        and lhs.get("runtime_session_id") == rhs.get("runtime_session_id")
    )


def runtime_identity_matches(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    lhs = extract_runtime_identity(left)
    rhs = extract_runtime_identity(right)
    return bool(
        lhs.get("session_id")
        and lhs.get("runtime_session_id")
        and lhs.get("session_id") == rhs.get("session_id")
        and lhs.get("runtime_session_id") == rhs.get("runtime_session_id")
    )


def canonical_work_identity(value: Mapping[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    lineage = extract_goal_lineage(value)
    if not lineage.get("goal_lineage_id") or not lineage.get("branch_id"):
        return ()
    return (
        lineage["goal_lineage_id"],
        lineage.get("session_id", ""),
        lineage.get("runtime_session_id", ""),
        lineage.get("branch_type", ""),
        lineage["branch_id"],
    )


def attach_goal_lineage(target: Mapping[str, Any], lineage: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(target))
    canonical = extract_goal_lineage(lineage, require_complete=True)
    result["goal_lineage"] = canonical
    for field in GOAL_LINEAGE_FIELDS:
        result[field] = canonical[field]
    return result


__all__ = [
    "GOAL_LINEAGE_FIELDS",
    "GOAL_LINEAGE_SCHEMA",
    "RUNTIME_IDENTITY_FIELDS",
    "RUNTIME_IDENTITY_SCHEMA",
    "SESSION_IDENTITY_FIELDS",
    "attach_goal_lineage",
    "build_goal_lineage_id",
    "canonical_work_identity",
    "extract_goal_lineage",
    "extract_runtime_identity",
    "lineage_scope_matches",
    "runtime_identity_matches",
]
