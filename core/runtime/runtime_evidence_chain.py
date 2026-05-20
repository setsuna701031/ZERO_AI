from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "runtime_evidence_chain.v1"

EVIDENCE_INTEGRITY_VALID = "valid"
EVIDENCE_INTEGRITY_MISSING = "missing_chain"
EVIDENCE_INTEGRITY_BROKEN = "broken_linkage"
EVIDENCE_INTEGRITY_TAMPERED = "tampered"
EVIDENCE_INTEGRITY_REPLAY_MISMATCH = "replay_mismatch"
EVIDENCE_INTEGRITY_INVALID_SEAL = "invalid_seal"

EVIDENCE_REQUIRED_FIELDS: tuple[str, ...] = (
    "evidence_id",
    "transaction_id",
    "execution_intent",
    "boundary_state",
    "approval_chain_id",
    "capability_grant_id",
    "verification_state",
    "rollback_state",
    "seal_state",
    "timestamp",
    "previous_evidence_id",
    "evidence_hash",
    "evidence_signature",
)


def runtime_evidence_chain_required_fields() -> List[str]:
    return list(EVIDENCE_REQUIRED_FIELDS)


def build_runtime_evidence_record(
    *,
    transaction_id: str,
    execution_intent: str,
    boundary_state: str,
    approval_chain_id: str = "",
    capability_grant_id: str = "",
    verification_state: str = "",
    rollback_state: str = "",
    seal_state: str = "",
    previous_evidence_id: str = "",
    timestamp: str | None = None,
) -> Dict[str, Any]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": "",
        "transaction_id": _text(transaction_id),
        "execution_intent": _text(execution_intent),
        "boundary_state": _text(boundary_state),
        "approval_chain_id": _text(approval_chain_id),
        "capability_grant_id": _text(capability_grant_id),
        "verification_state": _text(verification_state),
        "rollback_state": _text(rollback_state),
        "seal_state": _text(seal_state),
        "timestamp": _text(timestamp) or datetime.now(UTC).isoformat(),
        "previous_evidence_id": _text(previous_evidence_id),
        "evidence_hash": "",
        "evidence_signature": "",
    }
    record["evidence_hash"] = compute_runtime_evidence_hash(record)
    record["evidence_id"] = "runtime-evidence-" + record["evidence_hash"][:16]
    record["evidence_signature"] = compute_runtime_evidence_signature(record)
    return record


def compute_runtime_evidence_hash(record: Any) -> str:
    payload = _evidence_hash_payload(_mapping(record))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def compute_runtime_evidence_signature(record: Any) -> str:
    payload = {
        "evidence_id": _text(_mapping(record).get("evidence_id")),
        "evidence_hash": _text(_mapping(record).get("evidence_hash")),
    }
    return "runtime-evidence-signature-" + _stable_hash(payload)[:24]


def validate_runtime_evidence_record(record: Any) -> Dict[str, Any]:
    payload = _mapping(record)
    missing = [field for field in EVIDENCE_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if payload:
        expected_hash = compute_runtime_evidence_hash(payload)
        if _text(payload.get("evidence_hash")) != expected_hash:
            invalid_fields.append({"field": "evidence_hash", "reason": "hash_mismatch"})
        if _text(payload.get("evidence_signature")) != compute_runtime_evidence_signature(payload):
            invalid_fields.append({"field": "evidence_signature", "reason": "signature_mismatch"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(EVIDENCE_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(record, dict) else type(record).__name__,
    }


def validate_runtime_evidence_chain(
    evidence_records: Iterable[Any] | None,
    *,
    transaction_id: str = "",
    replay_evidence: Any | None = None,
    seal_evidence: Any | None = None,
) -> Dict[str, Any]:
    records = [copy.deepcopy(item) for item in (evidence_records or []) if isinstance(item, dict)]
    issues: List[Dict[str, Any]] = []

    if not records:
        issues.append({"kind": "missing_evidence_chain"})

    for index, record in enumerate(records):
        validation = validate_runtime_evidence_record(record)
        if not validation["ok"]:
            issues.append(
                {
                    "kind": "tampered_evidence",
                    "index": index,
                    "evidence_id": _text(record.get("evidence_id")),
                    "invalid_fields": copy.deepcopy(validation["invalid_fields"]),
                    "missing_fields": copy.deepcopy(validation["missing_fields"]),
                }
            )
        if transaction_id and _text(record.get("transaction_id")) != _text(transaction_id):
            issues.append(
                {
                    "kind": "transaction_evidence_mismatch",
                    "index": index,
                    "evidence_id": _text(record.get("evidence_id")),
                }
            )
        if index == 0:
            if _text(record.get("previous_evidence_id")):
                issues.append({"kind": "broken_evidence_linkage", "index": index, "reason": "first_record_has_previous"})
        else:
            previous = records[index - 1]
            if _text(record.get("previous_evidence_id")) != _text(previous.get("evidence_id")):
                issues.append(
                    {
                        "kind": "broken_evidence_linkage",
                        "index": index,
                        "expected_previous_evidence_id": _text(previous.get("evidence_id")),
                        "actual_previous_evidence_id": _text(record.get("previous_evidence_id")),
                    }
                )

    replay_state = _replay_evidence_state(records, replay_evidence)
    if replay_state == "replay_evidence_mismatch":
        issues.append({"kind": "replay_evidence_mismatch"})

    seal_valid = _seal_evidence_valid(records, seal_evidence)
    if not seal_valid:
        issues.append({"kind": "invalid_seal_evidence"})

    evidence_tamper_detected = any(item.get("kind") == "tampered_evidence" for item in issues)
    integrity_state = _integrity_state(issues)
    return {
        "ok": not issues,
        "schema_version": SCHEMA_VERSION,
        "evidence_chain_valid": not issues,
        "evidence_integrity_state": integrity_state,
        "replay_evidence_consistent": replay_state != "replay_evidence_mismatch",
        "evidence_tamper_detected": evidence_tamper_detected,
        "evidence_seal_valid": seal_valid,
        "latest_evidence_id": _text(records[-1].get("evidence_id")) if records else "",
        "evidence_count": len(records),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def _evidence_hash_payload(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        field: _text(record.get(field))
        for field in EVIDENCE_REQUIRED_FIELDS
        if field not in {"evidence_id", "evidence_hash", "evidence_signature"}
    }


def _replay_evidence_state(records: List[Dict[str, Any]], replay_evidence: Any) -> str:
    replay = _mapping(replay_evidence)
    if not replay:
        return "replay_not_checked"
    expected_latest = _text(replay.get("latest_evidence_id") or replay.get("evidence_id"))
    if expected_latest and records and expected_latest != _text(records[-1].get("evidence_id")):
        return "replay_evidence_mismatch"
    if replay.get("consistent") is False or replay.get("replay_evidence_consistent") is False:
        return "replay_evidence_mismatch"
    return "replay_evidence_consistent"


def _seal_evidence_valid(records: List[Dict[str, Any]], seal_evidence: Any) -> bool:
    seal = _mapping(seal_evidence)
    if not seal:
        return True
    expected_latest = _text(seal.get("latest_evidence_id") or seal.get("evidence_id"))
    if expected_latest and records and expected_latest != _text(records[-1].get("evidence_id")):
        return False
    if seal.get("sealed") is False or seal.get("evidence_seal_valid") is False:
        return False
    return True


def _integrity_state(issues: Iterable[Mapping[str, Any]]) -> str:
    kinds = {_text(item.get("kind")) for item in issues if isinstance(item, dict)}
    if "tampered_evidence" in kinds:
        return EVIDENCE_INTEGRITY_TAMPERED
    if "broken_evidence_linkage" in kinds:
        return EVIDENCE_INTEGRITY_BROKEN
    if "replay_evidence_mismatch" in kinds or "transaction_evidence_mismatch" in kinds:
        return EVIDENCE_INTEGRITY_REPLAY_MISMATCH
    if "invalid_seal_evidence" in kinds:
        return EVIDENCE_INTEGRITY_INVALID_SEAL
    if "missing_evidence_chain" in kinds:
        return EVIDENCE_INTEGRITY_MISSING
    return EVIDENCE_INTEGRITY_VALID


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


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
