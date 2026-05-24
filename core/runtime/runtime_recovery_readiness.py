from __future__ import annotations

import copy
from typing import Any, Mapping

from core.runtime.runtime_replay_readiness import build_runtime_replay_readiness_fields


RECOVERY_READY = "ready"
RECOVERY_BLOCKED = "blocked"
REPLAY_READY = "ready"
REPLAY_BLOCKED = "blocked"

CANONICAL_RECOVERY_READINESS_FIELDS = (
    "recovery_readiness",
    "replay_readiness",
    "deterministic_state",
    "resumable_state",
    "recovery_block_reason",
    "recovery_evidence",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, Mapping) else {}


def _nested_mapping(data: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, Mapping):
                return copy.deepcopy(dict(value))
    evidence = data.get("evidence")
    if isinstance(evidence, Mapping):
        for key in keys:
            value = evidence.get(key)
            if isinstance(value, Mapping):
                return copy.deepcopy(dict(value))
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        cleaned = _text(value)
        if cleaned:
            return cleaned
    return ""


def _append(evidence: dict[str, Any], bucket: str, kind: str, **fields: Any) -> None:
    evidence.setdefault(bucket, [])
    evidence[bucket].append({"kind": kind, **copy.deepcopy(fields)})


def _has_closure_mismatch(closure: Mapping[str, Any], closure_evidence: Mapping[str, Any]) -> bool:
    if closure.get("closure_mismatch") or closure.get("immutable_mismatch"):
        return True
    mismatches = closure_evidence.get("mismatch_evidence")
    return isinstance(mismatches, list) and bool(mismatches)


def build_runtime_recovery_readiness_fields(
    payload: Mapping[str, Any] | None = None,
    *,
    artifact_type: str = "runtime_state",
    artifact_id: str = "",
) -> dict[str, Any]:
    data = dict(payload or {})
    execution_evidence = _nested_mapping(data, "execution_evidence")
    transaction = _nested_mapping(data, "transaction_boundary", "transaction")
    authority = _nested_mapping(data, "authority_seal", "authority")
    consistency = _nested_mapping(data, "consistency_seal")
    closure = _nested_mapping(data, "runtime_closure", "closure")
    closure_evidence = _nested_mapping(data, "closure_evidence")
    if not closure_evidence and isinstance(closure.get("closure_evidence"), Mapping):
        closure_evidence = copy.deepcopy(dict(closure["closure_evidence"]))

    consistency_status = _lower(
        _first_text(data.get("consistency_status"), consistency.get("consistency_status"))
    )
    transaction_legality = _lower(
        _first_text(
            data.get("transaction_legality"),
            transaction.get("transaction_legality"),
            transaction.get("legality"),
        )
    )
    authority_status = _lower(
        _first_text(data.get("authority_status"), authority.get("authority_status"))
    )
    ownership_source = _first_text(
        data.get("ownership_source"),
        authority.get("ownership_source"),
    )
    closure_status = _lower(
        _first_text(data.get("closure_status"), closure.get("closure_status"))
    )

    evidence = {
        "artifact_type": _text(artifact_type),
        "artifact_id": _text(artifact_id),
        "readiness_mismatch_evidence": [],
        "recovery_block_evidence": [],
        "replay_block_evidence": [],
        "deterministic_failure_evidence": [],
        "evidence_refs": {
            "execution_evidence": bool(execution_evidence),
            "transaction_metadata": bool(transaction),
            "authority_metadata": bool(authority),
            "consistency_snapshot": bool(consistency or consistency_status),
            "closure_evidence": bool(closure_evidence or closure_status),
        },
    }

    missing = [
        key
        for key, present in evidence["evidence_refs"].items()
        if not present
    ]
    if missing:
        _append(
            evidence,
            "recovery_block_evidence",
            "missing_recovery_evidence",
            missing_evidence=missing,
        )

    if consistency_status == "mismatch":
        _append(
            evidence,
            "recovery_block_evidence",
            "inconsistent_runtime_state",
            consistency_status=consistency_status,
            mismatch_evidence=copy.deepcopy(consistency.get("mismatch_evidence", [])),
        )

    closure_mismatch = _has_closure_mismatch(closure or data, closure_evidence)
    if closure_mismatch:
        _append(
            evidence,
            "replay_block_evidence",
            "finalized_immutable_mismatch",
            closure_status=closure_status,
            closure_evidence=copy.deepcopy(closure_evidence),
        )

    missing_ownership = authority_status == "missing_ownership" or not ownership_source
    if missing_ownership:
        _append(
            evidence,
            "readiness_mismatch_evidence",
            "missing_ownership",
            authority_status=authority_status,
            ownership_source=ownership_source,
        )

    incomplete_transaction = transaction_legality == "incomplete" or _lower(
        transaction.get("transaction_status")
    ) == "incomplete"
    if incomplete_transaction:
        _append(
            evidence,
            "deterministic_failure_evidence",
            "incomplete_transaction",
            transaction_id=_text(transaction.get("transaction_id")),
            transaction_legality=transaction_legality,
        )

    deterministic = not incomplete_transaction
    resumable = not missing_ownership
    replay_ready = deterministic and not closure_mismatch
    recovery_ready = (
        not missing
        and consistency_status != "mismatch"
        and replay_ready
        and resumable
    )

    block_reasons: list[str] = []
    for bucket in (
        "recovery_block_evidence",
        "replay_block_evidence",
        "deterministic_failure_evidence",
        "readiness_mismatch_evidence",
    ):
        block_reasons.extend(
            item.get("kind", "")
            for item in evidence.get(bucket, [])
            if isinstance(item, dict) and item.get("kind")
        )
    block_reason = "recovery_ready" if recovery_ready else ",".join(sorted(set(block_reasons))) or "recovery_readiness_blocked"

    evidence["recovery_readiness"] = RECOVERY_READY if recovery_ready else RECOVERY_BLOCKED
    evidence["replay_readiness"] = REPLAY_READY if replay_ready else REPLAY_BLOCKED
    evidence["deterministic_state"] = bool(deterministic)
    evidence["resumable_state"] = bool(resumable)
    evidence["recovery_block_reason"] = block_reason

    recovery_fields = {
        "recovery_readiness": RECOVERY_READY if recovery_ready else RECOVERY_BLOCKED,
        "replay_readiness": REPLAY_READY if replay_ready else REPLAY_BLOCKED,
        "deterministic_state": bool(deterministic),
        "resumable_state": bool(resumable),
        "recovery_block_reason": block_reason,
        "recovery_evidence": evidence,
    }
    recovery_fields.update(
        build_runtime_replay_readiness_fields(
            {
                **data,
                **recovery_fields,
                "recovery_readiness_seal": copy.deepcopy(recovery_fields),
            },
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
    )
    return recovery_fields
