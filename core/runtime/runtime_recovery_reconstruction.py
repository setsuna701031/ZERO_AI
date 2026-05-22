from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.runtime_status import status_from_recovery_state
from core.runtime.runtime_status_transition import runtime_status_transition_payload


SCHEMA_VERSION = "runtime_recovery_reconstruction.v1"

RECONSTRUCTION_CONSISTENT = "consistent"
RECONSTRUCTION_FAILED = "failed"
RECONSTRUCTION_INCONSISTENT = "inconsistent"
RECONSTRUCTION_DIVERGED = "diverged"

RECOVERY_CONSTITUTION_CANONICAL = "canonical"
RECOVERY_CONSTITUTION_REVIEW_REQUIRED = "review_required"
RECOVERY_CONSTITUTION_BLOCK_RECOMMENDED = "block_recommended"

RECONSTRUCTION_REQUIRED_FIELDS: tuple[str, ...] = (
    "reconstruction_id",
    "source_transaction_id",
    "source_evidence_chain",
    "reconstruction_state",
    "replay_source_count",
    "reconstructed_runtime_state",
    "reconstruction_consistent",
)


def runtime_recovery_reconstruction_required_fields() -> List[str]:
    return list(RECONSTRUCTION_REQUIRED_FIELDS)


def build_runtime_recovery_reconstruction_contract(
    *,
    source_transaction_id: str,
    source_evidence_chain: Iterable[Any],
    reconstruction_state: str = RECONSTRUCTION_CONSISTENT,
    reconstructed_runtime_state: Any = "",
    reconstruction_consistent: bool = True,
    reconstruction_id: str = "",
) -> Dict[str, Any]:
    evidence = [copy.deepcopy(item) for item in source_evidence_chain or [] if isinstance(item, dict)]
    transition = runtime_status_transition_payload(
        "unknown",
        status_from_recovery_state(reconstruction_state),
        source="runtime_recovery_reconstruction",
    )
    constitution = recovery_constitution_summary(
        recovery_id=_text(reconstruction_id),
        recovery_lineage=[_text(source_transaction_id)] if _text(source_transaction_id) else [],
        recovery_source_state={
            "source_transaction_id": _text(source_transaction_id),
            "source_evidence_count": len(evidence),
        },
        recovery_target_state=reconstructed_runtime_state,
        transition=transition,
        transition_evidence=transition["transition_evidence"],
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "reconstruction_id": _text(reconstruction_id),
        "source_transaction_id": _text(source_transaction_id),
        "source_evidence_chain": evidence,
        "reconstruction_state": _text(reconstruction_state),
        "canonical_status": status_from_recovery_state(reconstruction_state),
        "canonical_from_status": transition["from_status"],
        "canonical_to_status": transition["to_status"],
        "transition_allowed": transition["allowed"],
        "transition_regression": transition["regression"],
        "transition_reason": transition["transition_reason"],
        "transition_trigger": transition["transition_trigger"],
        "transition_source": transition["transition_source"],
        "transition_evidence": transition["transition_evidence"],
        "enforcement_readiness": transition["enforcement_readiness"],
        "enforcement_classification": transition["enforcement_classification"],
        "enforcement_reason": transition["enforcement_reason"],
        "safe_to_enforce": transition["safe_to_enforce"],
        "review_required": transition["review_required"] or constitution["review_required"],
        "block_recommended": transition["block_recommended"] or constitution["block_recommended"],
        "constitutional_continuity": constitution["constitutional_continuity"],
        "continuity_verified": constitution["continuity_verified"],
        "continuity_break": constitution["continuity_break"],
        "recovery_constitution_status": constitution["recovery_constitution_status"],
        "enforcement_visibility": constitution["enforcement_visibility"],
        "enforcement_snapshot": constitution["enforcement_snapshot"],
        "replay_source_count": len(evidence),
        "reconstructed_runtime_state": copy.deepcopy(reconstructed_runtime_state),
        "reconstruction_consistent": bool(reconstruction_consistent),
    }
    if not payload["reconstruction_id"]:
        payload["reconstruction_id"] = _reconstruction_id(payload)
    return payload


def validate_runtime_recovery_reconstruction_contract(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in RECONSTRUCTION_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("reconstruction_state")) not in {
        RECONSTRUCTION_CONSISTENT,
        RECONSTRUCTION_FAILED,
        RECONSTRUCTION_INCONSISTENT,
        RECONSTRUCTION_DIVERGED,
    }:
        invalid_fields.append({"field": "reconstruction_state", "reason": "invalid_state"})
    if "source_evidence_chain" in payload and not isinstance(payload.get("source_evidence_chain"), list):
        invalid_fields.append({"field": "source_evidence_chain", "reason": "expected_list"})
    if "replay_source_count" in payload and not isinstance(payload.get("replay_source_count"), int):
        invalid_fields.append({"field": "replay_source_count", "reason": "expected_int"})
    if "reconstruction_consistent" in payload and not isinstance(payload.get("reconstruction_consistent"), bool):
        invalid_fields.append({"field": "reconstruction_consistent", "reason": "expected_bool"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(RECONSTRUCTION_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def validate_runtime_recovery_reconstruction(
    reconstruction_contract: Any,
    *,
    transaction_contract: Any | None = None,
    expected_evidence_chain: Iterable[Any] | None = None,
    rollback_reconstruction: Any | None = None,
    seal_reconstruction: Any | None = None,
) -> Dict[str, Any]:
    reconstruction = _mapping(reconstruction_contract)
    contract_validation = validate_runtime_recovery_reconstruction_contract(reconstruction)
    issues: List[Dict[str, Any]] = []

    if not contract_validation["ok"]:
        issues.append(
            {
                "kind": "reconstruction_contract_invalid",
                "missing_fields": copy.deepcopy(contract_validation["missing_fields"]),
                "invalid_fields": copy.deepcopy(contract_validation["invalid_fields"]),
            }
        )

    source_chain = [
        copy.deepcopy(item)
        for item in reconstruction.get("source_evidence_chain", [])
        if isinstance(item, dict)
    ]
    expected_chain = [
        copy.deepcopy(item)
        for item in (expected_evidence_chain or [])
        if isinstance(item, dict)
    ]
    if not source_chain:
        issues.append({"kind": "missing_evidence_reconstruction"})

    replay_order_valid = _replay_order_valid(source_chain)
    if not replay_order_valid:
        issues.append({"kind": "replay_order_mismatch"})

    if expected_chain and _evidence_ids(source_chain) != _evidence_ids(expected_chain):
        issues.append({"kind": "reconstruction_evidence_order_diverged"})

    transaction_id = _text(reconstruction.get("source_transaction_id"))
    transaction = _mapping(transaction_contract)
    expected_transaction_id = _text(transaction.get("transaction_id"))
    if expected_transaction_id and transaction_id != expected_transaction_id:
        issues.append(
            {
                "kind": "transaction_reconstruction_mismatch",
                "source_transaction_id": transaction_id,
                "expected_transaction_id": expected_transaction_id,
            }
        )
    for index, evidence in enumerate(source_chain):
        if transaction_id and _text(evidence.get("transaction_id")) != transaction_id:
            issues.append(
                {
                    "kind": "transaction_evidence_divergence",
                    "index": index,
                    "evidence_id": _text(evidence.get("evidence_id")),
                }
            )

    reconstruction_consistent = reconstruction.get("reconstruction_consistent") is True
    if not reconstruction_consistent or _text(reconstruction.get("reconstruction_state")) != RECONSTRUCTION_CONSISTENT:
        issues.append({"kind": "reconstruction_inconsistency"})

    rollback_valid = _rollback_reconstruction_valid(rollback_reconstruction, transaction)
    if not rollback_valid:
        issues.append({"kind": "invalid_rollback_reconstruction"})

    seal_valid = _seal_reconstruction_valid(seal_reconstruction, source_chain, transaction)
    if not seal_valid:
        issues.append({"kind": "invalid_seal_reconstruction"})

    divergence_detected = any(
        _text(item.get("kind")) in {
            "reconstruction_evidence_order_diverged",
            "transaction_reconstruction_mismatch",
            "transaction_evidence_divergence",
            "reconstruction_inconsistency",
        }
        for item in issues
        if isinstance(item, dict)
    )
    state = _reconstruction_state(issues, reconstruction)
    previous_status = reconstruction.get("previous_status") or reconstruction.get("from_status") or "unknown"
    transition = runtime_status_transition_payload(
        status_from_recovery_state(previous_status),
        status_from_recovery_state(state),
        source="runtime_recovery_reconstruction",
    )
    constitution = recovery_constitution_summary(
        recovery_id=_text(reconstruction.get("reconstruction_id")),
        recovery_lineage=[
            item
            for item in (
                _text(reconstruction.get("reconstruction_id")),
                transaction_id,
            )
            if item
        ],
        recovery_source_state={
            "source_transaction_id": transaction_id,
            "source_evidence_count": len(source_chain),
        },
        recovery_target_state=reconstruction.get("reconstructed_runtime_state"),
        transition=transition,
        transition_evidence=transition["transition_evidence"],
    )
    return {
        "ok": not issues,
        "schema_version": SCHEMA_VERSION,
        "reconstruction_id": _text(reconstruction.get("reconstruction_id")),
        "source_transaction_id": transaction_id,
        "reconstruction_state": state,
        "canonical_status": status_from_recovery_state(state),
        "canonical_from_status": transition["from_status"],
        "canonical_to_status": transition["to_status"],
        "transition_allowed": transition["allowed"],
        "transition_regression": transition["regression"],
        "transition_reason": transition["transition_reason"],
        "transition_trigger": transition["transition_trigger"],
        "transition_source": transition["transition_source"],
        "transition_evidence": transition["transition_evidence"],
        "enforcement_readiness": transition["enforcement_readiness"],
        "enforcement_classification": transition["enforcement_classification"],
        "enforcement_reason": transition["enforcement_reason"],
        "safe_to_enforce": transition["safe_to_enforce"],
        "review_required": transition["review_required"] or constitution["review_required"],
        "block_recommended": transition["block_recommended"] or constitution["block_recommended"],
        "constitutional_continuity": constitution["constitutional_continuity"],
        "continuity_verified": constitution["continuity_verified"],
        "continuity_break": constitution["continuity_break"],
        "recovery_constitution_status": constitution["recovery_constitution_status"],
        "enforcement_visibility": constitution["enforcement_visibility"],
        "enforcement_snapshot": constitution["enforcement_snapshot"],
        "reconstruction_consistent": not issues and reconstruction_consistent,
        "replay_order_valid": replay_order_valid,
        "reconstruction_divergence_detected": divergence_detected,
        "rollback_reconstruction_valid": rollback_valid,
        "seal_reconstruction_valid": seal_valid,
        "replay_source_count": len(source_chain),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def recovery_constitution_summary(
    *,
    recovery_id: str = "",
    recovery_lineage: list[str] | None = None,
    recovery_source_state: Any = None,
    recovery_target_state: Any = None,
    transition: dict[str, Any] | None = None,
    transition_evidence: dict[str, Any] | None = None,
    enforcement_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Summarize recovery constitutional continuity without blocking recovery."""

    lineage = [str(item) for item in (recovery_lineage or []) if _text(item)]
    source_state = copy.deepcopy(recovery_source_state)
    target_state = copy.deepcopy(recovery_target_state)
    transition_payload = copy.deepcopy(transition) if isinstance(transition, dict) else {}
    evidence = (
        copy.deepcopy(transition_evidence)
        if isinstance(transition_evidence, dict)
        else copy.deepcopy(transition_payload.get("transition_evidence"))
        if isinstance(transition_payload.get("transition_evidence"), dict)
        else {}
    )
    snapshot = (
        copy.deepcopy(enforcement_snapshot)
        if isinstance(enforcement_snapshot, dict)
        else copy.deepcopy(transition_payload.get("enforcement_decision"))
        if isinstance(transition_payload.get("enforcement_decision"), dict)
        else {}
    )
    meta = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}

    review_reasons: List[str] = []
    block_reasons: List[str] = []
    if not evidence:
        review_reasons.append("missing_recovery_evidence")
    if not lineage:
        review_reasons.append("missing_recovery_lineage")
    if not isinstance(source_state, dict) or not source_state:
        review_reasons.append("missing_recovery_source_state")
    elif int(source_state.get("source_evidence_count") or 0) <= 0:
        review_reasons.append("missing_recovery_evidence")
    if target_state in (None, ""):
        review_reasons.append("missing_recovery_target_state")
    if bool(transition_payload.get("regression")) and not bool(transition_payload.get("allowed")):
        review_reasons.append("recovery_graph_discontinuity")
    if bool(meta.get("recovery_lineage_corrupted") or meta.get("lineage_corruption")):
        block_reasons.append("recovery_lineage_corruption")

    from_status = _text(transition_payload.get("from_status"))
    to_status = _text(transition_payload.get("to_status"))
    forbidden_terminal_targets = {"blocked", "failed", "sealed"}
    if to_status in forbidden_terminal_targets and from_status not in {"", to_status}:
        block_reasons.append("recovery_target_forbidden_terminal_regression")

    status = RECOVERY_CONSTITUTION_CANONICAL
    if block_reasons:
        status = RECOVERY_CONSTITUTION_BLOCK_RECOMMENDED
    elif review_reasons:
        status = RECOVERY_CONSTITUTION_REVIEW_REQUIRED

    continuity_breaks = _sorted_unique([*review_reasons, *block_reasons])
    return {
        "constitutional_continuity": {
            "kind": "runtime_recovery_constitution",
            "recovery_id": _text(recovery_id),
            "recovery_lineage": list(lineage),
            "recovery_source_state": source_state,
            "recovery_target_state": target_state,
            "transition_legal": bool(transition_payload.get("allowed", True)),
            "transition_regression": bool(transition_payload.get("regression", False)),
            "evidence_lineage": copy.deepcopy(evidence),
            "evidence_complete": bool(evidence),
            "enforcement_visibility": bool(snapshot),
            "enforcement_snapshot": copy.deepcopy(snapshot),
            "classification": status,
        },
        "continuity_verified": status == RECOVERY_CONSTITUTION_CANONICAL,
        "continuity_break": ",".join(continuity_breaks),
        "recovery_constitution_status": status,
        "enforcement_visibility": bool(snapshot),
        "enforcement_snapshot": snapshot,
        "legality": status,
        "evidence_complete": bool(evidence),
        "constitutional_classification": status,
        "review_required": status == RECOVERY_CONSTITUTION_REVIEW_REQUIRED,
        "block_recommended": status == RECOVERY_CONSTITUTION_BLOCK_RECOMMENDED,
    }


def _replay_order_valid(source_chain: List[Dict[str, Any]]) -> bool:
    for index, evidence in enumerate(source_chain):
        previous_id = _text(evidence.get("previous_evidence_id"))
        if index == 0:
            if previous_id:
                return False
            continue
        if previous_id != _text(source_chain[index - 1].get("evidence_id")):
            return False
    return True


def _rollback_reconstruction_valid(value: Any, transaction: Mapping[str, Any]) -> bool:
    if transaction.get("rollback_available") is not True:
        return True
    payload = _mapping(value)
    if not payload:
        return False
    return payload.get("valid") is True or payload.get("rollback_reconstruction_valid") is True


def _seal_reconstruction_valid(value: Any, source_chain: List[Dict[str, Any]], transaction: Mapping[str, Any]) -> bool:
    if transaction.get("seal_required") is not True:
        return True
    payload = _mapping(value)
    if not payload:
        return False
    if not (payload.get("valid") is True or payload.get("seal_reconstruction_valid") is True):
        return False
    latest = _text(payload.get("latest_evidence_id") or payload.get("evidence_id"))
    if latest and source_chain and latest != _text(source_chain[-1].get("evidence_id")):
        return False
    return True


def _reconstruction_state(issues: Iterable[Mapping[str, Any]], reconstruction: Mapping[str, Any]) -> str:
    kinds = {_text(item.get("kind")) for item in issues if isinstance(item, dict)}
    if not kinds:
        return RECONSTRUCTION_CONSISTENT
    if "missing_evidence_reconstruction" in kinds:
        return RECONSTRUCTION_FAILED
    if any(kind.endswith("divergence") or "mismatch" in kind or "diverged" in kind for kind in kinds):
        return RECONSTRUCTION_DIVERGED
    return RECONSTRUCTION_INCONSISTENT


def _evidence_ids(chain: Iterable[Mapping[str, Any]]) -> List[str]:
    return [_text(item.get("evidence_id")) for item in chain if isinstance(item, dict)]


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _reconstruction_id(payload: Mapping[str, Any]) -> str:
    return "runtime-recovery-reconstruction-" + _stable_hash(payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    if values is None:
        return []
    return sorted({_text(value) for value in values if _text(value)})


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
