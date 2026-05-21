from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_status import status_from_execution_result


_BLOCKED_ERROR_TYPES = {"blocked", "denied", "rejected", "policy_blocked"}
_SUCCESS_STATUSES = {
    "ok",
    "success",
    "succeeded",
    "done",
    "completed",
    "complete",
    "finished",
    "written",
    "created",
    "updated",
}
_FAILURE_STATUSES = {
    "error",
    "failed",
    "failure",
    "blocked",
    "denied",
    "rejected",
    "exception",
}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _copy_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _metadata(payload: Any, metadata: Any | None) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return metadata
    payload_mapping = _mapping(payload)
    return _mapping(payload_mapping.get("metadata"))


def _evidence(payload: Any, metadata: Any | None, evidence: Any | None) -> dict[str, Any]:
    if isinstance(evidence, dict) and evidence:
        return evidence
    payload_mapping = _mapping(payload)
    if isinstance(payload_mapping.get("evidence"), dict) and payload_mapping.get("evidence"):
        return payload_mapping["evidence"]
    metadata_mapping = _metadata(payload_mapping, metadata)
    return _mapping(metadata_mapping.get("evidence"))


def _error_type(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("type") or error.get("error_type") or "")
    if error is not None:
        return str(error)
    return str(payload.get("error_type") or "")


def _bool_from_mapping(mapping: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    for key in keys:
        if key in mapping:
            return bool(mapping.get(key))
    return None


def _list_from_any(value: Any) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []

    if not isinstance(value, (list, tuple, set)):
        return []

    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized = item.strip()
            if normalized:
                items.append(normalized)
        elif item is not None:
            normalized = str(item).strip()
            if normalized:
                items.append(normalized)
    return items


def _extend_unique(items: list[str], value: Any) -> None:
    for item in _list_from_any(value):
        if item not in items:
            items.append(item)


def _collect_target_paths(items: list[str], value: Any) -> None:
    if not isinstance(value, list):
        return
    for entry in value:
        if not isinstance(entry, dict):
            continue
        _extend_unique(items, entry.get("impacted_files"))
        _extend_unique(items, entry.get("changed_files"))
        _extend_unique(items, entry.get("target_paths"))
        _extend_unique(items, entry.get("target_path"))
        _extend_unique(items, entry.get("path"))


def _mutation_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    return _mapping(evidence.get("mutation_summary"))


def _path_candidates(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    evidence: dict[str, Any],
) -> list[Any]:
    mutation_summary = _mutation_summary(evidence)
    candidates: list[Any] = [
        payload.get("impacted_files"),
        payload.get("changed_files"),
        payload.get("target_paths"),
        payload.get("target_path"),
        metadata.get("impacted_files"),
        metadata.get("changed_files"),
        metadata.get("target_paths"),
        metadata.get("target_path"),
        metadata.get("files"),
        mutation_summary.get("impacted_files"),
        mutation_summary.get("changed_files"),
        mutation_summary.get("target_paths"),
        mutation_summary.get("target_path"),
    ]

    for container in (
        payload.get("metadata"),
        payload.get("mutation_metadata"),
        payload.get("mutation"),
        metadata.get("mutation_metadata"),
        metadata.get("mutation"),
        metadata.get("result"),
    ):
        if isinstance(container, dict):
            candidates.extend(
                [
                    container.get("impacted_files"),
                    container.get("changed_files"),
                    container.get("target_paths"),
                    container.get("target_path"),
                    container.get("files"),
                ]
            )

    return candidates


def _resolve_file_list(payload: Any, metadata: Any | None, evidence: Any | None) -> list[str]:
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)
    evidence_mapping = _evidence(payload_mapping, metadata_mapping, evidence)
    items: list[str] = []

    for candidate in _path_candidates(payload_mapping, metadata_mapping, evidence_mapping):
        _extend_unique(items, candidate)

    for value in (
        payload_mapping.get("operations"),
        payload_mapping.get("mutations"),
        metadata_mapping.get("operations"),
        metadata_mapping.get("mutations"),
        _mutation_summary(evidence_mapping).get("operations"),
        _mutation_summary(evidence_mapping).get("mutations"),
    ):
        _collect_target_paths(items, value)

    return items


def resolve_executed(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> bool:
    del evidence
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)

    explicit = _bool_from_mapping(payload_mapping, ("ok", "executed", "success"))
    if explicit is not None:
        return explicit

    nested = payload_mapping.get("result")
    if isinstance(nested, dict):
        explicit = _bool_from_mapping(nested, ("ok", "executed", "success"))
        if explicit is not None:
            return explicit
        status = str(nested.get("status") or "").strip().lower()
        if status:
            return status in _SUCCESS_STATUSES

    explicit = _bool_from_mapping(metadata_mapping, ("ok", "executed", "success"))
    if explicit is not None:
        return explicit

    status = str(payload_mapping.get("status") or "").strip().lower()
    if status:
        return status in _SUCCESS_STATUSES

    if resolve_blocked(payload_mapping, metadata_mapping):
        return False
    if payload_mapping.get("error") or payload_mapping.get("error_type"):
        return False

    return bool(payload_mapping.get("ok", False))


def resolve_blocked(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> bool:
    del evidence
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)

    if bool(payload_mapping.get("blocked", False)) or bool(metadata_mapping.get("blocked", False)):
        return True

    error_type = _error_type(payload_mapping).strip().lower()
    if error_type in _BLOCKED_ERROR_TYPES:
        return True

    status = str(payload_mapping.get("status") or metadata_mapping.get("status") or "").strip().lower()
    return status in {"blocked", "denied", "rejected"}


def resolve_failed(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> bool:
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)

    if resolve_blocked(payload_mapping, metadata_mapping, evidence):
        return False
    if bool(payload_mapping.get("failed", False)) or bool(metadata_mapping.get("failed", False)):
        return True

    status = str(payload_mapping.get("status") or metadata_mapping.get("status") or "").strip().lower()
    if status in _FAILURE_STATUSES:
        return True

    return not resolve_executed(payload_mapping, metadata_mapping, evidence)


def resolve_verification_passed(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> bool:
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)
    evidence_mapping = _evidence(payload_mapping, metadata_mapping, evidence)
    mutation_summary = _mutation_summary(evidence_mapping)

    for source in (
        payload_mapping,
        metadata_mapping,
        mutation_summary,
        _mapping(payload_mapping.get("verification")),
        _mapping(metadata_mapping.get("verification")),
        _mapping(evidence_mapping.get("verification")),
    ):
        explicit = _bool_from_mapping(source, ("verification_passed", "ok", "passed"))
        if explicit is not None and explicit:
            return True

    return bool(resolve_executed(payload_mapping, metadata_mapping, evidence_mapping))


def resolve_changed_files(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> list[str]:
    return _resolve_file_list(payload, metadata, evidence)


def resolve_impacted_files(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> list[str]:
    return _resolve_file_list(payload, metadata, evidence)


def resolve_rollback_snapshot(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> dict[str, Any]:
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)
    evidence_mapping = _evidence(payload_mapping, metadata_mapping, evidence)

    for value in (
        payload_mapping.get("rollback_snapshot"),
        payload_mapping.get("rollback_metadata"),
        metadata_mapping.get("rollback_snapshot"),
        metadata_mapping.get("rollback_metadata"),
        evidence_mapping.get("rollback_snapshot"),
        evidence_mapping.get("rollback_metadata"),
    ):
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)
    return {}


def resolve_evidence(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> dict[str, Any]:
    payload_mapping = _mapping(payload)
    metadata_mapping = _metadata(payload_mapping, metadata)
    evidence_mapping = _copy_mapping(_evidence(payload_mapping, metadata_mapping, evidence))

    verification = _copy_mapping(payload_mapping.get("verification"))
    if not verification:
        verification = _copy_mapping(metadata_mapping.get("verification"))
    if not verification:
        verification = _copy_mapping(evidence_mapping.get("verification"))

    rollback_snapshot = resolve_rollback_snapshot(payload_mapping, metadata_mapping, evidence_mapping)
    changed_files = resolve_changed_files(payload_mapping, metadata_mapping, evidence_mapping)
    impacted_files = resolve_impacted_files(payload_mapping, metadata_mapping, evidence_mapping)
    verification_passed = resolve_verification_passed(
        payload_mapping,
        metadata_mapping,
        evidence_mapping,
    )

    mutation_summary = _copy_mapping(evidence_mapping.get("mutation_summary"))
    mutation_summary["ok"] = bool(payload_mapping.get("ok", resolve_executed(payload_mapping, metadata_mapping)))
    mutation_summary["changed_files"] = copy.deepcopy(changed_files)
    mutation_summary["impacted_files"] = copy.deepcopy(impacted_files)
    mutation_summary["rollback_available"] = bool(
        rollback_snapshot.get("restore_available", False)
        or rollback_snapshot.get("rollback_available", False)
        or rollback_snapshot.get("available", False)
    )
    mutation_summary["verification_passed"] = bool(verification_passed)

    evidence_mapping["mutation_summary"] = mutation_summary
    evidence_mapping["verification"] = verification
    evidence_mapping["rollback_metadata"] = copy.deepcopy(rollback_snapshot)

    return evidence_mapping


def normalize_runtime_execution_fields(
    payload: Any,
    metadata: Any | None = None,
    evidence: Any | None = None,
) -> dict[str, Any]:
    payload_mapping = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    metadata_mapping = copy.deepcopy(_metadata(payload_mapping, metadata))
    evidence_mapping = copy.deepcopy(_evidence(payload_mapping, metadata_mapping, evidence))

    executed = resolve_executed(payload_mapping, metadata_mapping, evidence_mapping)
    blocked = resolve_blocked(payload_mapping, metadata_mapping, evidence_mapping)
    failed = resolve_failed(payload_mapping, metadata_mapping, evidence_mapping)
    verification_passed = resolve_verification_passed(
        payload_mapping,
        metadata_mapping,
        evidence_mapping,
    )

    changed_files = resolve_changed_files(payload_mapping, metadata_mapping, evidence_mapping)
    impacted_files = resolve_impacted_files(payload_mapping, metadata_mapping, evidence_mapping)
    if not changed_files:
        changed_files = list(impacted_files)
    if not impacted_files:
        impacted_files = list(changed_files)

    rollback_snapshot = resolve_rollback_snapshot(
        payload_mapping,
        metadata_mapping,
        evidence_mapping,
    )

    normalized = copy.deepcopy(payload_mapping)
    normalized["ok"] = bool(normalized.get("ok", executed))
    normalized["executed"] = bool(executed)
    normalized["blocked"] = bool(blocked)
    normalized["failed"] = bool(failed)
    normalized["verification_passed"] = bool(verification_passed)
    normalized["changed_files"] = copy.deepcopy(changed_files)
    normalized["impacted_files"] = copy.deepcopy(impacted_files)
    normalized["rollback_metadata"] = copy.deepcopy(rollback_snapshot)
    normalized["rollback_snapshot"] = copy.deepcopy(rollback_snapshot)
    normalized["metadata"] = copy.deepcopy(metadata_mapping)
    normalized["evidence"] = resolve_evidence(
        {
            **normalized,
            "changed_files": copy.deepcopy(changed_files),
            "impacted_files": copy.deepcopy(impacted_files),
            "rollback_metadata": copy.deepcopy(rollback_snapshot),
            "rollback_snapshot": copy.deepcopy(rollback_snapshot),
        },
        metadata_mapping,
        evidence_mapping,
    )
    normalized["canonical_status"] = status_from_execution_result(normalized)

    return normalized
