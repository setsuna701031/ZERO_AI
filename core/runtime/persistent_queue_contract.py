from __future__ import annotations

"""Shared lineage and idempotency seal for persistent queue boundaries."""

import copy
from typing import Any, Iterable, Mapping
from core.goals.goal_lineage_contract import canonical_work_identity, extract_goal_lineage


QUEUE_LINEAGE_FIELDS = (
    "root_goal_id",
    "goal_lineage_id",
    "branch_type",
    "branch_id",
    "session_id",
    "runtime_session_id",
    "goal_id",
    "source_goal_id",
    "cycle_index",
    "task_id",
    "continuation_goal_id",
    "continuation_task_id",
    "replan_request_id",
    "evidence_ref",
    "evidence_refs",
    "decision_evidence_id",
    "authority_state",
)

QUEUE_IDENTITY_FIELDS = (
    "task_id",
    "continuation_task_id",
    "continuation_goal_id",
    "replan_request_id",
)

QUEUE_SESSION_FIELDS = (
    "session_id",
    "runtime_session_id",
    "operator_session_id",
    "persistent_operator_session_id",
    "source_session_id",
)

_NESTED_LINEAGE_KEYS = (
    "metadata",
    "lineage",
    "runtime_queue_item",
    "task",
    "continuation_work_item",
    "replan_record",
    "replan_request",
    "next_runtime_request",
)

_BLOCKED_MARKERS = (
    "blocked",
    "policy_denied",
    "policy denied",
    "authority_denied",
    "authority denied",
    "permission_denied",
    "permission denied",
    "forbidden",
)

_RECOVERABLE_MARKERS = (
    "recoverable",
    "repairable",
    "retryable",
    "missing_artifact",
    "missing artifact",
    "missing_output",
    "missing output",
    "verification_failed",
    "verification failed",
    "validation_failed",
    "validation failed",
    "artifact_not_found",
    "output_not_found",
    "request_replan",
    "retry_with_replan",
    "manual_or_planner_replan",
    " replan ",
)


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _sources(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    ordered: list[Mapping[str, Any]] = [payload]
    for key in _NESTED_LINEAGE_KEYS:
        value = payload.get(key)
        if isinstance(value, Mapping):
            ordered.extend(_sources(value))
    return ordered


def extract_queue_lineage(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract only source-provided lineage; never manufacture evidence."""
    if not isinstance(payload, Mapping):
        return {}
    sources = _sources(payload)
    lineage: dict[str, Any] = {}
    continuation = payload.get("continuation_work_item")
    if isinstance(continuation, Mapping):
        continuation_goal_id = continuation.get("continuation_goal_id") or continuation.get("goal_id")
        continuation_task_id = continuation.get("continuation_task_id") or continuation.get("task_id")
        if _present(continuation_goal_id):
            lineage["continuation_goal_id"] = copy.deepcopy(continuation_goal_id)
        if _present(continuation_task_id):
            lineage["continuation_task_id"] = copy.deepcopy(continuation_task_id)
    replan_record = payload.get("replan_record")
    if isinstance(replan_record, Mapping):
        replan_request = replan_record.get("replan_request")
        replan_request_id = replan_record.get("replan_request_id") or replan_record.get("request_id")
        if not _present(replan_request_id) and isinstance(replan_request, Mapping):
            replan_request_id = replan_request.get("request_id")
        if _present(replan_request_id):
            lineage["replan_request_id"] = copy.deepcopy(replan_request_id)
    for field in QUEUE_LINEAGE_FIELDS:
        if field in lineage:
            continue
        if field == "evidence_refs":
            refs: list[Any] = []
            for source in sources:
                value = source.get(field)
                if isinstance(value, list):
                    refs.extend(copy.deepcopy(value))
            for scalar_field in ("evidence_ref", "decision_evidence_id"):
                value = next((source.get(scalar_field) for source in sources if _present(source.get(scalar_field))), None)
                if _present(value):
                    refs.append(copy.deepcopy(value))
            if refs:
                lineage[field] = list(dict.fromkeys(refs))
            continue
        value = next((source.get(field) for source in sources if _present(source.get(field))), None)
        if _present(value):
            lineage[field] = copy.deepcopy(value)
    return lineage


def merge_queue_lineage(
    target: Mapping[str, Any],
    *sources: Mapping[str, Any] | None,
    preserve_existing_evidence: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fill missing lineage without replacing existing non-empty authority/evidence."""
    merged = copy.deepcopy(dict(target))
    conflicts: list[dict[str, Any]] = []
    for source in sources:
        incoming = extract_queue_lineage(source)
        for field, value in incoming.items():
            existing = merged.get(field)
            if field == "evidence_refs":
                existing_refs = list(existing) if isinstance(existing, list) else []
                if preserve_existing_evidence and existing_refs:
                    rejected = [item for item in value if item not in existing_refs]
                    if rejected:
                        conflicts.append({"field": field, "kept": existing_refs, "rejected": copy.deepcopy(rejected)})
                    merged[field] = existing_refs
                else:
                    merged[field] = list(dict.fromkeys([*existing_refs, *copy.deepcopy(value)]))
            elif not _present(existing):
                merged[field] = copy.deepcopy(value)
            elif existing != value:
                conflicts.append({"field": field, "kept": copy.deepcopy(existing), "rejected": copy.deepcopy(value)})
    return merged, conflicts


def queue_identity(payload: Mapping[str, Any] | None) -> dict[str, str]:
    lineage = extract_queue_lineage(payload)
    identity = {
        field: str(lineage.get(field) or "").strip()
        for field in QUEUE_IDENTITY_FIELDS
        if str(lineage.get(field) or "").strip()
    }
    session_id = queue_session_id(payload)
    if session_id:
        identity = {"session_id": session_id, **identity}
    return identity


def queue_session_id(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    for source in _sources(payload):
        for field in QUEUE_SESSION_FIELDS:
            value = str(source.get(field) or "").strip()
            if value:
                return value
    return ""


def duplicate_identity(
    candidate: Mapping[str, Any] | None,
    existing_items: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, dict[str, str]]:
    candidate_key = canonical_work_identity(candidate)
    if not candidate_key:
        return None, {}
    for existing in existing_items:
        if candidate_key == canonical_work_identity(existing):
            candidate_identity = queue_identity(candidate)
            existing_identity = queue_identity(existing)
            matched = {
                field: value
                for field, value in candidate_identity.items()
                if value and existing_identity.get(field) == value
            }
            explicit = extract_queue_lineage(candidate)
            if explicit.get("goal_lineage_id") or explicit.get("root_goal_id"):
                lineage = extract_goal_lineage(candidate)
                matched.update({
                    "goal_lineage_id": lineage.get("goal_lineage_id", ""),
                    "branch_type": lineage.get("branch_type", ""),
                    "branch_id": lineage.get("branch_id", ""),
                })
            return existing, matched
    return None, {}


def classify_queue_failure(*values: Any) -> str:
    text = " " + " ".join(str(value or "").strip().lower() for value in values) + " "
    if any(marker in text for marker in _BLOCKED_MARKERS):
        return "blocked"
    if any(marker in text for marker in _RECOVERABLE_MARKERS):
        return "replan"
    return "failed"


__all__ = [
    "QUEUE_IDENTITY_FIELDS",
    "QUEUE_LINEAGE_FIELDS",
    "QUEUE_SESSION_FIELDS",
    "classify_queue_failure",
    "duplicate_identity",
    "extract_queue_lineage",
    "merge_queue_lineage",
    "queue_identity",
    "queue_session_id",
]
