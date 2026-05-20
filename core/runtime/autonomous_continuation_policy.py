from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.execution_landing_consistency import (
    build_execution_landing_consistency_report,
)
from core.runtime.runtime_forensic_stack import (
    summarize_runtime_forensic_stack,
)
from core.runtime.runtime_forensic_stack_contract import (
    validate_forensic_report_contract,
)


POLICY_ID = "autonomous_continuation_policy.v1"

ACTION_NO_ACTION = "no_action"
ACTION_NEEDS_REVIEW = "needs_review"
ACTION_REPAIR_RECOMMENDED = "repair_recommended"
ACTION_REPLAY_RECOMMENDED = "replay_recommended"
ACTION_PLANNER_HANDOFF_RECOMMENDED = "planner_handoff_recommended"
ACTION_BLOCKED = "blocked"

STATE_SAFE_TO_CONTINUE = "safe_to_continue"
STATE_NEEDS_REVIEW = "needs_review"
STATE_BLOCKED = "blocked"

ACTION_TYPES: tuple[str, ...] = (
    ACTION_NO_ACTION,
    ACTION_NEEDS_REVIEW,
    ACTION_REPAIR_RECOMMENDED,
    ACTION_REPLAY_RECOMMENDED,
    ACTION_PLANNER_HANDOFF_RECOMMENDED,
    ACTION_BLOCKED,
)

CONTINUATION_STATES: tuple[str, ...] = (
    STATE_SAFE_TO_CONTINUE,
    STATE_NEEDS_REVIEW,
    STATE_BLOCKED,
)


def detect_continuation_candidates(forensic_report: Any) -> Dict[str, Any]:
    """Detect read-only forensic findings that may justify continuation guidance."""

    report = _forensic_report(forensic_report)
    reconstruction = _reconstruction_report(report)
    analyzer = _analyzer_results(reconstruction)
    chain_breaks = _chain_break_findings(report, reconstruction, analyzer)
    replay_divergence = _list(analyzer.get("replay_divergence_chains"))
    replay_hints = _list(reconstruction.get("replay_divergence_hints") or analyzer.get("replay_divergence_hints"))
    affected_repair_chain_ids = _affected_repair_chain_ids(
        report,
        reconstruction,
        chain_breaks,
        replay_divergence,
    )
    return {
        "policy_id": POLICY_ID,
        "input_report_id": _report_id(report, reconstruction),
        "has_findings": bool(chain_breaks or replay_divergence),
        "chain_break_candidates": chain_breaks,
        "replay_divergence_candidates": replay_divergence,
        "replay_divergence_hints": replay_hints,
        "affected_repair_chain_ids": affected_repair_chain_ids,
        "reason_codes": _reason_codes_for_candidates(chain_breaks, replay_divergence),
    }


def classify_broken_chains(forensic_report: Any) -> Dict[str, Any]:
    """Classify broken timeline chains into non-executing continuation actions."""

    candidates = detect_continuation_candidates(forensic_report)
    chain_breaks = candidates["chain_break_candidates"]
    reason_codes = sorted(
        {
            _text(item.get("reason_code"))
            for item in chain_breaks
            if _text(item.get("reason_code"))
        }
    )
    if not chain_breaks:
        return _classification(
            source="broken_chains",
            action_type=ACTION_NO_ACTION,
            continuation_state=STATE_SAFE_TO_CONTINUE,
            reason_codes=[],
            confidence=1.0,
        )

    blocking_kinds = {"circular_chain_ref", "self_parent_reference"}
    continuation_state = (
        STATE_BLOCKED
        if any(_text(item.get("kind")) in blocking_kinds for item in chain_breaks)
        else STATE_NEEDS_REVIEW
    )
    action_type = ACTION_BLOCKED if continuation_state == STATE_BLOCKED else ACTION_REPAIR_RECOMMENDED
    return _classification(
        source="broken_chains",
        action_type=action_type,
        continuation_state=continuation_state,
        reason_codes=reason_codes or ["chain_break_detected"],
        affected_repair_chain_ids=candidates["affected_repair_chain_ids"],
        findings=chain_breaks,
        confidence=0.86 if continuation_state == STATE_NEEDS_REVIEW else 0.93,
    )


def classify_replay_divergence(report_or_comparison: Any) -> Dict[str, Any]:
    """Classify replay divergence or replay diff reports into safe recommendations."""

    payload = _mapping(report_or_comparison)
    if "divergence_regions" in payload or "replay_drift" in payload:
        divergence_findings = [
            _tagged_finding("replay_divergence", item)
            for item in _list(payload.get("divergence_regions"))
        ]
        drift_findings = [
            _tagged_finding("replay_drift", item)
            for item in _list(payload.get("replay_drift"))
        ]
        new_breaks = [
            _tagged_finding("new_chain_break", item)
            for item in _list(payload.get("new_chain_breaks"))
        ]
        findings = [*divergence_findings, *drift_findings, *new_breaks]
        affected = _string_list(payload.get("affected_repair_chain_ids"))
        report_id = _text(payload.get("comparison_id"))
        severity = _text(_mapping(payload.get("severity_hint")).get("level"))
    else:
        candidates = detect_continuation_candidates(payload)
        findings = [
            _tagged_finding("replay_divergence", item)
            for item in candidates["replay_divergence_candidates"]
        ]
        affected = candidates["affected_repair_chain_ids"]
        report_id = candidates["input_report_id"]
        severity = "medium" if findings else "low"

    if not findings:
        return _classification(
            source="replay_divergence",
            action_type=ACTION_NO_ACTION,
            continuation_state=STATE_SAFE_TO_CONTINUE,
            reason_codes=[],
            confidence=1.0,
            input_report_id=report_id,
        )

    reason_codes = sorted(
        {
            _text(reason)
            for item in findings
            for reason in (
                _string_list(item.get("reasons"))
                or _string_list(item.get("reason"))
                or [_text(item.get("kind"))]
            )
            if _text(reason)
        }
    )
    continuation_state = STATE_BLOCKED if severity == "high" and any(
        _text(item.get("kind")) == "new_chain_break" for item in findings
    ) else STATE_NEEDS_REVIEW
    return _classification(
        source="replay_divergence",
        action_type=ACTION_BLOCKED if continuation_state == STATE_BLOCKED else ACTION_REPLAY_RECOMMENDED,
        continuation_state=continuation_state,
        reason_codes=reason_codes or ["replay_divergence_detected"],
        affected_repair_chain_ids=affected,
        findings=findings,
        confidence=0.82 if continuation_state == STATE_NEEDS_REVIEW else 0.9,
        input_report_id=report_id,
    )


def classify_execution_landing_inconsistencies(landing_report_or_contracts: Any) -> Dict[str, Any]:
    """Classify execution landing consistency issues without mutating runtime surfaces."""

    payload = _mapping(landing_report_or_contracts)
    report = (
        copy.deepcopy(payload)
        if payload.get("schema_version") == "execution_landing_consistency.v1"
        else build_execution_landing_consistency_report(payload)
    )
    blocking_issues = _list(report.get("blocking_issues"))
    if not blocking_issues:
        return _classification(
            source="execution_landing_consistency",
            action_type=ACTION_NO_ACTION,
            continuation_state=STATE_SAFE_TO_CONTINUE,
            reason_codes=[],
            confidence=1.0,
            input_report_id=_text(report.get("report_id")),
        )

    reason_codes = sorted(
        {
            "landing_" + _text(item.get("kind"))
            for item in blocking_issues
            if _text(item.get("kind"))
        }
    )
    return _classification(
        source="execution_landing_consistency",
        action_type=ACTION_BLOCKED,
        continuation_state=STATE_BLOCKED,
        reason_codes=reason_codes or ["landing_consistency_blocking_issue"],
        blocking_issues=blocking_issues,
        confidence=0.94,
        input_report_id=_text(report.get("report_id")),
    )


def build_planner_handoff_payload(
    recommendations: Iterable[Any],
    *,
    input_report_id: str = "",
    affected_repair_chain_ids: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Create a planner handoff payload as data only; this never invokes a planner."""

    actions = [
        copy.deepcopy(item)
        for item in recommendations
        if isinstance(item, dict) and _text(item.get("action_type")) not in ("", ACTION_NO_ACTION)
    ]
    repair_chain_ids = _sorted_unique(
        [
            *_string_list(affected_repair_chain_ids),
            *[
                chain_id
                for action in actions
                for chain_id in _string_list(action.get("affected_repair_chain_ids"))
            ],
        ]
    )
    return {
        "policy_id": POLICY_ID,
        "input_report_id": _text(input_report_id),
        "handoff_type": ACTION_PLANNER_HANDOFF_RECOMMENDED,
        "planner_invoked": False,
        "recommended_actions": actions,
        "affected_repair_chain_ids": repair_chain_ids,
        "reason_codes": _sorted_unique(
            reason
            for action in actions
            for reason in _string_list(action.get("reason_codes"))
        ),
    }


def build_autonomous_continuation_recommendation(
    forensic_report: Any,
    *,
    replay_comparison: Any | None = None,
    landing_consistency_report: Any | None = None,
) -> Dict[str, Any]:
    """Produce a read-only autonomous continuation policy recommendation."""

    report = _forensic_report(forensic_report)
    reconstruction = _reconstruction_report(report)
    input_report_id = _report_id(report, reconstruction)
    contract_validation = validate_forensic_report_contract(report)
    candidates = detect_continuation_candidates(report)

    classifications = [
        classify_broken_chains(report),
        classify_replay_divergence(replay_comparison if replay_comparison is not None else report),
    ]
    if landing_consistency_report is not None:
        classifications.append(classify_execution_landing_inconsistencies(landing_consistency_report))
    if not contract_validation.get("ok"):
        classifications.append(
            _classification(
                source="forensic_report_contract",
                action_type=ACTION_BLOCKED,
                continuation_state=STATE_BLOCKED,
                reason_codes=["forensic_report_contract_invalid"],
                blocking_issues=[
                    {
                        "kind": "contract_validation_failed",
                        "missing_fields": copy.deepcopy(contract_validation.get("missing_fields", [])),
                        "unexpected_type": _text(contract_validation.get("unexpected_type")),
                    }
                ],
                confidence=0.98,
                input_report_id=input_report_id,
            )
        )

    meaningful = [
        item
        for item in classifications
        if _text(item.get("action_type")) != ACTION_NO_ACTION
    ]
    state = _continuation_state(classifications)
    reason_codes = _sorted_unique(
        reason
        for item in classifications
        for reason in _string_list(item.get("reason_codes"))
    )
    affected = _sorted_unique(
        [
            *candidates.get("affected_repair_chain_ids", []),
            *[
                chain_id
                for item in classifications
                for chain_id in _string_list(item.get("affected_repair_chain_ids"))
            ],
        ]
    )
    if not meaningful:
        meaningful = [
            _classification(
                source="autonomous_continuation_policy",
                action_type=ACTION_NO_ACTION,
                continuation_state=STATE_SAFE_TO_CONTINUE,
                reason_codes=[],
                confidence=1.0,
                input_report_id=input_report_id,
            )
        ]

    handoff_payload = (
        build_planner_handoff_payload(
            meaningful,
            input_report_id=input_report_id,
            affected_repair_chain_ids=affected,
        )
        if state == STATE_NEEDS_REVIEW and any(
            _text(item.get("action_type")) in {ACTION_REPAIR_RECOMMENDED, ACTION_REPLAY_RECOMMENDED}
            for item in meaningful
        )
        else {}
    )
    if handoff_payload:
        meaningful.append(
            _classification(
                source="planner_handoff",
                action_type=ACTION_PLANNER_HANDOFF_RECOMMENDED,
                continuation_state=STATE_NEEDS_REVIEW,
                reason_codes=handoff_payload["reason_codes"],
                affected_repair_chain_ids=affected,
                confidence=0.78,
                input_report_id=input_report_id,
            )
        )

    blocking_issues = [
        issue
        for item in classifications
        for issue in _list(item.get("blocking_issues"))
    ]
    recommendation = {
        "policy_id": POLICY_ID,
        "input_report_id": input_report_id,
        "continuation_state": state,
        "recommended_actions": copy.deepcopy(meaningful),
        "blocking_issues": copy.deepcopy(blocking_issues),
        "affected_repair_chain_ids": affected,
        "planner_handoff_payload": handoff_payload,
        "confidence": _confidence(meaningful, state),
        "reason_codes": reason_codes,
    }
    recommendation["recommendation_id"] = _recommendation_id(recommendation)
    return recommendation


def _classification(
    *,
    source: str,
    action_type: str,
    continuation_state: str,
    reason_codes: Iterable[Any],
    affected_repair_chain_ids: Iterable[Any] | None = None,
    findings: Iterable[Any] | None = None,
    blocking_issues: Iterable[Any] | None = None,
    confidence: float = 0.0,
    input_report_id: str = "",
) -> Dict[str, Any]:
    return {
        "source": _text(source),
        "action_type": _text(action_type),
        "continuation_state": _text(continuation_state),
        "input_report_id": _text(input_report_id),
        "affected_repair_chain_ids": _sorted_unique(_string_list(affected_repair_chain_ids)),
        "findings": [copy.deepcopy(item) for item in findings or [] if isinstance(item, dict)],
        "blocking_issues": [copy.deepcopy(item) for item in blocking_issues or [] if isinstance(item, dict)],
        "confidence": round(float(confidence), 4),
        "reason_codes": _sorted_unique(_string_list(reason_codes)),
    }


def _forensic_report(value: Any) -> Dict[str, Any]:
    return _mapping(value)


def _reconstruction_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(report.get("reconstruction_report"), dict):
        return copy.deepcopy(report["reconstruction_report"])
    if isinstance(report.get("report"), dict):
        return copy.deepcopy(report["report"])
    return {}


def _analyzer_results(reconstruction: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(reconstruction.get("analyzer_results"), dict):
        return copy.deepcopy(reconstruction["analyzer_results"])
    return {}


def _chain_break_findings(
    report: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    analyzer: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    evidence = _mapping(report.get("evidence_bundle") or reconstruction.get("evidence_bundle"))
    broken = _mapping(evidence.get("broken_timeline_chains"))
    for item in _list(broken.get("missing_parent_refs")):
        findings.append(_chain_break("missing_parent_ref", "missing_parent_ref", item))
    for item in _list(broken.get("missing_previous_runtime_refs")):
        findings.append(_chain_break("missing_previous_runtime_ref", "missing_previous_runtime_ref", item))
    for item in _list(analyzer.get("broken_parent_refs")):
        reason = _text(item.get("reason")) or "broken_parent_ref"
        findings.append(_chain_break(reason, reason, item))
    for item in _list(analyzer.get("circular_chain_refs")):
        findings.append(_chain_break("circular_chain_ref", "circular_chain_ref", item))
    for item in _list(analyzer.get("depth_anomalies")):
        reason = _text(item.get("reason")) or "depth_anomaly"
        findings.append(_chain_break("depth_anomaly", reason, item))
    return _dedupe_findings(findings)


def _chain_break(kind: str, reason_code: str, item: Mapping[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(dict(item))
    payload["kind"] = _text(kind)
    payload["reason_code"] = _text(reason_code)
    return payload


def _tagged_finding(kind: str, item: Mapping[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(dict(item))
    payload["kind"] = _text(payload.get("kind") or kind)
    return payload


def _dedupe_findings(findings: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in findings:
        payload = copy.deepcopy(dict(item))
        deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _affected_repair_chain_ids(
    report: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    chain_breaks: Iterable[Mapping[str, Any]],
    replay_divergence: Iterable[Mapping[str, Any]],
) -> List[str]:
    values: List[Any] = []
    summary = summarize_runtime_forensic_stack(report)
    values.extend(_string_list(summary.get("repair_chain_ids")))
    values.extend(_string_list(reconstruction.get("affected_repair_chain_ids")))
    for item in [*list(chain_breaks), *list(replay_divergence)]:
        values.extend(_string_list(item.get("repair_chain_ids")))
        values.append(item.get("repair_chain_id"))
    return _sorted_unique(_string_list(values))


def _reason_codes_for_candidates(
    chain_breaks: Iterable[Mapping[str, Any]],
    replay_divergence: Iterable[Mapping[str, Any]],
) -> List[str]:
    codes = [
        _text(item.get("reason_code"))
        for item in chain_breaks
        if _text(item.get("reason_code"))
    ]
    for item in replay_divergence:
        codes.extend(_string_list(item.get("reasons")))
    return _sorted_unique(codes)


def _continuation_state(classifications: Iterable[Mapping[str, Any]]) -> str:
    states = {_text(item.get("continuation_state")) for item in classifications}
    if STATE_BLOCKED in states:
        return STATE_BLOCKED
    if STATE_NEEDS_REVIEW in states:
        return STATE_NEEDS_REVIEW
    return STATE_SAFE_TO_CONTINUE


def _confidence(actions: Iterable[Mapping[str, Any]], state: str) -> float:
    values = [
        float(item.get("confidence"))
        for item in actions
        if isinstance(item.get("confidence"), (int, float))
    ]
    if not values:
        return 1.0 if state == STATE_SAFE_TO_CONTINUE else 0.0
    return round(min(values), 4)


def _report_id(report: Mapping[str, Any], reconstruction: Mapping[str, Any]) -> str:
    return _text(report.get("report_id") or reconstruction.get("report_id"))


def _recommendation_id(recommendation: Mapping[str, Any]) -> str:
    payload = {
        "policy_id": recommendation.get("policy_id"),
        "input_report_id": recommendation.get("input_report_id"),
        "continuation_state": recommendation.get("continuation_state"),
        "recommended_actions": recommendation.get("recommended_actions", []),
        "blocking_issues": recommendation.get("blocking_issues", []),
        "affected_repair_chain_ids": recommendation.get("affected_repair_chain_ids", []),
        "reason_codes": recommendation.get("reason_codes", []),
    }
    return "autonomous-continuation-" + _stable_hash(payload)[:16]


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
    return sorted({_text(value) for value in values if _text(value)})


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
