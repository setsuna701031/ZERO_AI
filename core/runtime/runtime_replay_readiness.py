from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


CANONICAL_REPLAY_READINESS_FIELDS = (
    "replay_admissible",
    "deterministic_replay",
    "replay_block_reason",
    "replay_evidence",
    "replay_state_hash",
    "replay_snapshot",
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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append(evidence: dict[str, Any], bucket: str, kind: str, **fields: Any) -> None:
    evidence.setdefault(bucket, [])
    evidence[bucket].append({"kind": kind, **copy.deepcopy(fields)})


def _has_closure_mismatch(closure: Mapping[str, Any], closure_evidence: Mapping[str, Any]) -> bool:
    mismatches = closure_evidence.get("mismatch_evidence")
    return bool(closure.get("closure_mismatch")) or (isinstance(mismatches, list) and bool(mismatches))


def build_runtime_replay_readiness_fields(
    payload: Mapping[str, Any] | None = None,
    *,
    artifact_type: str = "runtime_state",
    artifact_id: str = "",
) -> dict[str, Any]:
    data = dict(payload or {})
    execution = _nested_mapping(data, "execution_evidence")
    transaction = _nested_mapping(data, "transaction_boundary", "transaction")
    authority = _nested_mapping(data, "authority_seal", "authority")
    consistency = _nested_mapping(data, "consistency_seal")
    closure = _nested_mapping(data, "runtime_closure", "closure")
    closure_evidence = _nested_mapping(data, "closure_evidence")
    if not closure_evidence and isinstance(closure.get("closure_evidence"), Mapping):
        closure_evidence = copy.deepcopy(dict(closure["closure_evidence"]))
    recovery = _nested_mapping(data, "recovery_readiness_seal", "recovery")

    consistency_status = _lower(
        _first_text(data.get("consistency_status"), consistency.get("consistency_status"))
    )
    transaction_legality = _lower(
        _first_text(data.get("transaction_legality"), transaction.get("transaction_legality"))
    )
    transaction_status = _lower(
        _first_text(data.get("transaction_status"), transaction.get("transaction_status"), transaction.get("status"))
    )
    deterministic_state = data.get("deterministic_state")
    if deterministic_state is None:
        deterministic_state = recovery.get("deterministic_state")
    deterministic = bool(deterministic_state) if deterministic_state is not None else True

    session_state = _lower(_first_text(data.get("session_state"), data.get("lifecycle_status")))
    transition_valid = data.get("transition_valid")
    if transition_valid is None:
        transition_valid = recovery.get("transition_valid")

    evidence = {
        "artifact_type": _text(artifact_type),
        "artifact_id": _text(artifact_id),
        "replay_drift_evidence": [],
        "replay_admissibility_rejection_evidence": [],
        "deterministic_mismatch_evidence": [],
        "replay_normalization_rejection_evidence": [],
        "evidence_refs": {
            "execution_evidence": bool(execution),
            "transaction_metadata": bool(transaction),
            "authority_metadata": bool(authority),
            "consistency_snapshot": bool(consistency or consistency_status),
            "closure_evidence": bool(closure_evidence or closure),
            "recovery_readiness": bool(recovery or data.get("recovery_readiness")),
        },
    }

    missing = [key for key, present in evidence["evidence_refs"].items() if not present]
    if missing:
        _append(
            evidence,
            "deterministic_mismatch_evidence",
            "missing_replay_evidence",
            missing_evidence=missing,
        )

    if not deterministic:
        _append(
            evidence,
            "deterministic_mismatch_evidence",
            "nondeterministic_state",
            deterministic_state=deterministic_state,
        )

    if consistency_status == "mismatch":
        _append(
            evidence,
            "replay_admissibility_rejection_evidence",
            "consistency_mismatch",
            mismatch_evidence=copy.deepcopy(consistency.get("mismatch_evidence", [])),
        )

    closure_mismatch = _has_closure_mismatch(closure or data, closure_evidence)
    if closure_mismatch:
        _append(
            evidence,
            "replay_admissibility_rejection_evidence",
            "finalized_immutable_mismatch",
            closure_evidence=copy.deepcopy(closure_evidence),
        )

    incomplete_transaction = transaction_legality == "incomplete" or transaction_status == "incomplete"
    if incomplete_transaction:
        _append(
            evidence,
            "replay_admissibility_rejection_evidence",
            "incomplete_transaction",
            transaction_id=_text(transaction.get("transaction_id")),
        )

    if transition_valid is False or session_state in {"invalid", "unknown"}:
        _append(
            evidence,
            "replay_normalization_rejection_evidence",
            "runtime_session_state_normalization_rejected",
            session_state=session_state,
            transition_valid=transition_valid,
        )

    if data.get("replay_drift") or data.get("replay_state_drift"):
        _append(
            evidence,
            "replay_drift_evidence",
            "replay_drift_detected",
            expected_hash=_text(data.get("expected_replay_state_hash")),
            actual_hash=_text(data.get("actual_replay_state_hash")),
        )

    snapshot = {
        "artifact_type": _text(artifact_type),
        "artifact_id": _text(artifact_id),
        "execution_evidence": execution,
        "transaction_boundary": transaction,
        "authority_seal": authority,
        "consistency_seal": consistency,
        "runtime_closure": closure,
        "recovery_readiness": recovery or {
            key: copy.deepcopy(data.get(key))
            for key in (
                "recovery_readiness",
                "replay_readiness",
                "deterministic_state",
                "resumable_state",
                "recovery_block_reason",
            )
            if key in data
        },
        "session_state": session_state,
    }
    replay_state_hash = _stable_hash(snapshot)
    deterministic_replay = deterministic and not missing
    replay_snapshot_ready = deterministic_replay and not incomplete_transaction
    replay_admissible = (
        deterministic_replay
        and consistency_status != "mismatch"
        and not closure_mismatch
        and replay_snapshot_ready
        and not evidence["replay_drift_evidence"]
        and not evidence["replay_normalization_rejection_evidence"]
    )

    block_reasons: list[str] = []
    for bucket in (
        "replay_drift_evidence",
        "replay_admissibility_rejection_evidence",
        "deterministic_mismatch_evidence",
        "replay_normalization_rejection_evidence",
    ):
        block_reasons.extend(
            item.get("kind", "")
            for item in evidence.get(bucket, [])
            if isinstance(item, dict) and item.get("kind")
        )
    block_reason = "replay_admissible" if replay_admissible else ",".join(sorted(set(block_reasons))) or "replay_not_admissible"

    evidence["replay_admissible"] = bool(replay_admissible)
    evidence["deterministic_replay"] = bool(deterministic_replay)
    evidence["replay_snapshot_ready"] = bool(replay_snapshot_ready)
    evidence["replay_safe"] = bool(replay_admissible)
    evidence["replay_block_reason"] = block_reason
    evidence["replay_state_hash"] = replay_state_hash

    snapshot["replay_state_hash"] = replay_state_hash
    snapshot["replay_snapshot_ready"] = bool(replay_snapshot_ready)

    return {
        "replay_admissible": bool(replay_admissible),
        "deterministic_replay": bool(deterministic_replay),
        "replay_block_reason": block_reason,
        "replay_evidence": evidence,
        "replay_state_hash": replay_state_hash,
        "replay_snapshot": snapshot,
    }
