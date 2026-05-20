from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "runtime_governance_chain_seal.v1"

GOVERNANCE_CHAIN_SEALABLE = "sealable"
GOVERNANCE_CHAIN_BLOCKED = "blocked"
GOVERNANCE_CHAIN_WARNING = "warning"

GOVERNANCE_CHAIN_SEAL_STATES: tuple[str, ...] = (
    GOVERNANCE_CHAIN_SEALABLE,
    GOVERNANCE_CHAIN_BLOCKED,
    GOVERNANCE_CHAIN_WARNING,
)

SEAL_REQUIRED_FIELDS: tuple[str, ...] = (
    "governance_chain_seal_id",
    "governance_chain_sealable",
    "governance_chain_state",
    "seal_blockers",
    "seal_warnings",
    "seal_summary",
)

_VERIFICATION_BLOCKING_STATES = {
    "verification_missing",
    "verification_failed",
}

_ROLLBACK_BLOCKING_STATES = {
    "rollback_unavailable",
    "rollback_not_ready",
}

_SEAL_BLOCKING_STATES = {
    "seal_missing",
    "seal_not_ready",
}

_REPLAY_BLOCKING_STATES = {
    "replay_inconsistent",
    "replay_missing",
}

_NOT_APPLICABLE_STATES = {
    "",
    "not_applicable",
    "verification_not_applicable",
    "verification_not_required",
    "verification_not_due",
    "rollback_not_applicable",
    "rollback_not_required",
    "rollback_not_due",
    "seal_not_applicable",
    "seal_not_required",
    "seal_not_due",
    "replay_not_applicable",
    "replay_not_required",
    "replay_not_due",
}


def runtime_governance_chain_seal_required_fields() -> List[str]:
    return list(SEAL_REQUIRED_FIELDS)


def runtime_governance_chain_seal_states() -> List[str]:
    return list(GOVERNANCE_CHAIN_SEAL_STATES)


def build_runtime_governance_chain_seal_report(
    *,
    boundary_report: Any | None = None,
    boundary_state: str = "",
    execution_intent: str = "",
    capability_grant_state: str = "",
    approval_state: str = "",
    transaction_state: str = "",
    transition_valid: bool | None = None,
    rollback_state: str = "",
    verification_state: str = "",
    seal_state: str = "",
    replay_consistency_state: str = "",
    evidence_chain_valid: bool | None = None,
    evidence_integrity_state: str = "",
    replay_evidence_consistent: bool | None = None,
    evidence_tamper_detected: bool | None = None,
    evidence_seal_valid: bool | None = None,
    reconstruction_state: str = "",
    reconstruction_consistent: bool | None = None,
    replay_order_valid: bool | None = None,
    reconstruction_divergence_detected: bool | None = None,
    rollback_reconstruction_valid: bool | None = None,
    seal_reconstruction_valid: bool | None = None,
    existing_blocking_issues: Iterable[Any] | None = None,
    existing_reason_codes: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Build a deterministic, data-only seal decision for a governed runtime chain."""

    source = _mapping(boundary_report)
    inputs = {
        "boundary_state": _first_text(boundary_state, source.get("boundary_state")),
        "execution_intent": _first_text(execution_intent, source.get("execution_intent")),
        "capability_grant_state": _first_text(capability_grant_state, source.get("capability_grant_state")),
        "approval_state": _first_text(approval_state, source.get("approval_state")),
        "transaction_state": _first_text(transaction_state, source.get("transaction_state")),
        "transition_valid": _first_bool(transition_valid, source.get("transition_valid")),
        "rollback_state": _first_text(rollback_state, source.get("rollback_state")),
        "verification_state": _first_text(verification_state, source.get("verification_state")),
        "seal_state": _first_text(seal_state, source.get("seal_state")),
        "replay_consistency_state": _first_text(replay_consistency_state, source.get("replay_consistency_state")),
        "evidence_chain_valid": _first_bool(evidence_chain_valid, source.get("evidence_chain_valid")),
        "evidence_integrity_state": _first_text(evidence_integrity_state, source.get("evidence_integrity_state")),
        "replay_evidence_consistent": _first_bool(replay_evidence_consistent, source.get("replay_evidence_consistent")),
        "evidence_tamper_detected": _first_bool(evidence_tamper_detected, source.get("evidence_tamper_detected")),
        "evidence_seal_valid": _first_bool(evidence_seal_valid, source.get("evidence_seal_valid")),
        "reconstruction_state": _first_text(reconstruction_state, source.get("reconstruction_state")),
        "reconstruction_consistent": _first_bool(reconstruction_consistent, source.get("reconstruction_consistent")),
        "replay_order_valid": _first_bool(replay_order_valid, source.get("replay_order_valid")),
        "reconstruction_divergence_detected": _first_bool(
            reconstruction_divergence_detected,
            source.get("reconstruction_divergence_detected"),
        ),
        "rollback_reconstruction_valid": _first_bool(
            rollback_reconstruction_valid,
            source.get("rollback_reconstruction_valid"),
        ),
        "seal_reconstruction_valid": _first_bool(
            seal_reconstruction_valid,
            source.get("seal_reconstruction_valid"),
        ),
    }
    existing_issues = [copy.deepcopy(item) for item in (existing_blocking_issues or source.get("blocking_issues", [])) if isinstance(item, dict)]
    existing_reasons = _sorted_unique([*(_string_list(existing_reason_codes)), *(_string_list(source.get("reason_codes")))])

    blockers = _seal_blockers(inputs, existing_issues)
    warnings = _seal_warnings(inputs)
    governance_chain_state = GOVERNANCE_CHAIN_BLOCKED if blockers else GOVERNANCE_CHAIN_WARNING if warnings else GOVERNANCE_CHAIN_SEALABLE
    governance_chain_sealable = governance_chain_state != GOVERNANCE_CHAIN_BLOCKED

    summary = {
        "boundary_state": inputs["boundary_state"],
        "execution_intent": inputs["execution_intent"],
        "capability_grant_state": inputs["capability_grant_state"],
        "approval_state": inputs["approval_state"],
        "transaction_state": inputs["transaction_state"],
        "evidence_integrity_state": inputs["evidence_integrity_state"],
        "reconstruction_state": inputs["reconstruction_state"],
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "reason_codes": _sorted_unique(
            [
                *existing_reasons,
                *_reason_codes_from_issues(blockers),
                *_reason_codes_from_issues(warnings),
            ]
        ),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "governance_chain_seal_id": "",
        "source_boundary_id": _text(source.get("boundary_id")),
        "governance_chain_sealable": governance_chain_sealable,
        "governance_chain_state": governance_chain_state,
        "seal_blockers": blockers,
        "seal_warnings": warnings,
        "seal_summary": summary,
        "decision_inputs": copy.deepcopy(inputs),
    }
    report["governance_chain_seal_id"] = _seal_id(report)
    return report


def validate_runtime_governance_chain_seal_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in SEAL_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("governance_chain_state")) not in GOVERNANCE_CHAIN_SEAL_STATES:
        invalid_fields.append({"field": "governance_chain_state", "reason": "invalid_state"})
    if "governance_chain_sealable" in payload and not isinstance(payload.get("governance_chain_sealable"), bool):
        invalid_fields.append({"field": "governance_chain_sealable", "reason": "expected_bool"})
    for field in ("seal_blockers", "seal_warnings"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    if "seal_summary" in payload and not isinstance(payload.get("seal_summary"), dict):
        invalid_fields.append({"field": "seal_summary", "reason": "expected_dict"})
    if "decision_inputs" in payload and not isinstance(payload.get("decision_inputs"), dict):
        invalid_fields.append({"field": "decision_inputs", "reason": "expected_dict"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(SEAL_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _seal_blockers(inputs: Mapping[str, Any], existing_issues: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    boundary_state = _text(inputs.get("boundary_state"))
    if boundary_state == "blocked":
        blockers.append({"kind": "boundary_blocked"})
    elif boundary_state and boundary_state != "boundary_ready":
        blockers.append({"kind": "boundary_not_ready", "boundary_state": boundary_state})

    capability_state = _text(inputs.get("capability_grant_state"))
    if capability_state and capability_state not in {"grant_valid", "not_applicable"}:
        blockers.append({"kind": "capability_grant_not_valid", "capability_grant_state": capability_state})

    approval_state = _text(inputs.get("approval_state"))
    if approval_state and approval_state not in {"approval_valid", "not_applicable"}:
        blockers.append({"kind": "approval_chain_not_valid", "approval_state": approval_state})

    if inputs.get("transition_valid") is False:
        blockers.append({"kind": "transaction_transition_invalid"})

    verification_state = _text(inputs.get("verification_state"))
    if verification_state in _VERIFICATION_BLOCKING_STATES:
        blockers.append({"kind": verification_state})

    rollback_state = _text(inputs.get("rollback_state"))
    if rollback_state in _ROLLBACK_BLOCKING_STATES:
        blockers.append({"kind": rollback_state})

    seal_state = _text(inputs.get("seal_state"))
    if seal_state in _SEAL_BLOCKING_STATES:
        blockers.append({"kind": seal_state})

    replay_state = _text(inputs.get("replay_consistency_state"))
    if replay_state in _REPLAY_BLOCKING_STATES:
        blockers.append({"kind": replay_state})

    if inputs.get("evidence_chain_valid") is False:
        blockers.append({"kind": "evidence_chain_invalid"})
    if _text(inputs.get("evidence_integrity_state")) in {"missing_chain", "broken_linkage", "tampered", "replay_mismatch", "invalid_seal"}:
        blockers.append({"kind": "evidence_integrity_invalid", "evidence_integrity_state": _text(inputs.get("evidence_integrity_state"))})
    if inputs.get("replay_evidence_consistent") is False:
        blockers.append({"kind": "replay_evidence_inconsistent"})
    if inputs.get("evidence_tamper_detected") is True:
        blockers.append({"kind": "evidence_tamper_detected"})
    if inputs.get("evidence_seal_valid") is False:
        blockers.append({"kind": "evidence_seal_invalid"})

    reconstruction_state = _text(inputs.get("reconstruction_state"))
    if reconstruction_state in {"failed", "inconsistent", "diverged"}:
        blockers.append({"kind": "reconstruction_invalid", "reconstruction_state": reconstruction_state})
    if inputs.get("reconstruction_consistent") is False:
        blockers.append({"kind": "reconstruction_inconsistent"})
    if inputs.get("replay_order_valid") is False:
        blockers.append({"kind": "replay_order_invalid"})
    if inputs.get("reconstruction_divergence_detected") is True:
        blockers.append({"kind": "reconstruction_divergence_detected"})
    if inputs.get("rollback_reconstruction_valid") is False:
        blockers.append({"kind": "rollback_reconstruction_invalid"})
    if inputs.get("seal_reconstruction_valid") is False:
        blockers.append({"kind": "seal_reconstruction_invalid"})

    for issue in existing_issues or []:
        kind = _text(issue.get("kind"))
        if kind and kind not in {"seal_warning", "non_blocking_warning"}:
            blockers.append({"kind": "upstream_blocking_issue", "upstream_kind": kind})
    return _dedupe_issues(blockers)


def _seal_warnings(inputs: Mapping[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    if _text(inputs.get("transaction_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "transaction_not_supplied"})
    if _text(inputs.get("evidence_integrity_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "evidence_chain_not_supplied"})
    if _text(inputs.get("reconstruction_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "reconstruction_not_supplied"})
    if _text(inputs.get("verification_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "verification_not_due_or_not_supplied"})
    if _text(inputs.get("rollback_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "rollback_not_due_or_not_supplied"})
    if _text(inputs.get("seal_state")) in _NOT_APPLICABLE_STATES:
        warnings.append({"kind": "seal_not_due_or_not_supplied"})
    return _dedupe_issues(warnings)


def _seal_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_boundary_id": report.get("source_boundary_id"),
        "governance_chain_sealable": report.get("governance_chain_sealable"),
        "governance_chain_state": report.get("governance_chain_state"),
        "seal_blockers": report.get("seal_blockers", []),
        "seal_warnings": report.get("seal_warnings", []),
        "seal_summary": report.get("seal_summary", {}),
        "decision_inputs": report.get("decision_inputs", {}),
    }
    return "runtime-governance-chain-seal-" + _stable_hash(payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _first_text(primary: Any, fallback: Any) -> str:
    text = _text(primary)
    return text if text else _text(fallback)


def _first_bool(primary: Any, fallback: Any) -> bool | None:
    if isinstance(primary, bool):
        return primary
    if isinstance(fallback, bool):
        return fallback
    return None


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (dict, bytes)):
        values = list(value)
    else:
        values = []
    return [_text(item) for item in values if _text(item)]


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    if values is None:
        return []
    return sorted({_text(value) for value in values if _text(value)})


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
