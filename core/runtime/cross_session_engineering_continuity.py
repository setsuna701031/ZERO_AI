from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.autonomous_continuation_policy import (
    ACTION_NO_ACTION,
    ACTION_PLANNER_HANDOFF_RECOMMENDED,
    ACTION_REPAIR_RECOMMENDED,
    ACTION_REPLAY_RECOMMENDED,
    POLICY_ID as CONTINUATION_POLICY_ID,
    STATE_BLOCKED,
    STATE_NEEDS_REVIEW,
    STATE_SAFE_TO_CONTINUE,
    build_autonomous_continuation_recommendation,
    build_planner_handoff_payload as build_policy_planner_handoff_payload,
)
from core.runtime.execution_landing_consistency import (
    build_execution_landing_consistency_report,
)
from core.runtime.runtime_forensic_stack import (
    summarize_runtime_forensic_stack,
)


HANDOFF_POLICY_ID = "cross_session_engineering_continuity.v1"

HANDOFF_REQUIRED_FIELDS: tuple[str, ...] = (
    "handoff_id",
    "source_session_id",
    "source_report_id",
    "continuation_state",
    "recommended_actions",
    "blocking_issues",
    "affected_repair_chain_ids",
    "next_session_startup_hints",
    "planner_handoff_payload",
    "handoff_valid",
    "reason_codes",
)

VALID_CONTINUATION_STATES: tuple[str, ...] = (
    STATE_SAFE_TO_CONTINUE,
    STATE_NEEDS_REVIEW,
    STATE_BLOCKED,
)


def cross_session_handoff_required_fields() -> List[str]:
    return list(HANDOFF_REQUIRED_FIELDS)


def summarize_previous_session_engineering_state(
    forensic_report: Any,
    *,
    source_session_id: str = "",
) -> Dict[str, Any]:
    """Summarize previous-session engineering state from read-only forensic data."""

    report = _mapping(forensic_report)
    summary = summarize_runtime_forensic_stack(report)
    return {
        "policy_id": HANDOFF_POLICY_ID,
        "source_session_id": _text(source_session_id) or _latest_session_id(report),
        "source_report_id": _text(report.get("report_id") or summary.get("report_id")),
        "stack_version": _text(summary.get("stack_version")),
        "session_count": _safe_int(summary.get("session_count")),
        "replay_count": _safe_int(summary.get("replay_count")),
        "repair_chain_count": _safe_int(summary.get("repair_chain_count")),
        "orphan_session_count": _safe_int(summary.get("orphan_session_count")),
        "replay_divergence_count": _safe_int(summary.get("replay_divergence_count")),
        "chain_break_count": _safe_int(summary.get("chain_break_count")),
        "affected_repair_chain_ids": _sorted_unique(summary.get("repair_chain_ids")),
        "source_record_count": _safe_int(summary.get("source_record_count")),
    }


def generate_next_session_startup_hints(
    continuation_recommendation: Any,
    *,
    previous_session_state: Any | None = None,
) -> List[Dict[str, Any]]:
    """Generate deterministic next-session startup hints without invoking runtime actors."""

    recommendation = _mapping(continuation_recommendation)
    previous_state = _mapping(previous_session_state)
    state = _text(recommendation.get("continuation_state")) or STATE_SAFE_TO_CONTINUE
    reason_codes = _string_list(recommendation.get("reason_codes"))
    affected = _sorted_unique(
        [
            *_string_list(previous_state.get("affected_repair_chain_ids")),
            *_string_list(recommendation.get("affected_repair_chain_ids")),
        ]
    )
    hints: List[Dict[str, Any]] = [
        {
            "hint_type": "load_previous_engineering_state",
            "source_report_id": _text(
                recommendation.get("input_report_id") or previous_state.get("source_report_id")
            ),
            "source_session_id": _text(previous_state.get("source_session_id")),
        }
    ]
    if state == STATE_BLOCKED:
        hints.append(
            {
                "hint_type": "resolve_blocking_issues_before_continuation",
                "reason_codes": reason_codes,
            }
        )
    elif state == STATE_NEEDS_REVIEW:
        hints.append(
            {
                "hint_type": "review_recommended_actions_before_continuation",
                "reason_codes": reason_codes,
            }
        )
    else:
        hints.append(
            {
                "hint_type": "safe_to_continue_without_repair",
                "reason_codes": [],
            }
        )
    if affected:
        hints.append(
            {
                "hint_type": "preserve_repair_chain_context",
                "affected_repair_chain_ids": affected,
            }
        )
    return hints


def build_cross_session_planner_handoff_payload(
    continuation_recommendation: Any,
    *,
    source_session_id: str = "",
) -> Dict[str, Any]:
    """Build a planner handoff payload as data only; this never calls a planner."""

    recommendation = _mapping(continuation_recommendation)
    existing = _mapping(recommendation.get("planner_handoff_payload"))
    if existing:
        payload = copy.deepcopy(existing)
    else:
        actions = [
            action
            for action in _list(recommendation.get("recommended_actions"))
            if _text(action.get("action_type"))
            in {
                ACTION_REPAIR_RECOMMENDED,
                ACTION_REPLAY_RECOMMENDED,
                ACTION_PLANNER_HANDOFF_RECOMMENDED,
            }
        ]
        payload = (
            build_policy_planner_handoff_payload(
                actions,
                input_report_id=_text(recommendation.get("input_report_id")),
                affected_repair_chain_ids=_string_list(recommendation.get("affected_repair_chain_ids")),
            )
            if actions and _text(recommendation.get("continuation_state")) == STATE_NEEDS_REVIEW
            else {}
        )
    if not payload:
        return {}
    payload["source_session_id"] = _text(source_session_id)
    payload["planner_invoked"] = False
    return payload


def build_cross_session_handoff_payload(
    *,
    source_session_id: str = "",
    forensic_report: Any | None = None,
    continuation_recommendation: Any | None = None,
    landing_consistency_report: Any | None = None,
) -> Dict[str, Any]:
    """Convert continuation policy output into a read-only cross-session handoff."""

    report = _mapping(forensic_report)
    previous_state = (
        summarize_previous_session_engineering_state(report, source_session_id=source_session_id)
        if report
        else {
            "policy_id": HANDOFF_POLICY_ID,
            "source_session_id": _text(source_session_id),
            "source_report_id": "",
            "affected_repair_chain_ids": [],
        }
    )
    recommendation = (
        _mapping(continuation_recommendation)
        if continuation_recommendation is not None
        else build_autonomous_continuation_recommendation(
            report,
            landing_consistency_report=(
                _landing_consistency_report(landing_consistency_report)
                if landing_consistency_report is not None
                else None
            ),
        )
    )
    source_report_id = _text(
        recommendation.get("input_report_id") or previous_state.get("source_report_id")
    )
    affected_repair_chain_ids = _sorted_unique(
        [
            *_string_list(previous_state.get("affected_repair_chain_ids")),
            *_string_list(recommendation.get("affected_repair_chain_ids")),
        ]
    )
    planner_handoff_payload = build_cross_session_planner_handoff_payload(
        recommendation,
        source_session_id=_text(previous_state.get("source_session_id")),
    )
    payload = {
        "policy_id": HANDOFF_POLICY_ID,
        "continuation_policy_id": _text(recommendation.get("policy_id")) or CONTINUATION_POLICY_ID,
        "handoff_id": "",
        "source_session_id": _text(previous_state.get("source_session_id")) or _text(source_session_id),
        "source_report_id": source_report_id,
        "continuation_state": _text(recommendation.get("continuation_state")) or STATE_SAFE_TO_CONTINUE,
        "recommended_actions": copy.deepcopy(recommendation.get("recommended_actions", [])),
        "blocking_issues": copy.deepcopy(recommendation.get("blocking_issues", [])),
        "affected_repair_chain_ids": affected_repair_chain_ids,
        "previous_session_engineering_state": copy.deepcopy(previous_state),
        "next_session_startup_hints": generate_next_session_startup_hints(
            recommendation,
            previous_session_state=previous_state,
        ),
        "planner_handoff_payload": planner_handoff_payload,
        "handoff_valid": False,
        "reason_codes": _sorted_unique(recommendation.get("reason_codes")),
    }
    payload["handoff_id"] = _handoff_id(payload)
    validation = validate_cross_session_handoff_payload(payload)
    payload["handoff_valid"] = bool(validation["ok"])
    return payload


def validate_cross_session_handoff_payload(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [
        field
        for field in HANDOFF_REQUIRED_FIELDS
        if field not in payload
    ]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("continuation_state")) not in VALID_CONTINUATION_STATES:
        invalid_fields.append(
            {
                "field": "continuation_state",
                "reason": "invalid_continuation_state",
            }
        )
    for field in (
        "recommended_actions",
        "blocking_issues",
        "affected_repair_chain_ids",
        "next_session_startup_hints",
        "reason_codes",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    if "planner_handoff_payload" in payload and not isinstance(payload.get("planner_handoff_payload"), dict):
        invalid_fields.append({"field": "planner_handoff_payload", "reason": "expected_dict"})
    if _mapping(payload.get("planner_handoff_payload")).get("planner_invoked") is True:
        invalid_fields.append({"field": "planner_handoff_payload", "reason": "planner_invoked_must_be_false"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": HANDOFF_POLICY_ID,
        "required_fields": list(HANDOFF_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _latest_session_id(report: Mapping[str, Any]) -> str:
    entries = report.get("timeline_entries")
    if not isinstance(entries, list):
        evidence = _mapping(report.get("evidence_bundle"))
        entries = evidence.get("timeline")
    if not isinstance(entries, list):
        return ""
    session_ids = [
        _text(entry.get("session_id"))
        for entry in entries
        if isinstance(entry, dict) and _text(entry.get("session_id"))
    ]
    return session_ids[-1] if session_ids else ""


def _landing_consistency_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _handoff_id(payload: Mapping[str, Any]) -> str:
    stable_payload = {
        "policy_id": payload.get("policy_id"),
        "source_session_id": payload.get("source_session_id"),
        "source_report_id": payload.get("source_report_id"),
        "continuation_state": payload.get("continuation_state"),
        "recommended_actions": payload.get("recommended_actions", []),
        "blocking_issues": payload.get("blocking_issues", []),
        "affected_repair_chain_ids": payload.get("affected_repair_chain_ids", []),
        "reason_codes": payload.get("reason_codes", []),
    }
    return "cross-session-handoff-" + _stable_hash(stable_payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(item) for item in value if isinstance(item, dict)]


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
