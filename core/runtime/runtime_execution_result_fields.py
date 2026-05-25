from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_status import status_from_execution_result
from core.runtime.runtime_authority import authority_allows_execution, build_authority_metadata
from core.runtime.runtime_consistency import build_runtime_state_consistency
from core.runtime.runtime_closure import build_runtime_closure_fields, closure_has_mismatch
from core.runtime.runtime_recovery_readiness import build_runtime_recovery_readiness_fields


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
_LEGAL_EXECUTION_SOURCES = {
    "legacy_runtime_execution_result",
    "runtime_execution_result",
    "runtime_execution_gateway",
    "canonical_execution_gateway",
    "step_executor",
    "runtime_step_executor",
    "executor",
    "runtime_executor",
    "runtime_execution_session",
    "governed_mutation",
    "repair_transaction_execution_bridge",
}
_EXECUTION_SOURCE_PRODUCER_LAYERS = {
    "legacy_runtime_execution_result": "runtime",
    "runtime_execution_result": "runtime",
    "runtime_execution_gateway": "governed_execution",
    "canonical_execution_gateway": "governed_execution",
    "step_executor": "step_executor",
    "runtime_step_executor": "step_executor",
    "executor": "step_executor",
    "runtime_executor": "step_executor",
    "runtime_execution_session": "governed_execution",
    "governed_mutation": "governed_execution",
    "repair_transaction_execution_bridge": "governed_execution",
}
_TRUSTED_EXECUTION_PRODUCER_LAYERS = {"runtime", "governed_execution", "step_executor"}


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


def _status(payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    metadata_mapping = _mapping(metadata)
    return str(payload.get("status") or metadata_mapping.get("status") or "").strip().lower()


def _execution_source(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    source = str(
        payload.get("execution_source")
        or metadata.get("execution_source")
        or metadata.get("source")
        or payload.get("source")
        or ""
    ).strip()
    return source or "legacy_runtime_execution_result"


def _producer_layer(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized in _EXECUTION_SOURCE_PRODUCER_LAYERS:
        return _EXECUTION_SOURCE_PRODUCER_LAYERS[normalized]
    if normalized.startswith("scheduler"):
        return "scheduler"
    if normalized.startswith("agent_loop") or normalized == "agentloop":
        return "agent_loop"
    if "code_chain" in normalized:
        return "output_artifact"
    return "external"


def _declared_producer_layer(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        payload.get("producer_layer")
        or metadata.get("producer_layer")
        or ""
    ).strip()


def _execution_id(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        payload.get("execution_id")
        or metadata.get("execution_id")
        or payload.get("execution_start_id")
        or metadata.get("execution_start_id")
        or ""
    ).strip()


def _runtime_session_id(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        payload.get("runtime_session_id")
        or metadata.get("runtime_session_id")
        or payload.get("session_id")
        or metadata.get("session_id")
        or ""
    ).strip()


def _timestamp(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(payload.get("timestamp") or metadata.get("timestamp") or "").strip()


def _denial_reason(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        reason = error.get("reason") or error.get("message") or error.get("type")
        if reason:
            return str(reason)
    for key in ("denial_reason", "blocked_reason", "error_type"):
        value = payload.get(key)
        if value:
            return str(value)
        value = metadata.get(key)
        if value:
            return str(value)
    if error:
        return str(error)
    return ""


def _failure_evidence(payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in ("error_type", "message", "final_answer", "status"):
        value = payload.get(key)
        if value:
            evidence[key] = copy.deepcopy(value)
    error = payload.get("error")
    if error:
        evidence["error"] = copy.deepcopy(error)
    metadata_error = metadata.get("error")
    if metadata_error and "error" not in evidence:
        evidence["error"] = copy.deepcopy(metadata_error)
    return evidence


def _has_blocked_signal(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    if bool(payload.get("blocked", False)) or bool(metadata.get("blocked", False)):
        return True
    if _error_type(payload).strip().lower() in _BLOCKED_ERROR_TYPES:
        return True
    return _status(payload, metadata) in {"blocked", "denied", "rejected"}


def _has_failed_signal(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    if bool(payload.get("failed", False)) or bool(metadata.get("failed", False)):
        return True
    if payload.get("error") or payload.get("error_type"):
        return True
    return _status(payload, metadata) in _FAILURE_STATUSES


def _authority_payload(payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    authority = build_authority_metadata({**metadata, **payload})
    return authority


def _has_denied_authority(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return not authority_allows_execution({**metadata, **payload})


def _duplicate_execution_propagation(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return isinstance(payload.get("runtime_execution_result"), dict) or isinstance(
        metadata.get("runtime_execution_result"),
        dict,
    )


def _execution_legality_metadata(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    executed: bool,
    blocked: bool,
    failed: bool,
) -> dict[str, Any]:
    source = _execution_source(payload, metadata)
    status = _status(payload, metadata)
    duplicate = _duplicate_execution_propagation(payload, metadata)
    denial_reason = _denial_reason(payload, metadata)

    legal_source = source in _LEGAL_EXECUTION_SOURCES
    expected_producer_layer = _producer_layer(source)
    declared_producer_layer = _declared_producer_layer(payload, metadata)
    producer_layer = declared_producer_layer or expected_producer_layer
    producer_mismatch = bool(
        declared_producer_layer
        and expected_producer_layer in _TRUSTED_EXECUTION_PRODUCER_LAYERS
        and declared_producer_layer != expected_producer_layer
    )
    untrusted_producer = producer_layer not in _TRUSTED_EXECUTION_PRODUCER_LAYERS
    if duplicate:
        legality = "duplicate"
        denial_reason = denial_reason or "duplicate_execution_propagation"
    elif blocked:
        legality = "denied"
        denial_reason = denial_reason or "execution_blocked"
    elif failed:
        legality = "failed"
        denial_reason = denial_reason or "execution_failed"
    elif executed and legal_source and producer_mismatch:
        legality = "denied"
        denial_reason = denial_reason or f"producer_layer_mismatch:{producer_layer}"
    elif executed and legal_source and untrusted_producer:
        legality = "denied"
        denial_reason = denial_reason or f"untrusted_producer_layer:{producer_layer}"
    elif executed and legal_source:
        legality = "legal"
    elif executed:
        legality = "denied"
        denial_reason = denial_reason or f"illegal_execution_source:{source}"
    else:
        legality = "not_executed"

    result = {
        "execution_source": source,
        "producer_layer": producer_layer,
        "execution_status": status or ("executed" if executed else "not_executed"),
        "execution_legality": legality,
        "duplicate_execution_propagation": duplicate,
    }
    if denial_reason:
        result["denial_reason"] = denial_reason
    return result


def _canonical_execution_evidence(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    legality: dict[str, Any],
    timestamp: str,
    failed: bool,
) -> dict[str, Any]:
    evidence = {
        "execution_id": _execution_id(payload, metadata),
        "execution_source": legality["execution_source"],
        "producer_layer": legality.get("producer_layer") or _producer_layer(legality["execution_source"]),
        "execution_status": legality["execution_status"],
        "execution_legality": legality["execution_legality"],
        "timestamp": timestamp,
    }
    denial_reason = legality.get("denial_reason")
    if denial_reason:
        evidence["denial_reason"] = denial_reason
    runtime_session_id = _runtime_session_id(payload, metadata)
    if runtime_session_id:
        evidence["runtime_session_id"] = runtime_session_id
    if failed:
        failure = _failure_evidence(payload, metadata)
        if failure:
            evidence["failure_evidence"] = failure
    if legality.get("duplicate_execution_propagation"):
        nested = payload.get("runtime_execution_result") or metadata.get("runtime_execution_result")
        evidence["duplicate_execution_propagation"] = True
        if isinstance(nested, dict):
            evidence["duplicate_execution_evidence"] = {
                "execution_id": str(nested.get("execution_id") or ""),
                "execution_source": str(nested.get("execution_source") or ""),
                "execution_status": str(nested.get("execution_status") or nested.get("status") or ""),
                "execution_legality": str(nested.get("execution_legality") or ""),
            }
    return evidence


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

    if _duplicate_execution_propagation(payload_mapping, metadata_mapping):
        return False
    if _has_blocked_signal(payload_mapping, metadata_mapping):
        return False
    if _has_failed_signal(payload_mapping, metadata_mapping):
        return False
    if _has_denied_authority(payload_mapping, metadata_mapping):
        return False
    if build_runtime_state_consistency({**metadata_mapping, **payload_mapping}).get("consistency_status") == "mismatch":
        return False

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

    status = _status(payload_mapping, metadata_mapping)
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

    return _status(payload_mapping, metadata_mapping) in {"blocked", "denied", "rejected"}


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

    if _status(payload_mapping, metadata_mapping) in _FAILURE_STATUSES:
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
    authority = _authority_payload(payload_mapping, metadata_mapping)
    legality = _execution_legality_metadata(
        payload_mapping,
        metadata_mapping,
        executed=bool(normalized["executed"]),
        blocked=bool(normalized["blocked"]),
        failed=bool(normalized["failed"]),
    )
    if legality["execution_legality"] in {"denied", "duplicate", "failed"}:
        normalized["executed"] = False
        normalized["ok"] = False
        if legality["execution_legality"] == "failed":
            normalized["failed"] = True
        normalized["canonical_status"] = status_from_execution_result(normalized)
    if authority["authority_status"] in {
        "denied",
        "blocked",
        "rejected",
        "restricted",
        "requires_confirmation",
        "missing_ownership",
        "mismatch",
        "duplicate",
        "closed_transaction_boundary",
    }:
        normalized["executed"] = False
        normalized["ok"] = False
        normalized["canonical_status"] = status_from_execution_result(normalized)
    consistency = build_runtime_state_consistency(
        {
            **metadata_mapping,
            **payload_mapping,
            **legality,
            **authority,
            "executed": payload_mapping.get("executed", normalized["executed"]),
            "ok": payload_mapping.get("ok", normalized["ok"]),
        }
    )
    if consistency["consistency_status"] == "mismatch":
        normalized["executed"] = False
        normalized["ok"] = False
        normalized["canonical_status"] = status_from_execution_result(normalized)
    closure = build_runtime_closure_fields(
        {
            **metadata_mapping,
            **payload_mapping,
            "allow_existing_closure": True,
            "execution_status": legality.get("execution_status"),
            "status": normalized.get("status"),
            "timestamp": _timestamp(normalized, metadata_mapping),
        },
        artifact_type="execution",
        artifact_id=_execution_id(payload_mapping, metadata_mapping),
        finalized_by=legality.get("execution_source") or _execution_source(payload_mapping, metadata_mapping),
    )
    if closure_has_mismatch(closure):
        normalized["executed"] = False
        normalized["ok"] = False
        normalized["canonical_status"] = status_from_execution_result(normalized)
    execution_evidence = _canonical_execution_evidence(
        payload_mapping,
        metadata_mapping,
        legality=legality,
        timestamp=_timestamp(normalized, metadata_mapping),
        failed=bool(normalized["failed"]),
    )
    recovery = build_runtime_recovery_readiness_fields(
        {
            **metadata_mapping,
            **payload_mapping,
            **legality,
            **authority,
            **consistency,
            **closure,
            "execution_evidence": execution_evidence,
            "authority_seal": authority,
            "consistency_seal": consistency,
            "runtime_closure": closure,
        },
        artifact_type="execution",
        artifact_id=_execution_id(payload_mapping, metadata_mapping),
    )
    normalized.update(legality)
    normalized.update(authority)
    normalized.update(consistency)
    normalized.update(closure)
    normalized.update(recovery)
    normalized["execution_evidence"] = copy.deepcopy(execution_evidence)
    normalized["evidence"] = {
        **copy.deepcopy(normalized["evidence"]),
        "execution_evidence": copy.deepcopy(execution_evidence),
        "consistency_seal": copy.deepcopy(consistency),
        "closure_evidence": copy.deepcopy(closure["closure_evidence"]),
        "recovery_evidence": copy.deepcopy(recovery["recovery_evidence"]),
        "replay_evidence": copy.deepcopy(recovery["replay_evidence"]),
    }
    normalized["metadata"] = {
        **copy.deepcopy(normalized["metadata"]),
        **copy.deepcopy(legality),
        **copy.deepcopy(authority),
        **copy.deepcopy(consistency),
        **copy.deepcopy(closure),
        **copy.deepcopy(recovery),
        "authority_seal": copy.deepcopy(authority),
        "consistency_seal": copy.deepcopy(consistency),
        "execution_evidence": copy.deepcopy(execution_evidence),
        "runtime_closure": copy.deepcopy(closure),
        "recovery_readiness_seal": copy.deepcopy(recovery),
        "replay_readiness_seal": {
            key: copy.deepcopy(recovery[key])
            for key in (
                "replay_admissible",
                "deterministic_replay",
                "replay_block_reason",
                "replay_evidence",
                "replay_state_hash",
                "replay_snapshot",
            )
        },
    }

    return normalized


# ZERO v7.3.32 - Public runtime output sanitizer field policy
# These names belong to observation/evidence internals. They may be retained by
# private hooks/boundaries, but public runtime outputs must not expose them.
ZERO_V7332_PUBLIC_OUTPUT_INTERNAL_KEYS = frozenset(
    {
        "evidence",
        "evidence_adapter",
        "evidence_events",
        "boundary",
        "boundary_fingerprint",
        "adapter_fingerprint",
        "hook",
        "hook_fingerprint",
    }
)


def public_runtime_output_internal_keys() -> frozenset[str]:
    return ZERO_V7332_PUBLIC_OUTPUT_INTERNAL_KEYS
