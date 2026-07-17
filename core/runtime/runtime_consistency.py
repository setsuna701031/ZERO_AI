from __future__ import annotations

import copy
from typing import Any, Mapping

from core.runtime.runtime_closure import build_runtime_closure_fields, closure_has_mismatch
from core.runtime.runtime_recovery_readiness import build_runtime_recovery_readiness_fields


CONSISTENCY_MISMATCH_STATUS = "mismatch"
CONSISTENCY_CONSISTENT_STATUS = "consistent"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        cleaned = _text(value)
        if cleaned:
            return cleaned
    return ""


def _snapshot(data: Mapping[str, Any]) -> dict[str, Any]:
    execution = _mapping(data.get("execution_evidence"))
    authority = _mapping(data.get("authority_seal"))
    transaction = _mapping(data.get("transaction_boundary"))
    lifecycle = _mapping(data.get("lifecycle"))
    metadata = _mapping(data.get("metadata"))

    lifecycle_status = _first_text(
        data.get("lifecycle_status"),
        data.get("lifecycle_state"),
        data.get("lifecycle_phase"),
        lifecycle.get("status"),
        lifecycle.get("state"),
        lifecycle.get("phase"),
        metadata.get("lifecycle_status"),
        metadata.get("lifecycle_state"),
    )
    execution_status = _first_text(
        data.get("execution_status"),
        execution.get("execution_status"),
        data.get("status"),
        metadata.get("execution_status"),
    )
    transaction_status = _first_text(
        data.get("transaction_status"),
        transaction.get("transaction_status"),
        transaction.get("status"),
        metadata.get("transaction_status"),
    )
    transaction_legality = _first_text(
        data.get("transaction_legality"),
        transaction.get("transaction_legality"),
        metadata.get("transaction_legality"),
    )
    authority_status = _first_text(
        data.get("authority_status"),
        authority.get("authority_status"),
        metadata.get("authority_status"),
    )
    ownership_source = _first_text(
        data.get("ownership_source"),
        authority.get("ownership_source"),
        metadata.get("ownership_source"),
    )
    executed = data.get("executed")
    if executed is None:
        executed = metadata.get("executed")
    ok = data.get("ok")
    if ok is None:
        ok = metadata.get("ok")

    return {
        "lifecycle_status": lifecycle_status,
        "execution_status": execution_status,
        "execution_legality": _first_text(
            data.get("execution_legality"),
            execution.get("execution_legality"),
            metadata.get("execution_legality"),
        ),
        "transaction_status": transaction_status,
        "transaction_legality": transaction_legality,
        "authority_status": authority_status,
        "ownership_source": ownership_source,
        "executed": bool(executed) if executed is not None else False,
        "ok": bool(ok) if ok is not None else False,
    }


def build_runtime_state_consistency(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    existing = data.get("consistency_seal")
    if isinstance(existing, Mapping):
        data = {**dict(existing), **data}

    snapshot = _snapshot(data)
    mismatches: list[dict[str, Any]] = []

    authority_status = _lower(snapshot.get("authority_status"))
    transaction_status = _lower(snapshot.get("transaction_status"))
    transaction_legality = _lower(snapshot.get("transaction_legality"))
    execution_status = _lower(snapshot.get("execution_status"))
    lifecycle_status = _lower(snapshot.get("lifecycle_status"))
    ownership_source = _text(snapshot.get("ownership_source"))

    if authority_status in {"denied", "blocked", "rejected", "restricted", "missing_ownership", "mismatch"} and transaction_status == "committed":
        mismatches.append(
            {
                "kind": "authority_transaction_mismatch",
                "authority_status": authority_status,
                "transaction_status": transaction_status,
            }
        )

    if execution_status in {"failed", "failure", "error", "exception"} and lifecycle_status in {"finished", "complete", "completed", "success", "succeeded"}:
        mismatches.append(
            {
                "kind": "lifecycle_execution_mismatch",
                "execution_status": execution_status,
                "lifecycle_status": lifecycle_status,
            }
        )

    if transaction_status in {"denied", "rejected", "blocked"} or transaction_legality in {"denied", "rejected", "blocked", "failed", "incomplete"}:
        if snapshot.get("executed") is True:
            mismatches.append(
                {
                    "kind": "transaction_execution_mismatch",
                    "transaction_status": transaction_status,
                    "transaction_legality": transaction_legality,
                    "executed": True,
                }
            )

    if lifecycle_status == "blocked" and (snapshot.get("executed") is True or snapshot.get("ok") is True or execution_status in {"ok", "success", "succeeded", "executed"}):
        mismatches.append(
            {
                "kind": "blocked_lifecycle_execution_mismatch",
                "lifecycle_status": lifecycle_status,
                "execution_status": execution_status,
                "executed": bool(snapshot.get("executed")),
            }
        )

    if (authority_status == "missing_ownership" or not ownership_source) and transaction_status == "committed":
        mismatches.append(
            {
                "kind": "ownership_transaction_mismatch",
                "authority_status": authority_status,
                "ownership_source": ownership_source,
                "transaction_status": transaction_status,
            }
        )

    duplicate = isinstance(data.get("runtime_consistency"), Mapping)
    if duplicate:
        mismatches.append({"kind": "duplicate_consistency_mismatch"})

    closure = build_runtime_closure_fields({**data, "allow_existing_closure": True})
    if closure_has_mismatch(closure):
        for item in closure["closure_evidence"].get("mismatch_evidence", []):
            if isinstance(item, dict):
                mismatches.append({"kind": "closure_mismatch", **copy.deepcopy(item)})

    status = CONSISTENCY_MISMATCH_STATUS if mismatches else CONSISTENCY_CONSISTENT_STATUS
    seal = {
        "consistency_status": status,
        "consistency_reason": "runtime_state_mismatch" if mismatches else "runtime_state_consistent",
        "mismatch_evidence": copy.deepcopy(mismatches),
        "runtime_state_snapshot": copy.deepcopy(snapshot),
    }
    if duplicate:
        seal["duplicate_consistency_mismatch"] = True
        seal["duplicate_consistency_evidence"] = copy.deepcopy(_mapping(data.get("runtime_consistency")))
    seal.update(
        build_runtime_recovery_readiness_fields(
            {
                **data,
                "consistency_seal": copy.deepcopy(seal),
                "consistency_status": status,
            },
            artifact_type="consistency_seal",
            artifact_id=_first_text(data.get("runtime_session_id"), data.get("execution_id"), data.get("transaction_id")),
        )
    )
    return seal


def runtime_state_consistent(payload: Mapping[str, Any] | None = None) -> bool:
    return build_runtime_state_consistency(payload).get("consistency_status") == CONSISTENCY_CONSISTENT_STATUS
