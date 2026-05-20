from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "governed_runtime_mutation_transaction.v1"

TRANSACTION_PREPARED = "prepared"
TRANSACTION_AWAITING_REVIEW = "awaiting_review"
TRANSACTION_APPROVED = "approved"
TRANSACTION_EXECUTING = "executing"
TRANSACTION_VERIFICATION_PENDING = "verification_pending"
TRANSACTION_SEALED = "sealed"
TRANSACTION_ROLLED_BACK = "rolled_back"
TRANSACTION_BLOCKED = "blocked"
TRANSACTION_FAILED = "failed"

TRANSACTION_STATES: tuple[str, ...] = (
    TRANSACTION_PREPARED,
    TRANSACTION_AWAITING_REVIEW,
    TRANSACTION_APPROVED,
    TRANSACTION_EXECUTING,
    TRANSACTION_VERIFICATION_PENDING,
    TRANSACTION_SEALED,
    TRANSACTION_ROLLED_BACK,
    TRANSACTION_BLOCKED,
    TRANSACTION_FAILED,
)

TERMINAL_STATES = {
    TRANSACTION_SEALED,
    TRANSACTION_ROLLED_BACK,
    TRANSACTION_BLOCKED,
    TRANSACTION_FAILED,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "": {TRANSACTION_PREPARED},
    TRANSACTION_PREPARED: {TRANSACTION_AWAITING_REVIEW, TRANSACTION_BLOCKED},
    TRANSACTION_AWAITING_REVIEW: {TRANSACTION_APPROVED, TRANSACTION_BLOCKED},
    TRANSACTION_APPROVED: {TRANSACTION_EXECUTING, TRANSACTION_BLOCKED},
    TRANSACTION_EXECUTING: {TRANSACTION_VERIFICATION_PENDING, TRANSACTION_FAILED, TRANSACTION_ROLLED_BACK},
    TRANSACTION_VERIFICATION_PENDING: {TRANSACTION_SEALED, TRANSACTION_FAILED, TRANSACTION_ROLLED_BACK},
    TRANSACTION_SEALED: set(),
    TRANSACTION_ROLLED_BACK: set(),
    TRANSACTION_BLOCKED: set(),
    TRANSACTION_FAILED: set(),
}

MUTATION_TRANSACTION_REQUIRED_FIELDS: tuple[str, ...] = (
    "transaction_id",
    "transaction_state",
    "execution_intent",
    "required_capabilities",
    "approval_chain_id",
    "verification_required",
    "rollback_available",
    "seal_required",
)


def governed_runtime_mutation_transaction_states() -> List[str]:
    return list(TRANSACTION_STATES)


def governed_runtime_mutation_transaction_required_fields() -> List[str]:
    return list(MUTATION_TRANSACTION_REQUIRED_FIELDS)


def build_governed_runtime_mutation_transaction_contract(
    *,
    transaction_id: str = "",
    transaction_state: str = TRANSACTION_PREPARED,
    execution_intent: str = "",
    required_capabilities: Iterable[Any] | None = None,
    approval_chain_id: str = "",
    verification_required: bool = True,
    rollback_available: bool = True,
    seal_required: bool = True,
) -> Dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "transaction_id": _text(transaction_id),
        "transaction_state": _text(transaction_state),
        "execution_intent": _text(execution_intent),
        "required_capabilities": _sorted_unique(required_capabilities or []),
        "approval_chain_id": _text(approval_chain_id),
        "verification_required": bool(verification_required),
        "rollback_available": bool(rollback_available),
        "seal_required": bool(seal_required),
    }
    if not payload["transaction_id"]:
        payload["transaction_id"] = _transaction_id(payload)
    return payload


def validate_governed_runtime_mutation_transaction_contract(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in MUTATION_TRANSACTION_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("transaction_state")) not in TRANSACTION_STATES:
        invalid_fields.append({"field": "transaction_state", "reason": "invalid_state"})
    if "required_capabilities" in payload and not isinstance(payload.get("required_capabilities"), list):
        invalid_fields.append({"field": "required_capabilities", "reason": "expected_list"})
    for field in ("verification_required", "rollback_available", "seal_required"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(MUTATION_TRANSACTION_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def validate_governed_runtime_mutation_transaction_lifecycle(
    transaction_contract: Any,
    *,
    previous_transaction_state: str | None = None,
    verification_report: Any | None = None,
    rollback_report: Any | None = None,
    seal_report: Any | None = None,
    replay_report: Any | None = None,
) -> Dict[str, Any]:
    transaction = _mapping(transaction_contract)
    contract_validation = validate_governed_runtime_mutation_transaction_contract(transaction)
    state = _text(transaction.get("transaction_state"))
    previous = _text(previous_transaction_state)
    issues: List[Dict[str, Any]] = []

    if not contract_validation["ok"]:
        issues.append(
            {
                "kind": "transaction_contract_invalid",
                "missing_fields": copy.deepcopy(contract_validation["missing_fields"]),
                "invalid_fields": copy.deepcopy(contract_validation["invalid_fields"]),
            }
        )

    transition_valid = _transition_valid(previous, state)
    if not transition_valid:
        issues.append({"kind": "invalid_transaction_state_transition", "from": previous, "to": state})

    verification_state = _verification_state(transaction, verification_report)
    if verification_state in {"verification_missing", "verification_failed"}:
        issues.append({"kind": verification_state})

    rollback_state = _rollback_state(transaction, rollback_report)
    if rollback_state in {"rollback_unavailable", "rollback_not_ready"}:
        issues.append({"kind": rollback_state})

    seal_state = _seal_state(transaction, seal_report)
    if seal_state in {"seal_missing", "seal_not_ready"}:
        issues.append({"kind": seal_state})

    replay_consistency_state = _replay_consistency_state(replay_report)
    if replay_consistency_state in {"replay_inconsistent", "replay_missing"}:
        issues.append({"kind": replay_consistency_state})

    return {
        "ok": not issues,
        "schema_version": SCHEMA_VERSION,
        "transaction_id": _text(transaction.get("transaction_id")),
        "transaction_state": state,
        "previous_transaction_state": previous,
        "transition_valid": transition_valid,
        "rollback_state": rollback_state,
        "verification_state": verification_state,
        "seal_state": seal_state,
        "replay_consistency_state": replay_consistency_state,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def _transition_valid(previous: str, current: str) -> bool:
    if current not in TRANSACTION_STATES:
        return False
    if not previous and current == TRANSACTION_PREPARED:
        return True
    return current in ALLOWED_TRANSITIONS.get(previous, set())


def _verification_state(transaction: Mapping[str, Any], verification_report: Any) -> str:
    state = _text(transaction.get("transaction_state"))
    if transaction.get("verification_required") is not True:
        return "verification_not_required"
    if state not in {TRANSACTION_SEALED, TRANSACTION_VERIFICATION_PENDING, TRANSACTION_FAILED}:
        return "verification_not_due"
    report = _mapping(verification_report)
    if not report:
        return "verification_missing"
    if report.get("ok") is True or report.get("verified") is True or _text(report.get("verification_state")) in {"verified", "passed"}:
        return "verified"
    return "verification_failed"


def _rollback_state(transaction: Mapping[str, Any], rollback_report: Any) -> str:
    state = _text(transaction.get("transaction_state"))
    if transaction.get("rollback_available") is not True:
        return "rollback_unavailable"
    report = _mapping(rollback_report)
    if state in {TRANSACTION_EXECUTING, TRANSACTION_VERIFICATION_PENDING, TRANSACTION_FAILED, TRANSACTION_ROLLED_BACK}:
        if not report:
            return "rollback_not_ready"
        if report.get("available") is True or report.get("rollback_available") is True or _text(report.get("rollback_state")) in {"ready", "available", "rolled_back"}:
            return "rollback_ready" if state != TRANSACTION_ROLLED_BACK else "rolled_back"
        return "rollback_not_ready"
    return "rollback_ready"


def _seal_state(transaction: Mapping[str, Any], seal_report: Any) -> str:
    state = _text(transaction.get("transaction_state"))
    if transaction.get("seal_required") is not True:
        return "seal_not_required"
    if state != TRANSACTION_SEALED:
        return "seal_pending"
    report = _mapping(seal_report)
    if not report:
        return "seal_missing"
    if report.get("sealed") is True or report.get("seal_ready") is True or _text(report.get("seal_state")) in {"sealed", "ready"}:
        return "sealed"
    return "seal_not_ready"


def _replay_consistency_state(replay_report: Any) -> str:
    report = _mapping(replay_report)
    if not report:
        return "replay_not_checked"
    if report.get("consistent") is True or report.get("replay_consistent") is True or _text(report.get("replay_consistency_state")) in {"consistent", "replay_consistent"}:
        return "replay_consistent"
    if report.get("consistent") is False or report.get("replay_consistent") is False or _text(report.get("replay_consistency_state")) in {"inconsistent", "replay_inconsistent"}:
        return "replay_inconsistent"
    return "replay_missing"


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _transaction_id(payload: Mapping[str, Any]) -> str:
    return "governed-runtime-mutation-transaction-" + _stable_hash(payload)[:16]


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
