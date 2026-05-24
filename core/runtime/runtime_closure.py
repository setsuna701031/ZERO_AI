from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any, Mapping


CLOSURE_OPEN = "open"
CLOSURE_FINALIZED = "finalized"
CLOSURE_COMMITTED = "committed"
CLOSURE_CLOSED = "closed"
CLOSURE_SEALED = "sealed"

CLOSED_CLOSURE_STATUSES = {
    CLOSURE_FINALIZED,
    CLOSURE_COMMITTED,
    CLOSURE_CLOSED,
    CLOSURE_SEALED,
    "rolled_back",
    "failed",
    "blocked",
    "denied",
}

TERMINAL_RUNTIME_STATUSES = {
    "completed",
    "complete",
    "succeeded",
    "success",
    "committed",
    "sealed",
    "rolled_back",
    "failed",
    "blocked",
    "denied",
}

CANONICAL_CLOSURE_FIELDS = (
    "closure_status",
    "closure_reason",
    "finalized_timestamp",
    "finalized_by",
    "immutable_state",
    "closure_evidence",
)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, Mapping) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        cleaned = _text(value)
        if cleaned:
            return cleaned
    return ""


def closure_status_is_closed(status: Any) -> bool:
    return _lower(status) in CLOSED_CLOSURE_STATUSES


def _status_from_payload(data: Mapping[str, Any]) -> str:
    status = _lower(
        _first_text(
            data.get("closure_status"),
            data.get("transaction_status"),
            data.get("session_state"),
            data.get("lifecycle_status"),
            data.get("lifecycle_state"),
            data.get("execution_status"),
            data.get("status"),
            data.get("state"),
        )
    )
    if status in {"opened", "active", "created", "running", "queued", "executing"}:
        return CLOSURE_OPEN
    if status in {"succeeded", "success", "completed", "complete"}:
        return CLOSURE_FINALIZED
    if status == "committed":
        return CLOSURE_COMMITTED
    if status == "sealed":
        return CLOSURE_SEALED
    if status in {"rolled_back", "failed", "blocked", "denied"}:
        return status
    return status or CLOSURE_OPEN


def _base_evidence(
    data: Mapping[str, Any],
    *,
    artifact_type: str,
    artifact_id: str,
    closure_status: str,
    closure_reason: str,
    finalized_timestamp: str,
    finalized_by: str,
) -> dict[str, Any]:
    existing = _mapping(data.get("closure_evidence"))
    evidence = {
        **existing,
        "artifact_type": _text(artifact_type) or _text(existing.get("artifact_type")),
        "artifact_id": _text(artifact_id) or _text(existing.get("artifact_id")),
        "closure_status": closure_status,
        "closure_reason": closure_reason,
        "finalized_timestamp": finalized_timestamp,
        "finalized_by": finalized_by,
    }
    attempts = evidence.get("mismatch_evidence")
    evidence["mismatch_evidence"] = copy.deepcopy(attempts) if isinstance(attempts, list) else []
    return evidence


def _append_mismatch(evidence: dict[str, Any], kind: str, **fields: Any) -> None:
    evidence.setdefault("mismatch_evidence", [])
    evidence["mismatch_evidence"].append({"kind": kind, **copy.deepcopy(fields)})


def _has_mutation_attempt(data: Mapping[str, Any]) -> bool:
    if data.get("mutation_attempt") or data.get("immutable_mutation_attempt"):
        return True
    if data.get("attempted_mutation") or data.get("attempted_changes"):
        return True
    return False


def _has_overwrite_attempt(data: Mapping[str, Any]) -> bool:
    if data.get("overwrite_attempt") or data.get("attempted_overwrite"):
        return True
    previous = data.get("previous_runtime_execution_result")
    return isinstance(previous, Mapping)


def _has_reopen_attempt(data: Mapping[str, Any]) -> bool:
    if data.get("reopen_attempt") or data.get("attempted_reopen"):
        return True
    requested = _lower(data.get("requested_closure_status") or data.get("requested_status"))
    return requested in {"open", "opened", "active", "running"}


def build_runtime_closure_fields(
    payload: Mapping[str, Any] | None = None,
    *,
    artifact_type: str = "runtime_state",
    artifact_id: str = "",
    closure_status: Any = "",
    closure_reason: Any = "",
    finalized_by: Any = "",
    finalized_timestamp: Any = "",
) -> dict[str, Any]:
    data = dict(payload or {})
    nested = _mapping(data.get("closure"))
    if nested:
        data = {**nested, **data}

    status = _lower(closure_status) or _status_from_payload(data)
    reason = (
        _text(closure_reason)
        or _first_text(data.get("closure_reason"), data.get("reason"), data.get("denial_reason"))
        or ("runtime_state_open" if status == CLOSURE_OPEN else f"runtime_state_{status}")
    )
    timestamp = (
        _text(finalized_timestamp)
        or _first_text(
            data.get("finalized_timestamp"),
            data.get("finished_at"),
            data.get("transaction_timestamp"),
            data.get("timestamp"),
        )
    )
    by = (
        _text(finalized_by)
        or _first_text(data.get("finalized_by"), data.get("source"), data.get("execution_source"))
        or "runtime"
    )
    immutable = bool(data.get("immutable_state")) or closure_status_is_closed(status)
    if immutable and not timestamp:
        timestamp = utc_timestamp()

    evidence = _base_evidence(
        data,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        closure_status=status,
        closure_reason=reason,
        finalized_timestamp=timestamp,
        finalized_by=by,
    )

    if immutable and _has_reopen_attempt(data):
        _append_mismatch(evidence, "reopen_attempt", requested_status=_text(data.get("requested_status") or data.get("requested_closure_status")))
    if immutable and _has_overwrite_attempt(data):
        _append_mismatch(evidence, "overwrite_attempt")
    if immutable and _has_mutation_attempt(data):
        _append_mismatch(evidence, "immutable_mutation_attempt")
    if not data.get("allow_existing_closure") and (
        isinstance(data.get("runtime_closure"), Mapping) or isinstance(data.get("closure"), Mapping)
    ):
        _append_mismatch(evidence, "duplicate_closure_propagation")
        evidence["duplicate_closure_evidence"] = _mapping(data.get("runtime_closure")) or nested

    closure_fields = {
        "closure_status": status,
        "closure_reason": reason,
        "finalized_timestamp": timestamp,
        "finalized_by": by,
        "immutable_state": immutable,
        "closure_evidence": evidence,
    }
    try:
        from core.runtime.runtime_recovery_readiness import build_runtime_recovery_readiness_fields

        closure_fields.update(
            build_runtime_recovery_readiness_fields(
                {
                    **data,
                    **closure_fields,
                    "runtime_closure": {**closure_fields},
                },
                artifact_type=artifact_type,
                artifact_id=artifact_id,
            )
        )
    except Exception:
        pass
    return closure_fields


def closure_has_mismatch(closure_fields: Mapping[str, Any] | None = None) -> bool:
    evidence = _mapping(_mapping(closure_fields).get("closure_evidence"))
    mismatches = evidence.get("mismatch_evidence")
    return bool(mismatches)
