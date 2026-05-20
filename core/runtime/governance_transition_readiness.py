from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.autonomous_continuation_policy import (
    ACTION_BLOCKED,
    ACTION_NEEDS_REVIEW,
    ACTION_NO_ACTION,
    STATE_BLOCKED,
    build_autonomous_continuation_recommendation,
)
from core.runtime.cross_session_engineering_continuity import (
    build_cross_session_handoff_payload,
    validate_cross_session_handoff_payload,
)
from core.runtime.execution_landing_consistency import (
    build_execution_landing_consistency_report,
)
from core.runtime.runtime_forensic_stack import summarize_runtime_forensic_stack
from core.runtime.runtime_governance_closure import (
    CLOSURE_BLOCKED,
    CLOSURE_CLOSED,
    build_runtime_governance_closure_report,
    validate_runtime_governance_closure_report,
)
from core.runtime.runtime_replay_snapshot_seal import (
    SEAL_VERSION,
    seal_replay_reconstruction_report,
)
from core.runtime.self_edit_mainline_convergence import (
    CONVERGENCE_BLOCKED,
    CONVERGENCE_CONVERGED,
    build_self_edit_convergence_report,
    validate_self_edit_convergence_report,
)
from core.runtime.windows_runtime_stabilization import build_windows_runtime_report


SCHEMA_VERSION = "governance_transition_readiness.v1"

TRANSITION_READY = "ready"
TRANSITION_NEEDS_REVIEW = "needs_review"
TRANSITION_BLOCKED = "blocked"

READINESS_REQUIRED_FIELDS: tuple[str, ...] = (
    "readiness_id",
    "transition_state",
    "governance_closed",
    "self_edit_ready",
    "continuation_ready",
    "cross_session_ready",
    "landing_ready",
    "seal_ready",
    "windows_runtime_ready",
    "blocking_issues",
    "recommended_actions",
    "readiness_score",
    "reason_codes",
)


def governance_transition_readiness_required_fields() -> List[str]:
    return list(READINESS_REQUIRED_FIELDS)


def check_governance_closure_usable(closure_report: Any) -> Dict[str, Any]:
    closure = _mapping(closure_report)
    if not closure:
        return {
            "usable": False,
            "state": "",
            "blocking_issues": [{"kind": "governance_closure_missing"}],
            "reason_codes": ["governance_closure_missing"],
        }
    validation = validate_runtime_governance_closure_report(closure) if closure else {"ok": False}
    state = _text(closure.get("closure_state"))
    return {
        "usable": bool(validation.get("ok")) and state == CLOSURE_CLOSED,
        "state": state,
        "blocking_issues": _blocking_from_report(
            closure.get("governance_blockers", []),
            default_kind="governance_closure_not_closed",
            blocked=state == CLOSURE_BLOCKED or not validation.get("ok"),
        ),
        "reason_codes": _string_list(closure.get("reason_codes")),
    }


def check_self_edit_convergence_usable(convergence_report: Any) -> Dict[str, Any]:
    convergence = _mapping(convergence_report)
    if not convergence:
        return {
            "usable": False,
            "state": "",
            "blocking_issues": [{"kind": "self_edit_convergence_missing"}],
            "reason_codes": ["self_edit_convergence_missing"],
        }
    validation = validate_self_edit_convergence_report(convergence) if convergence else {"ok": False}
    state = _text(convergence.get("convergence_state"))
    return {
        "usable": bool(validation.get("ok")) and state == CONVERGENCE_CONVERGED,
        "state": state,
        "blocking_issues": _blocking_from_report(
            convergence.get("blocking_issues", []),
            default_kind="self_edit_not_converged",
            blocked=state == CONVERGENCE_BLOCKED or not validation.get("ok"),
        ),
        "reason_codes": _string_list(convergence.get("reason_codes")),
    }


def check_continuation_policy_usable(continuation_recommendation: Any) -> Dict[str, Any]:
    continuation = _mapping(continuation_recommendation)
    state = _text(continuation.get("continuation_state"))
    usable = bool(continuation) and state != STATE_BLOCKED
    return {
        "usable": usable,
        "state": state,
        "blocking_issues": _blocking_from_report(
            continuation.get("blocking_issues", []),
            default_kind="continuation_policy_blocked",
            blocked=state == STATE_BLOCKED or not continuation,
        ),
        "reason_codes": _string_list(continuation.get("reason_codes")),
    }


def check_cross_session_handoff_usable(cross_session_handoff: Any) -> Dict[str, Any]:
    handoff = _mapping(cross_session_handoff)
    validation = validate_cross_session_handoff_payload(handoff) if handoff else {"ok": False}
    usable = bool(validation.get("ok"))
    return {
        "usable": usable,
        "state": _text(handoff.get("continuation_state")),
        "blocking_issues": [] if usable else [{"kind": "cross_session_handoff_not_usable"}],
        "reason_codes": _string_list(handoff.get("reason_codes")),
    }


def check_execution_landing_consistent(landing_consistency_report: Any) -> Dict[str, Any]:
    landing = _normalize_landing_consistency(landing_consistency_report)
    ready = bool(landing) and not landing.get("blocking_issues")
    return {
        "usable": ready,
        "report_id": _text(landing.get("report_id")),
        "blocking_issues": copy.deepcopy(landing.get("blocking_issues", []))
        if landing
        else [{"kind": "landing_consistency_missing"}],
        "reason_codes": _reason_codes_from_issues(landing.get("blocking_issues", [])),
    }


def check_replay_snapshot_seal_usable(snapshot_seal: Any, *, forensic_report: Any | None = None) -> Dict[str, Any]:
    seal = _mapping(snapshot_seal)
    forensic = _mapping(forensic_report)
    forensic_report_id = _text(forensic.get("report_id"))
    ready = (
        bool(seal)
        and _text(seal.get("seal_version")) == SEAL_VERSION
        and bool(_text(seal.get("snapshot_seal_id")))
        and bool(_text(seal.get("replay_hash")))
        and bool(_text(seal.get("integrity_hash")))
        and bool(_text(seal.get("divergence_hash")))
        and (not forensic_report_id or _text(seal.get("report_id")) == forensic_report_id)
    )
    issues: List[Dict[str, Any]] = []
    if not ready:
        issues.append({"kind": "replay_snapshot_seal_not_usable" if seal else "replay_snapshot_seal_missing"})
    return {
        "usable": ready,
        "snapshot_seal_id": _text(seal.get("snapshot_seal_id")),
        "blocking_issues": issues,
        "reason_codes": _reason_codes_from_issues(issues),
    }


def check_windows_runtime_blockers(windows_runtime_report: Any) -> Dict[str, Any]:
    report = _mapping(windows_runtime_report)
    ready = bool(report) and not report.get("blocking_issues") and bool(report.get("json_safe", True))
    issues = copy.deepcopy(report.get("blocking_issues", [])) if report else [{"kind": "windows_runtime_report_missing"}]
    return {
        "usable": ready,
        "report_id": _text(report.get("report_id")),
        "blocking_issues": issues,
        "reason_codes": _reason_codes_from_issues(issues),
    }


def build_governance_transition_next_action_recommendations(readiness_report: Any) -> List[Dict[str, Any]]:
    report = _mapping(readiness_report)
    state = _text(report.get("transition_state"))
    if state == TRANSITION_READY:
        return [{"action_type": ACTION_NO_ACTION, "reason_codes": [], "data_only": True}]
    return [
        {
            "action_type": ACTION_BLOCKED if state == TRANSITION_BLOCKED else ACTION_NEEDS_REVIEW,
            "target": "governance_transition_readiness",
            "blocking_issue_count": len(report.get("blocking_issues", []) or []),
            "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
            "data_only": True,
        }
    ]


def build_governance_transition_readiness_report(
    *,
    governance_closure_report: Any | None = None,
    self_edit_flow: Any | None = None,
    self_edit_convergence_report: Any | None = None,
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    landing_consistency_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    windows_runtime_report: Any | None = None,
) -> Dict[str, Any]:
    """Assess readiness to transition from reports into governed actions, read-only."""

    forensic = _mapping(forensic_report)
    landing = _normalize_landing_consistency(landing_consistency_report) or _derive_landing(self_edit_flow)
    seal = _mapping(snapshot_seal) or (
        seal_replay_reconstruction_report(_mapping(forensic.get("reconstruction_report")))
        if forensic.get("reconstruction_report")
        else {}
    )
    continuation = _mapping(continuation_recommendation) or (
        build_autonomous_continuation_recommendation(forensic, landing_consistency_report=landing if landing else None)
        if forensic
        else {}
    )
    convergence = _mapping(self_edit_convergence_report) or (
        build_self_edit_convergence_report(
            _mapping(self_edit_flow),
            forensic_report=forensic,
            landing_consistency_report=landing if landing else None,
            continuation_recommendation=continuation if continuation else None,
        )
        if self_edit_flow is not None
        else {}
    )
    handoff = _mapping(cross_session_handoff) or (
        build_cross_session_handoff_payload(
            forensic_report=forensic,
            continuation_recommendation=continuation,
        )
        if forensic and continuation
        else {}
    )
    closure = _mapping(governance_closure_report) or (
        build_runtime_governance_closure_report(
            forensic_report=forensic,
            self_edit_flow=self_edit_flow,
            continuation_recommendation=continuation if continuation else None,
            cross_session_handoff=handoff if handoff else None,
            convergence_report=convergence if convergence else None,
            landing_consistency_report=landing if landing else None,
            snapshot_seal=seal if seal else None,
        )
        if forensic or self_edit_flow is not None
        else {}
    )
    windows_report = _mapping(windows_runtime_report) or build_windows_runtime_report(cli_payload={"ok": True})

    checks = {
        "governance": check_governance_closure_usable(closure),
        "self_edit": check_self_edit_convergence_usable(convergence),
        "continuation": check_continuation_policy_usable(continuation),
        "cross_session": check_cross_session_handoff_usable(handoff),
        "landing": check_execution_landing_consistent(landing),
        "seal": check_replay_snapshot_seal_usable(seal, forensic_report=forensic),
        "windows_runtime": check_windows_runtime_blockers(windows_report),
    }
    blocking_issues = _dedupe_issues(
        issue
        for check in checks.values()
        for issue in check.get("blocking_issues", [])
    )
    state = _transition_state(checks, blocking_issues)
    report = {
        "schema_version": SCHEMA_VERSION,
        "readiness_id": "",
        "transition_state": state,
        "governance_closed": bool(checks["governance"]["usable"]),
        "self_edit_ready": bool(checks["self_edit"]["usable"]),
        "continuation_ready": bool(checks["continuation"]["usable"]),
        "cross_session_ready": bool(checks["cross_session"]["usable"]),
        "landing_ready": bool(checks["landing"]["usable"]),
        "seal_ready": bool(checks["seal"]["usable"]),
        "windows_runtime_ready": bool(checks["windows_runtime"]["usable"]),
        "blocking_issues": blocking_issues,
        "recommended_actions": [],
        "readiness_score": _readiness_score(checks, blocking_issues),
        "reason_codes": _sorted_unique(
            reason
            for check in checks.values()
            for reason in _string_list(check.get("reason_codes"))
        ),
        "checks": checks,
    }
    report["recommended_actions"] = build_governance_transition_next_action_recommendations(report)
    report["readiness_id"] = _readiness_id(report)
    return report


def validate_governance_transition_readiness_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in READINESS_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("transition_state")) not in {
        TRANSITION_READY,
        TRANSITION_NEEDS_REVIEW,
        TRANSITION_BLOCKED,
    }:
        invalid_fields.append({"field": "transition_state", "reason": "invalid_state"})
    for field in ("blocking_issues", "recommended_actions", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(READINESS_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _transition_state(checks: Mapping[str, Mapping[str, Any]], blocking_issues: Iterable[Any]) -> str:
    if any(_hard_blocker(issue) for issue in blocking_issues):
        return TRANSITION_BLOCKED
    if all(bool(check.get("usable")) for check in checks.values()):
        return TRANSITION_READY
    return TRANSITION_NEEDS_REVIEW


def _hard_blocker(issue: Any) -> bool:
    if not isinstance(issue, dict):
        return False
    return _text(issue.get("kind")) in {
        "governance_closure_not_closed",
        "continuation_policy_blocked",
        "self_edit_not_converged",
        "missing_required_fields",
        "incompatible_field",
        "replay_snapshot_seal_not_usable",
        "base_interpreter_missing",
        "bundled_python_inconsistent",
        "cli_json_circular_reference",
        "cli_json_serialization_error",
        "cli_json_not_safe",
        "python_launcher_blocked",
        "required_path_missing",
    }


def _readiness_score(checks: Mapping[str, Mapping[str, Any]], blocking_issues: Iterable[Any]) -> float:
    total = max(1, len(checks))
    ready = sum(1 for check in checks.values() if check.get("usable"))
    penalty = len(list(blocking_issues)) * 0.03
    return round(max(0.0, (ready / total) - penalty), 4)


def _blocking_from_report(
    issues: Any,
    *,
    default_kind: str,
    blocked: bool,
) -> List[Dict[str, Any]]:
    existing = [copy.deepcopy(item) for item in issues or [] if isinstance(item, dict)]
    if blocked and not existing:
        existing.append({"kind": default_kind})
    return existing


def _normalize_landing_consistency(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _derive_landing(self_edit_flow: Any | None) -> Dict[str, Any]:
    flow = _mapping(self_edit_flow)
    if not flow:
        return {}
    landing = flow.get("landing")
    if not isinstance(landing, dict) and isinstance(flow.get("stages"), dict):
        landing = flow["stages"].get("landing")
    return build_execution_landing_consistency_report({"self_edit": landing if isinstance(landing, dict) else {}})


def _reason_codes_from_issues(issues: Any) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues or [] if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _readiness_id(report: Mapping[str, Any]) -> str:
    payload = {
        "transition_state": report.get("transition_state"),
        "governance_closed": report.get("governance_closed"),
        "self_edit_ready": report.get("self_edit_ready"),
        "continuation_ready": report.get("continuation_ready"),
        "cross_session_ready": report.get("cross_session_ready"),
        "landing_ready": report.get("landing_ready"),
        "seal_ready": report.get("seal_ready"),
        "windows_runtime_ready": report.get("windows_runtime_ready"),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governance-transition-readiness-" + _stable_hash(payload)[:16]


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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
