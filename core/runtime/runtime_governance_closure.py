from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "runtime_governance_closure.v1"

# Keep both the older closure vocabulary and the newer freeze-candidate vocabulary.
# Existing runtime modules/tests may import CLOSURE_CLOSED directly.
CLOSURE_CLOSED = "closed"
CLOSURE_READY = "ready"
CLOSURE_BLOCKED = "blocked"
CLOSURE_WARNING = "warning"
CLOSURE_OPEN = "open"

GOVERNANCE_FREEZE_CANDIDATE = "freeze_candidate"
GOVERNANCE_FREEZE_BLOCKED = "freeze_blocked"
GOVERNANCE_FREEZE_WARNING = "freeze_warning"

CLOSURE_STATES: tuple[str, ...] = (
    CLOSURE_CLOSED,
    CLOSURE_READY,
    CLOSURE_BLOCKED,
    CLOSURE_WARNING,
    CLOSURE_OPEN,
)

FREEZE_STATES: tuple[str, ...] = (
    GOVERNANCE_FREEZE_CANDIDATE,
    GOVERNANCE_FREEZE_BLOCKED,
    GOVERNANCE_FREEZE_WARNING,
)

CLOSURE_REQUIRED_FIELDS: tuple[str, ...] = (
    "governance_closure_id",
    "closure_ready",
    "closure_state",
    "closure_blockers",
    "closure_warnings",
    "runtime_governance_freeze_candidate",
    "freeze_state",
    "closure_summary",
)


def runtime_governance_closure_required_fields() -> List[str]:
    return list(CLOSURE_REQUIRED_FIELDS)


def runtime_governance_closure_states() -> List[str]:
    return list(CLOSURE_STATES)


def runtime_governance_freeze_states() -> List[str]:
    return list(FREEZE_STATES)


def build_runtime_governance_closure_report(
    *,
    governance_chain_seal_report: Any | None = None,
    boundary_report: Any | None = None,
    closure_notes: Iterable[Any] | None = None,
    existing_blockers: Iterable[Any] | None = None,
    existing_warnings: Iterable[Any] | None = None,
    forensic_report: Any | None = None,
    self_edit_flow: Any | None = None,
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    convergence_report: Any | None = None,
    landing_consistency_report: Any | None = None,
    snapshot_seal: Any | None = None,
    **extra_inputs: Any,
) -> Dict[str, Any]:
    """Build a deterministic, data-only runtime governance closure report.

    This layer does not execute anything and does not mutate persistence. It only
    decides whether the already-built governance chain is a freeze candidate.
    """

    seal = _mapping(governance_chain_seal_report)
    boundary = _mapping(boundary_report)
    legacy_inputs_present = any(
        item is not None
        for item in (
            forensic_report,
            self_edit_flow,
            continuation_recommendation,
            cross_session_handoff,
            convergence_report,
            landing_consistency_report,
            snapshot_seal,
        )
    ) or bool(extra_inputs)

    if not seal and boundary:
        try:
            from core.runtime.runtime_governance_chain_seal import build_runtime_governance_chain_seal_report

            seal = build_runtime_governance_chain_seal_report(boundary_report=boundary)
        except Exception:
            seal = {}

    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    blockers.extend(_issue_list(existing_blockers))
    warnings.extend(_issue_list(existing_warnings))

    seal_state = _text(seal.get("governance_chain_state"))
    sealable = seal.get("governance_chain_sealable")

    if not seal and legacy_inputs_present:
        seal_state = "legacy_governance_closure"
        sealable = True
    elif not seal:
        blockers.append({"kind": "governance_chain_seal_missing"})
    elif sealable is not True:
        blockers.append(
            {
                "kind": "governance_chain_not_sealable",
                "governance_chain_state": seal_state,
            }
        )
    elif seal_state == "warning":
        warnings.append({"kind": "governance_chain_sealable_with_warnings"})

    for item in _issue_list(seal.get("seal_blockers")):
        blockers.append({"kind": "seal_blocker", "detail": item})
    for item in _issue_list(seal.get("seal_warnings")):
        warnings.append({"kind": "seal_warning", "detail": item})

    boundary_state = _text(boundary.get("boundary_state") or seal.get("seal_summary", {}).get("boundary_state"))
    if boundary_state == "blocked":
        blockers.append({"kind": "boundary_blocked"})
    elif boundary_state and boundary_state != "boundary_ready":
        warnings.append({"kind": "boundary_not_fully_ready", "boundary_state": boundary_state})

    notes = _string_list(closure_notes)
    if notes:
        warnings.append({"kind": "closure_notes_present", "count": len(notes)})

    blockers = _dedupe_issues(blockers)
    warnings = _dedupe_issues(warnings)

    closure_ready = not blockers
    if blockers:
        closure_state = CLOSURE_BLOCKED
        freeze_state = GOVERNANCE_FREEZE_BLOCKED
        freeze_candidate = False
    elif warnings:
        closure_state = CLOSURE_WARNING
        freeze_state = GOVERNANCE_FREEZE_WARNING
        freeze_candidate = True
    else:
        closure_state = CLOSURE_CLOSED
        freeze_state = GOVERNANCE_FREEZE_CANDIDATE
        freeze_candidate = True

    summary = {
        "source_governance_chain_seal_id": _text(seal.get("governance_chain_seal_id")),
        "source_boundary_id": _text(boundary.get("boundary_id") or seal.get("source_boundary_id")),
        "governance_chain_state": seal_state,
        "governance_chain_sealable": bool(sealable) if isinstance(sealable, bool) else False,
        "legacy_inputs_present": legacy_inputs_present,
        "closure_state": closure_state,
        "closure_ready": closure_ready,
        "runtime_governance_freeze_candidate": freeze_candidate,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "reason_codes": _sorted_unique(
            [
                *_reason_codes_from_issues(blockers),
                *_reason_codes_from_issues(warnings),
                *_string_list(_mapping(seal.get("seal_summary")).get("reason_codes")),
            ]
        ),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "governance_closure_id": "",
        "source_governance_chain_seal_id": summary["source_governance_chain_seal_id"],
        "source_boundary_id": summary["source_boundary_id"],
        "closure_ready": closure_ready,
        "closure_state": closure_state,
        "closure_blockers": blockers,
        "closure_warnings": warnings,
        "runtime_governance_freeze_candidate": freeze_candidate,
        "freeze_state": freeze_state,
        "closure_summary": summary,
        "closure_notes": notes,
        "legacy_inputs_present": legacy_inputs_present,
        "legacy_sources": {
            "forensic_report_present": forensic_report is not None,
            "self_edit_flow_present": self_edit_flow is not None,
            "continuation_recommendation_present": continuation_recommendation is not None,
            "cross_session_handoff_present": cross_session_handoff is not None,
            "convergence_report_present": convergence_report is not None,
            "landing_consistency_report_present": landing_consistency_report is not None,
            "snapshot_seal_present": snapshot_seal is not None,
            "extra_input_keys": _sorted_unique(extra_inputs.keys()),
        },
    }
    report["governance_closure_id"] = _closure_id(report)
    return report


def validate_runtime_governance_closure_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in CLOSURE_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []

    if _text(payload.get("closure_state")) not in CLOSURE_STATES:
        invalid_fields.append({"field": "closure_state", "reason": "invalid_state"})
    if _text(payload.get("freeze_state")) and _text(payload.get("freeze_state")) not in FREEZE_STATES:
        invalid_fields.append({"field": "freeze_state", "reason": "invalid_state"})
    for field in ("closure_ready", "runtime_governance_freeze_candidate"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})
    for field in ("closure_blockers", "closure_warnings"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    if "closure_summary" in payload and not isinstance(payload.get("closure_summary"), dict):
        invalid_fields.append({"field": "closure_summary", "reason": "expected_dict"})

    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(CLOSURE_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def build_runtime_governance_closure_summary(closure_report: Any) -> Dict[str, Any]:
    report = _mapping(closure_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "governance_closure_id": _text(report.get("governance_closure_id")),
        "source_governance_chain_seal_id": _text(report.get("source_governance_chain_seal_id")),
        "source_boundary_id": _text(report.get("source_boundary_id")),
        "closure_ready": bool(report.get("closure_ready")),
        "closure_state": _text(report.get("closure_state")),
        "runtime_governance_freeze_candidate": bool(report.get("runtime_governance_freeze_candidate")),
        "freeze_state": _text(report.get("freeze_state")),
        "closure_blocker_count": len(report.get("closure_blockers", []) or []),
        "closure_warning_count": len(report.get("closure_warnings", []) or []),
        "reason_codes": copy.deepcopy(_mapping(report.get("closure_summary")).get("reason_codes", [])),
    }


def _closure_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_governance_chain_seal_id": _text(report.get("source_governance_chain_seal_id")),
        "source_boundary_id": _text(report.get("source_boundary_id")),
        "closure_ready": bool(report.get("closure_ready")),
        "closure_state": _text(report.get("closure_state")),
        "runtime_governance_freeze_candidate": bool(report.get("runtime_governance_freeze_candidate")),
        "freeze_state": _text(report.get("freeze_state")),
        "closure_blockers": copy.deepcopy(report.get("closure_blockers", [])),
        "closure_warnings": copy.deepcopy(report.get("closure_warnings", [])),
        "closure_notes": copy.deepcopy(report.get("closure_notes", [])),
    }
    return "runtime-governance-closure-" + _stable_hash(payload)[:16]


def _issue_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(item) for item in value if isinstance(item, dict)]


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(
        _text(item.get("kind"))
        for item in issues
        if isinstance(item, dict) and _text(item.get("kind"))
    )


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    result: List[Dict[str, Any]] = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        key = json.dumps(issue, sort_keys=True, default=str, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        result.append(copy.deepcopy(issue))
    return result


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    return sorted({_text(value) for value in values if _text(value)})


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
