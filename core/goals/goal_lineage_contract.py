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

RUNTIME_IDENTITY_GRAPH_FIELDS = (
    *GOAL_LINEAGE_FIELDS,
    "execution_id",
    "capability_id",
    "evidence_id",
)

INVALID_IDENTITY_VALUES = frozenset({"unknown", "default", "legacy", "runtime", "system"})

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
    "runtime_identity_graph",
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


def create_root_goal_lineage(
    *,
    goal_id: str,
    session_id: str | None = None,
    runtime_session_id: str | None = None,
) -> dict[str, str]:
    """Canonical and sole root-lineage minting boundary."""
    goal = _required_identity("goal_id", goal_id)
    seed = hashlib.sha256(goal.encode("utf-8")).hexdigest()[:16]
    session = _required_identity("session_id", session_id or f"goal-session:{seed}")
    runtime_session = _required_identity(
        "runtime_session_id", runtime_session_id or f"runtime-session:{seed}"
    )
    return {
        "schema": GOAL_LINEAGE_SCHEMA,
        "root_goal_id": goal,
        "source_goal_id": goal,
        "goal_id": goal,
        "goal_lineage_id": build_goal_lineage_id(
            root_goal_id=goal,
            session_id=session,
            runtime_session_id=runtime_session,
        ),
        "branch_type": "root",
        "branch_id": goal,
        "session_id": session,
        "runtime_session_id": runtime_session,
    }


def create_goal_branch_lineage(
    parent: Mapping[str, Any],
    *,
    goal_id: str,
    branch_type: str,
    branch_id: str,
) -> dict[str, str]:
    """Create an explicit branch linked to its immediate canonical parent."""
    canonical = extract_goal_lineage(parent, require_complete=True, reject_conflicts=True)
    kind = _required_identity("branch_type", branch_type)
    if kind not in {"continuation", "replan"}:
        raise ValueError("explicit_goal_branch_type_required")
    child_goal = _required_identity("goal_id", goal_id)
    child_branch = _required_identity("branch_id", branch_id)
    return {
        **canonical,
        "source_goal_id": canonical["goal_id"],
        "goal_id": child_goal,
        "branch_type": kind,
        "branch_id": child_branch,
    }


def canonical_runtime_identity_graph(
    value: Mapping[str, Any] | None,
    *,
    require_complete: bool = False,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("runtime_identity_graph_requires_mapping")
    sources = _sources(value)
    graph = extract_goal_lineage(value, require_complete=require_complete, reject_conflicts=True)
    for field in ("execution_id", "capability_id", "evidence_id"):
        values = list(dict.fromkeys(_text(source.get(field)) for source in sources if _text(source.get(field))))
        if len(values) > 1:
            raise ValueError(f"runtime_identity_graph_conflict:{field}")
        if values:
            graph[field] = _required_identity(field, values[0])
    if require_complete:
        missing = [field for field in RUNTIME_IDENTITY_GRAPH_FIELDS if not _text(graph.get(field))]
        if missing:
            raise ValueError("runtime_identity_graph_missing_fields:" + ",".join(missing))
    canonical = {
        field: _required_identity(field, graph[field])
        for field in RUNTIME_IDENTITY_GRAPH_FIELDS
        if graph.get(field)
    }
    canonical["identity_graph_fingerprint"] = _identity_graph_fingerprint(canonical)
    return canonical


def bind_runtime_identity_graph(
    value: Mapping[str, Any],
    **bindings: Any,
) -> dict[str, str]:
    graph = canonical_runtime_identity_graph(value)
    for field, raw in bindings.items():
        if field not in {"execution_id", "capability_id", "evidence_id"}:
            raise ValueError(f"runtime_identity_binding_not_allowed:{field}")
        incoming = _required_identity(field, raw)
        if graph.get(field) and graph[field] != incoming:
            raise ValueError(f"runtime_identity_drift:{field}")
        graph[field] = incoming
    graph["identity_graph_fingerprint"] = _identity_graph_fingerprint(
        {field: graph[field] for field in RUNTIME_IDENTITY_GRAPH_FIELDS if graph.get(field)}
    )
    return graph


def build_runtime_execution_id(value: Mapping[str, Any], *, task_id: str) -> str:
    lineage = extract_goal_lineage(value, require_complete=True, reject_conflicts=True)
    task = _required_identity("task_id", task_id)
    encoded = json.dumps(
        {
            "goal_lineage_id": lineage["goal_lineage_id"],
            "session_id": lineage["session_id"],
            "runtime_session_id": lineage["runtime_session_id"],
            "branch_id": lineage["branch_id"],
            "task_id": task,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "execution:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def attach_runtime_identity_graph(target: Mapping[str, Any], graph: Mapping[str, Any]) -> dict[str, Any]:
    canonical = canonical_runtime_identity_graph(graph)
    result = copy.deepcopy(dict(target))
    existing = result.get("runtime_identity_graph")
    if isinstance(existing, Mapping):
        current = canonical_runtime_identity_graph(existing)
        for field in RUNTIME_IDENTITY_GRAPH_FIELDS:
            if current.get(field) and canonical.get(field) and current[field] != canonical[field]:
                raise ValueError(f"runtime_identity_drift:{field}")
    result["runtime_identity_graph"] = canonical
    for field in RUNTIME_IDENTITY_GRAPH_FIELDS:
        if canonical.get(field):
            explicit = _text(result.get(field))
            if explicit and explicit != canonical[field]:
                raise ValueError(f"runtime_identity_drift:{field}")
            result[field] = canonical[field]
    return result


def assert_runtime_identity_graph_consistency(
    *values: Mapping[str, Any],
    require_complete: bool = False,
) -> dict[str, str]:
    graphs: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        candidate = value.get("runtime_identity_graph") if isinstance(value.get("runtime_identity_graph"), Mapping) else value
        if any(candidate.get(field) for field in RUNTIME_IDENTITY_GRAPH_FIELDS):
            graphs.append(canonical_runtime_identity_graph(candidate, require_complete=require_complete))
    if not graphs:
        raise ValueError("runtime_identity_graph_required")
    expected = graphs[0]
    for graph in graphs[1:]:
        for field in RUNTIME_IDENTITY_GRAPH_FIELDS:
            if expected.get(field) and graph.get(field) and expected[field] != graph[field]:
                raise ValueError(f"runtime_identity_drift:{field}")
    return expected


def _required_identity(field: str, value: Any) -> str:
    text = _text(value)
    if not text or text.lower() in INVALID_IDENTITY_VALUES:
        raise ValueError(f"invalid_runtime_identity:{field}")
    return text


def _identity_graph_fingerprint(graph: Mapping[str, Any]) -> str:
    payload = {field: _text(graph.get(field)) for field in RUNTIME_IDENTITY_GRAPH_FIELDS if _text(graph.get(field))}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    "RUNTIME_IDENTITY_GRAPH_FIELDS",
    "INVALID_IDENTITY_VALUES",
    "SESSION_IDENTITY_FIELDS",
    "attach_goal_lineage",
    "attach_runtime_identity_graph",
    "assert_runtime_identity_graph_consistency",
    "bind_runtime_identity_graph",
    "build_goal_lineage_id",
    "build_runtime_execution_id",
    "canonical_work_identity",
    "canonical_runtime_identity_graph",
    "create_goal_branch_lineage",
    "create_root_goal_lineage",
    "extract_goal_lineage",
    "extract_runtime_identity",
    "lineage_scope_matches",
    "runtime_identity_matches",
]
