from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "governed_cross_session_handoff_contract.v1"

HANDOFF_READY = "ready"
HANDOFF_ACCEPTED = "accepted"
HANDOFF_REJECTED = "rejected"
HANDOFF_BLOCKED = "blocked"

HANDOFF_STATES: tuple[str, ...] = (
    HANDOFF_READY,
    HANDOFF_ACCEPTED,
    HANDOFF_REJECTED,
    HANDOFF_BLOCKED,
)

HANDOFF_REQUIRED_FIELDS: tuple[str, ...] = (
    "handoff_id",
    "handoff_state",
    "source_session_id",
    "target_session_id",
    "source_replay_session_id",
    "source_continuation_id",
    "parent_governance_chain_valid",
    "lineage_valid",
    "handoff_acceptance_ready",
    "handoff_payload",
    "blocking_issues",
    "reason_codes",
)


def governed_cross_session_handoff_states() -> List[str]:
    return list(HANDOFF_STATES)


def governed_cross_session_handoff_required_fields() -> List[str]:
    return list(HANDOFF_REQUIRED_FIELDS)


def build_governed_cross_session_handoff_contract(
    *,
    continuation_record: Any,
    replay_session_report: Any | None = None,
    execution_session_report: Any | None = None,
    governance_closure_report: Any | None = None,
    target_session_id: str | None = None,
    acceptance_context: Any | None = None,
) -> Dict[str, Any]:
    """Build a data-only governed handoff payload between runtime sessions."""

    continuation = _mapping(continuation_record)
    replay = _mapping(replay_session_report)
    execution = _mapping(execution_session_report)
    closure = _mapping(governance_closure_report)
    acceptance = _mapping(acceptance_context)

    source_session_id = _text(
        continuation.get("source_session_id")
        or execution.get("execution_session_id")
    )
    resolved_target_session_id = _text(
        target_session_id
        or continuation.get("target_session_id")
    )
    replay_session_id = _text(
        continuation.get("replay_session_id")
        or replay.get("replay_session_id")
    )
    continuation_id = _text(continuation.get("continuation_id"))

    lineage = _lineage_chain(
        continuation=continuation,
        execution=execution,
        replay=replay,
        source_session_id=source_session_id,
        replay_session_id=replay_session_id,
        target_session_id=resolved_target_session_id,
    )

    parent_governance_chain_valid = _parent_governance_chain_valid(closure)
    lineage_valid = _lineage_valid(
        lineage,
        source_session_id=source_session_id,
        replay_session_id=replay_session_id,
        target_session_id=resolved_target_session_id,
    )
    replay_valid = _replay_valid(replay)
    continuation_valid = _continuation_valid(continuation)
    acceptance_ready = _handoff_acceptance_ready(acceptance, lineage_valid, parent_governance_chain_valid)

    blocking_issues: List[Dict[str, Any]] = []
    if not source_session_id:
        blocking_issues.append({"kind": "source_session_missing"})
    if not resolved_target_session_id:
        blocking_issues.append({"kind": "target_session_missing"})
    if not replay_session_id:
        blocking_issues.append({"kind": "replay_session_missing"})
    if continuation and not continuation_valid:
        blocking_issues.append({"kind": "continuation_record_invalid"})
    if replay and not replay_valid:
        blocking_issues.append({"kind": "replay_session_invalid"})
    if not parent_governance_chain_valid:
        blocking_issues.append({"kind": "parent_governance_chain_invalid"})
    if not lineage_valid:
        blocking_issues.append({"kind": "handoff_lineage_invalid"})
    if acceptance and not acceptance_ready:
        blocking_issues.append({"kind": "handoff_acceptance_not_ready"})

    blocking_issues = _dedupe_issues(blocking_issues)

    if blocking_issues:
        handoff_state = HANDOFF_BLOCKED
    elif acceptance.get("accepted") is True or _text(acceptance.get("acceptance_state")) == HANDOFF_ACCEPTED:
        handoff_state = HANDOFF_ACCEPTED
    else:
        handoff_state = HANDOFF_READY

    payload = {
        "source_session_id": source_session_id,
        "target_session_id": resolved_target_session_id,
        "source_replay_session_id": replay_session_id,
        "source_continuation_id": continuation_id,
        "lineage_chain": lineage,
        "replay_state": _text(replay.get("replay_state")),
        "source_session_state": _text(execution.get("session_state")),
        "parent_closure_state": _text(closure.get("closure_state")),
        "parent_freeze_candidate": bool(closure.get("runtime_governance_freeze_candidate")),
        "acceptance_context": copy.deepcopy(acceptance),
        "data_only": True,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": "",
        "handoff_state": handoff_state,
        "source_session_id": source_session_id,
        "target_session_id": resolved_target_session_id,
        "source_replay_session_id": replay_session_id,
        "source_continuation_id": continuation_id,
        "parent_governance_chain_valid": parent_governance_chain_valid,
        "lineage_valid": lineage_valid,
        "handoff_acceptance_ready": acceptance_ready,
        "handoff_payload": payload,
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                *_string_list(continuation.get("reason_codes")),
                *_string_list(replay.get("reason_codes")),
                *_string_list(execution.get("reason_codes")),
                *_string_list(closure.get("reason_codes")),
                *_reason_codes_from_issues(blocking_issues),
            ]
        ),
    }
    report["handoff_id"] = _handoff_id(report)
    return report


def validate_governed_cross_session_handoff_contract(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in HANDOFF_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []

    if _text(payload.get("handoff_state")) not in HANDOFF_STATES:
        invalid_fields.append({"field": "handoff_state", "reason": "invalid_state"})

    for field in ("parent_governance_chain_valid", "lineage_valid", "handoff_acceptance_ready"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})

    for field in ("blocking_issues", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})

    if "handoff_payload" in payload and not isinstance(payload.get("handoff_payload"), dict):
        invalid_fields.append({"field": "handoff_payload", "reason": "expected_dict"})

    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(HANDOFF_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def build_governed_cross_session_handoff_summary(handoff_contract: Any) -> Dict[str, Any]:
    report = _mapping(handoff_contract)
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": _text(report.get("handoff_id")),
        "handoff_state": _text(report.get("handoff_state")),
        "source_session_id": _text(report.get("source_session_id")),
        "target_session_id": _text(report.get("target_session_id")),
        "source_replay_session_id": _text(report.get("source_replay_session_id")),
        "source_continuation_id": _text(report.get("source_continuation_id")),
        "parent_governance_chain_valid": bool(report.get("parent_governance_chain_valid")),
        "lineage_valid": bool(report.get("lineage_valid")),
        "handoff_acceptance_ready": bool(report.get("handoff_acceptance_ready")),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
    }


def _parent_governance_chain_valid(closure: Mapping[str, Any]) -> bool:
    if not closure:
        return True
    if closure.get("closure_ready") is True:
        return True
    if closure.get("runtime_governance_freeze_candidate") is True and _text(closure.get("closure_state")) in {"closed", "warning"}:
        return True
    return False


def _continuation_valid(continuation: Mapping[str, Any]) -> bool:
    if not continuation:
        return False
    if continuation.get("continuation_valid") is False:
        return False
    return bool(_text(continuation.get("source_session_id"))) and bool(_text(continuation.get("target_session_id")))


def _replay_valid(replay: Mapping[str, Any]) -> bool:
    if not replay:
        return True
    if replay.get("timeline_replay_valid") is False:
        return False
    if replay.get("checkpoint_replay_valid") is False:
        return False
    if _text(replay.get("replay_state")) in {"blocked", "failed"}:
        return False
    return True


def _handoff_acceptance_ready(acceptance: Mapping[str, Any], lineage_valid: bool, parent_valid: bool) -> bool:
    if not lineage_valid or not parent_valid:
        return False
    if not acceptance:
        return True
    if acceptance.get("blocked") is True:
        return False
    if _text(acceptance.get("acceptance_state")) in {"blocked", "rejected"}:
        return False
    return True


def _lineage_chain(
    *,
    continuation: Mapping[str, Any],
    execution: Mapping[str, Any],
    replay: Mapping[str, Any],
    source_session_id: str,
    replay_session_id: str,
    target_session_id: str,
) -> List[str]:
    lineage = _string_list(continuation.get("lineage_chain"))
    if lineage:
        return lineage
    return [
        item
        for item in [
            source_session_id or _text(execution.get("execution_session_id")),
            replay_session_id or _text(replay.get("replay_session_id")),
            target_session_id,
        ]
        if item
    ]


def _lineage_valid(lineage: Iterable[Any], *, source_session_id: str, replay_session_id: str, target_session_id: str) -> bool:
    chain = _string_list(lineage)
    if len(chain) < 3:
        return False
    if source_session_id and chain[0] != source_session_id:
        return False
    if replay_session_id and replay_session_id not in chain:
        return False
    if target_session_id and chain[-1] != target_session_id:
        return False
    return True


def _handoff_id(report: Mapping[str, Any]) -> str:
    payload = {
        "handoff_state": report.get("handoff_state"),
        "source_session_id": report.get("source_session_id"),
        "target_session_id": report.get("target_session_id"),
        "source_replay_session_id": report.get("source_replay_session_id"),
        "source_continuation_id": report.get("source_continuation_id"),
        "parent_governance_chain_valid": report.get("parent_governance_chain_valid"),
        "lineage_valid": report.get("lineage_valid"),
        "handoff_acceptance_ready": report.get("handoff_acceptance_ready"),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-cross-session-handoff-" + _stable_hash(payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


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
    for issue in issues or []:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
