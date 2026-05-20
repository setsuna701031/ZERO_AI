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
    STATE_NEEDS_REVIEW,
    STATE_SAFE_TO_CONTINUE,
    build_autonomous_continuation_recommendation,
)
from core.runtime.cross_session_engineering_continuity import (
    build_cross_session_handoff_payload,
    validate_cross_session_handoff_payload,
)
from core.runtime.execution_landing_consistency import (
    build_execution_landing_consistency_report,
)
from core.runtime.runtime_forensic_stack import (
    summarize_runtime_forensic_stack,
)
from core.runtime.runtime_forensic_stack_contract import (
    validate_forensic_report_contract,
)
from core.runtime.runtime_replay_snapshot_seal import (
    SEAL_VERSION,
    generate_replay_snapshot_seal_metadata,
    seal_replay_reconstruction_report,
)
from core.runtime.self_edit_mainline_convergence import (
    CONVERGENCE_BLOCKED,
    CONVERGENCE_CONVERGED,
    CONVERGENCE_NEEDS_REVIEW,
    build_self_edit_convergence_report,
)


SCHEMA_VERSION = "runtime_governance_closure.v1"

CLOSURE_CLOSED = "closed"
CLOSURE_NEEDS_REVIEW = "needs_review"
CLOSURE_BLOCKED = "blocked"

CLOSURE_REQUIRED_FIELDS: tuple[str, ...] = (
    "closure_id",
    "closure_state",
    "forensic_ready",
    "evidence_ready",
    "seal_ready",
    "continuation_ready",
    "cross_session_ready",
    "self_edit_converged",
    "landing_consistent",
    "governance_blockers",
    "recommended_actions",
    "affected_repair_chain_ids",
    "audit_summary",
    "closure_score",
    "reason_codes",
)

CLOSURE_LAYER_NAMES: tuple[str, ...] = (
    "forensic_stack",
    "evidence_bundle",
    "replay_snapshot_seal",
    "autonomous_continuation",
    "cross_session_continuity",
    "self_edit_convergence",
    "execution_landing_consistency",
)


def runtime_governance_closure_required_fields() -> List[str]:
    return list(CLOSURE_REQUIRED_FIELDS)


def runtime_governance_closure_layers() -> List[str]:
    return list(CLOSURE_LAYER_NAMES)


def check_runtime_governance_alignment(
    *,
    forensic_report: Any | None = None,
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    convergence_report: Any | None = None,
    landing_consistency_report: Any | None = None,
    snapshot_seal: Any | None = None,
) -> Dict[str, Any]:
    """Check read-only readiness/alignment across governance closure layers."""

    forensic = _mapping(forensic_report)
    continuation = _mapping(continuation_recommendation)
    handoff = _mapping(cross_session_handoff)
    convergence = _mapping(convergence_report)
    landing = _mapping(landing_consistency_report)
    seal = _mapping(snapshot_seal)
    forensic_validation = validate_forensic_report_contract(forensic)
    forensic_summary = summarize_runtime_forensic_stack(forensic)
    evidence = _mapping(forensic.get("evidence_bundle"))
    seal_metadata = generate_replay_snapshot_seal_metadata(seal) if seal else {}

    forensic_ready = bool(forensic) and bool(forensic_validation.get("ok"))
    evidence_ready = bool(evidence.get("timeline")) and _safe_int(evidence.get("source_record_count")) > 0
    seal_ready = _seal_ready(seal, forensic)
    continuation_ready = bool(continuation) and _text(continuation.get("continuation_state")) != STATE_BLOCKED
    cross_session_ready = bool(handoff) and bool(validate_cross_session_handoff_payload(handoff).get("ok"))
    self_edit_converged = bool(convergence) and _text(convergence.get("convergence_state")) == CONVERGENCE_CONVERGED
    landing_consistent = bool(landing) and not landing.get("blocking_issues")
    return {
        "schema_version": SCHEMA_VERSION,
        "forensic_ready": forensic_ready,
        "evidence_ready": evidence_ready,
        "seal_ready": seal_ready,
        "continuation_ready": continuation_ready,
        "cross_session_ready": cross_session_ready,
        "self_edit_converged": self_edit_converged,
        "landing_consistent": landing_consistent,
        "forensic_report_id": _text(forensic.get("report_id") or forensic_summary.get("report_id")),
        "snapshot_seal_id": _text(seal_metadata.get("snapshot_seal_id")),
        "continuation_state": _text(continuation.get("continuation_state")),
        "convergence_state": _text(convergence.get("convergence_state")),
    }


def detect_missing_closure_layers(
    *,
    forensic_report: Any | None = None,
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    convergence_report: Any | None = None,
    landing_consistency_report: Any | None = None,
    snapshot_seal: Any | None = None,
) -> List[str]:
    missing: List[str] = []
    if not _mapping(forensic_report):
        missing.append("forensic_stack")
    if not _mapping(forensic_report).get("evidence_bundle"):
        missing.append("evidence_bundle")
    if not _mapping(snapshot_seal):
        missing.append("replay_snapshot_seal")
    if not _mapping(continuation_recommendation):
        missing.append("autonomous_continuation")
    if not _mapping(cross_session_handoff):
        missing.append("cross_session_continuity")
    if not _mapping(convergence_report):
        missing.append("self_edit_convergence")
    if not _mapping(landing_consistency_report):
        missing.append("execution_landing_consistency")
    return missing


def detect_governance_blockers(
    *,
    alignment: Any,
    missing_layers: Iterable[Any],
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    convergence_report: Any | None = None,
    landing_consistency_report: Any | None = None,
) -> List[Dict[str, Any]]:
    aligned = _mapping(alignment)
    missing = set(_string_list(missing_layers))
    continuation = _mapping(continuation_recommendation)
    handoff = _mapping(cross_session_handoff)
    convergence = _mapping(convergence_report)
    landing = _mapping(landing_consistency_report)
    blockers: List[Dict[str, Any]] = []
    for layer in _string_list(missing_layers):
        blockers.append({"kind": "missing_closure_layer", "layer": layer})
    for key, layer in (
        ("forensic_ready", "forensic_stack"),
        ("evidence_ready", "evidence_bundle"),
        ("seal_ready", "replay_snapshot_seal"),
        ("landing_consistent", "execution_landing_consistency"),
    ):
        if key in aligned and not aligned.get(key) and layer not in missing:
            blockers.append({"kind": "layer_not_ready", "layer": layer})
    if _text(continuation.get("continuation_state")) == STATE_BLOCKED:
        blockers.append({"kind": "continuation_blocked", "layer": "autonomous_continuation"})
    if _text(convergence.get("convergence_state")) == CONVERGENCE_BLOCKED:
        blockers.append({"kind": "self_edit_convergence_blocked", "layer": "self_edit_convergence"})
    if handoff and not validate_cross_session_handoff_payload(handoff).get("ok"):
        blockers.append({"kind": "cross_session_handoff_invalid", "layer": "cross_session_continuity"})
    blockers.extend(copy.deepcopy(continuation.get("blocking_issues", [])))
    blockers.extend(copy.deepcopy(convergence.get("blocking_issues", [])))
    blockers.extend(copy.deepcopy(landing.get("blocking_issues", [])))
    return _dedupe_blockers(blockers)


def build_runtime_governance_next_action_recommendations(
    closure_report: Any,
) -> List[Dict[str, Any]]:
    report = _mapping(closure_report)
    state = _text(report.get("closure_state"))
    if state == CLOSURE_CLOSED:
        return [{"action_type": ACTION_NO_ACTION, "reason_codes": [], "data_only": True}]

    actions: List[Dict[str, Any]] = []
    missing_layers = _string_list(report.get("missing_layers"))
    if missing_layers:
        actions.append(
            {
                "action_type": ACTION_NEEDS_REVIEW,
                "target": "runtime_governance_layers",
                "missing_layers": missing_layers,
                "reason_codes": ["missing_closure_layers"],
                "data_only": True,
            }
        )
    if report.get("governance_blockers"):
        actions.append(
            {
                "action_type": ACTION_BLOCKED if state == CLOSURE_BLOCKED else ACTION_NEEDS_REVIEW,
                "target": "runtime_governance_blockers",
                "blocking_issue_count": len(report.get("governance_blockers", [])),
                "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
                "data_only": True,
            }
        )
    return actions or [
        {
            "action_type": ACTION_NEEDS_REVIEW,
            "target": "runtime_governance_closure",
            "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
            "data_only": True,
        }
    ]


def build_audit_ready_closure_summary(closure_report: Any) -> Dict[str, Any]:
    report = _mapping(closure_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "closure_id": _text(report.get("closure_id")),
        "closure_state": _text(report.get("closure_state")),
        "forensic_ready": bool(report.get("forensic_ready")),
        "evidence_ready": bool(report.get("evidence_ready")),
        "seal_ready": bool(report.get("seal_ready")),
        "continuation_ready": bool(report.get("continuation_ready")),
        "cross_session_ready": bool(report.get("cross_session_ready")),
        "self_edit_converged": bool(report.get("self_edit_converged")),
        "landing_consistent": bool(report.get("landing_consistent")),
        "governance_blocker_count": len(report.get("governance_blockers", []) or []),
        "recommended_action_count": len(report.get("recommended_actions", []) or []),
        "affected_repair_chain_ids": copy.deepcopy(report.get("affected_repair_chain_ids", [])),
        "closure_score": report.get("closure_score", 0.0),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
        "audit_log_written": False,
    }


def build_runtime_governance_closure_report(
    *,
    forensic_report: Any | None = None,
    self_edit_flow: Any | None = None,
    continuation_recommendation: Any | None = None,
    cross_session_handoff: Any | None = None,
    convergence_report: Any | None = None,
    landing_consistency_report: Any | None = None,
    snapshot_seal: Any | None = None,
) -> Dict[str, Any]:
    """Build an audit-ready, read-only runtime governance closure report."""

    forensic = _mapping(forensic_report)
    seal = _mapping(snapshot_seal) or (
        seal_replay_reconstruction_report(_mapping(forensic.get("reconstruction_report")))
        if forensic.get("reconstruction_report")
        else {}
    )
    landing = _normalize_landing_consistency(landing_consistency_report) or _derive_landing_consistency(self_edit_flow)
    continuation = _mapping(continuation_recommendation) or (
        build_autonomous_continuation_recommendation(
            forensic,
            landing_consistency_report=landing if landing else None,
        )
        if forensic
        else {}
    )
    convergence = _mapping(convergence_report) or (
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
    missing_layers = detect_missing_closure_layers(
        forensic_report=forensic,
        continuation_recommendation=continuation,
        cross_session_handoff=handoff,
        convergence_report=convergence,
        landing_consistency_report=landing,
        snapshot_seal=seal,
    )
    alignment = check_runtime_governance_alignment(
        forensic_report=forensic,
        continuation_recommendation=continuation,
        cross_session_handoff=handoff,
        convergence_report=convergence,
        landing_consistency_report=landing,
        snapshot_seal=seal,
    )
    blockers = detect_governance_blockers(
        alignment=alignment,
        missing_layers=missing_layers,
        continuation_recommendation=continuation,
        cross_session_handoff=handoff,
        convergence_report=convergence,
        landing_consistency_report=landing,
    )
    state = _closure_state(alignment, blockers, continuation, convergence)
    report = {
        "schema_version": SCHEMA_VERSION,
        "closure_id": "",
        "closure_state": state,
        "forensic_ready": bool(alignment["forensic_ready"]),
        "evidence_ready": bool(alignment["evidence_ready"]),
        "seal_ready": bool(alignment["seal_ready"]),
        "continuation_ready": bool(alignment["continuation_ready"]),
        "cross_session_ready": bool(alignment["cross_session_ready"]),
        "self_edit_converged": bool(alignment["self_edit_converged"]),
        "landing_consistent": bool(alignment["landing_consistent"]),
        "governance_blockers": blockers,
        "recommended_actions": [],
        "affected_repair_chain_ids": _affected_repair_chain_ids(forensic, continuation, handoff, convergence, seal),
        "audit_summary": {},
        "closure_score": _closure_score(alignment, blockers, missing_layers),
        "reason_codes": _reason_codes(
            blockers=blockers,
            missing_layers=missing_layers,
            continuation_recommendation=continuation,
            convergence_report=convergence,
        ),
        "missing_layers": missing_layers,
        "alignment": alignment,
        "seal_metadata": generate_replay_snapshot_seal_metadata(seal) if seal else {},
    }
    report["recommended_actions"] = build_runtime_governance_next_action_recommendations(report)
    report["closure_id"] = _closure_id(report)
    report["audit_summary"] = build_audit_ready_closure_summary(report)
    return report


def validate_runtime_governance_closure_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [
        field
        for field in CLOSURE_REQUIRED_FIELDS
        if field not in payload
    ]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("closure_state")) not in {
        CLOSURE_CLOSED,
        CLOSURE_NEEDS_REVIEW,
        CLOSURE_BLOCKED,
    }:
        invalid_fields.append({"field": "closure_state", "reason": "invalid_state"})
    for field in ("governance_blockers", "recommended_actions", "affected_repair_chain_ids", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    if "audit_summary" in payload and not isinstance(payload.get("audit_summary"), dict):
        invalid_fields.append({"field": "audit_summary", "reason": "expected_dict"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(CLOSURE_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _derive_landing_consistency(self_edit_flow: Any | None) -> Dict[str, Any]:
    flow = _mapping(self_edit_flow)
    if not flow:
        return {}
    landing = flow.get("landing")
    if not isinstance(landing, dict) and isinstance(flow.get("stages"), dict):
        landing = flow["stages"].get("landing")
    return build_execution_landing_consistency_report({"self_edit": landing if isinstance(landing, dict) else {}})


def _normalize_landing_consistency(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _seal_ready(seal: Mapping[str, Any], forensic: Mapping[str, Any]) -> bool:
    if not seal:
        return False
    report_id = _text(forensic.get("report_id"))
    return (
        _text(seal.get("seal_version")) == SEAL_VERSION
        and bool(_text(seal.get("snapshot_seal_id")))
        and bool(_text(seal.get("replay_hash")))
        and bool(_text(seal.get("integrity_hash")))
        and bool(_text(seal.get("divergence_hash")))
        and (not report_id or _text(seal.get("report_id")) == report_id)
    )


def _closure_state(
    alignment: Mapping[str, Any],
    blockers: Iterable[Any],
    continuation: Mapping[str, Any],
    convergence: Mapping[str, Any],
) -> str:
    blocker_list = list(blockers)
    if any(_hard_blocker(item) for item in blocker_list):
        return CLOSURE_BLOCKED
    if _text(continuation.get("continuation_state")) == STATE_BLOCKED:
        return CLOSURE_BLOCKED
    if _text(convergence.get("convergence_state")) == CONVERGENCE_BLOCKED:
        return CLOSURE_BLOCKED
    required = (
        "forensic_ready",
        "evidence_ready",
        "seal_ready",
        "continuation_ready",
        "cross_session_ready",
        "self_edit_converged",
        "landing_consistent",
    )
    if all(bool(alignment.get(key)) for key in required):
        return CLOSURE_CLOSED
    return CLOSURE_NEEDS_REVIEW


def _hard_blocker(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    kind = _text(item.get("kind"))
    if kind in {
        "continuation_blocked",
        "self_edit_convergence_blocked",
        "cross_session_handoff_invalid",
        "missing_required_fields",
        "incompatible_field",
        "contract_validation_failed",
    }:
        return True
    if kind == "layer_not_ready" and _text(item.get("layer")) in {
        "forensic_stack",
        "evidence_bundle",
        "replay_snapshot_seal",
        "execution_landing_consistency",
    }:
        return True
    return False


def _closure_score(alignment: Mapping[str, Any], blockers: Iterable[Any], missing_layers: Iterable[Any]) -> float:
    readiness_keys = (
        "forensic_ready",
        "evidence_ready",
        "seal_ready",
        "continuation_ready",
        "cross_session_ready",
        "self_edit_converged",
        "landing_consistent",
    )
    ready_count = sum(1 for key in readiness_keys if alignment.get(key))
    penalty = len(list(blockers)) + len(list(missing_layers))
    score = max(0.0, (ready_count / len(readiness_keys)) - (penalty * 0.04))
    return round(score, 4)


def _reason_codes(
    *,
    blockers: Iterable[Mapping[str, Any]],
    missing_layers: Iterable[Any],
    continuation_recommendation: Mapping[str, Any],
    convergence_report: Mapping[str, Any],
) -> List[str]:
    codes: List[Any] = []
    if list(missing_layers):
        codes.append("missing_closure_layers")
    codes.extend(item.get("kind") for item in blockers if isinstance(item, dict))
    codes.extend(_string_list(continuation_recommendation.get("reason_codes")))
    codes.extend(_string_list(convergence_report.get("reason_codes")))
    return _sorted_unique(codes)


def _affected_repair_chain_ids(
    forensic: Mapping[str, Any],
    continuation: Mapping[str, Any],
    handoff: Mapping[str, Any],
    convergence: Mapping[str, Any],
    seal: Mapping[str, Any],
) -> List[str]:
    forensic_summary = summarize_runtime_forensic_stack(forensic)
    evidence_refs = _mapping(convergence.get("evidence_refs"))
    return _sorted_unique(
        [
            *_string_list(forensic_summary.get("repair_chain_ids")),
            *_string_list(continuation.get("affected_repair_chain_ids")),
            *_string_list(handoff.get("affected_repair_chain_ids")),
            *_string_list(evidence_refs.get("repair_chain_ids")),
            *_string_list(seal.get("repair_chain_ids")),
        ]
    )


def _dedupe_blockers(blockers: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in blockers:
        if isinstance(item, dict):
            payload = copy.deepcopy(item)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _closure_id(report: Mapping[str, Any]) -> str:
    payload = {
        "closure_state": report.get("closure_state"),
        "forensic_ready": report.get("forensic_ready"),
        "evidence_ready": report.get("evidence_ready"),
        "seal_ready": report.get("seal_ready"),
        "continuation_ready": report.get("continuation_ready"),
        "cross_session_ready": report.get("cross_session_ready"),
        "self_edit_converged": report.get("self_edit_converged"),
        "landing_consistent": report.get("landing_consistent"),
        "governance_blockers": report.get("governance_blockers", []),
        "affected_repair_chain_ids": report.get("affected_repair_chain_ids", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "runtime-governance-closure-" + _stable_hash(payload)[:16]


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
