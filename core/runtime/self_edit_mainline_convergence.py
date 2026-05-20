from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.autonomous_continuation_policy import (
    ACTION_BLOCKED,
    ACTION_NEEDS_REVIEW,
    ACTION_NO_ACTION,
    ACTION_REPAIR_RECOMMENDED,
    ACTION_REPLAY_RECOMMENDED,
    STATE_BLOCKED,
    STATE_NEEDS_REVIEW,
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


SCHEMA_VERSION = "self_edit_mainline_convergence.v1"

CONVERGENCE_CONVERGED = "converged"
CONVERGENCE_NEEDS_REVIEW = "needs_review"
CONVERGENCE_BLOCKED = "blocked"

MAINLINE_STAGES: tuple[str, ...] = (
    "policy",
    "mutation",
    "verification",
    "rollback",
    "evidence",
    "landing",
)

STAGE_REQUIRED_FIELDS: Dict[str, tuple[str, ...]] = {
    "policy": ("policy_id", "decision"),
    "mutation": ("mutation_ref", "status"),
    "verification": ("verification_result",),
    "rollback": ("rollback_result",),
    "evidence": ("evidence_ref",),
    "landing": (
        "task_id",
        "session_id",
        "status",
        "execution_result",
        "verification_result",
        "rollback_result",
        "audit_ref",
        "evidence_ref",
    ),
}

CONVERGENCE_REQUIRED_FIELDS: tuple[str, ...] = (
    "convergence_id",
    "self_edit_flow_id",
    "convergence_state",
    "checked_stages",
    "missing_stages",
    "incompatible_fields",
    "evidence_refs",
    "landing_consistency",
    "continuation_recommendation",
    "cross_session_handoff_ready",
    "blocking_issues",
    "convergence_score",
    "reason_codes",
)


def self_edit_mainline_stages() -> List[str]:
    return list(MAINLINE_STAGES)


def self_edit_convergence_required_fields() -> List[str]:
    return list(CONVERGENCE_REQUIRED_FIELDS)


def collect_self_edit_mainline_contract_shape(self_edit_flow: Any) -> Dict[str, Any]:
    """Collect the read-only shape of a self-edit flow against the mainline stages."""

    flow = _mapping(self_edit_flow)
    stages = _stage_sources(flow)
    stage_shapes: Dict[str, Dict[str, Any]] = {}
    for stage in MAINLINE_STAGES:
        value = stages.get(stage)
        fields = _shape_fields(value)
        stage_shapes[stage] = {
            "stage": stage,
            "present": _stage_present(value),
            "fields": fields,
            "field_names": sorted(fields),
            "required_fields": list(STAGE_REQUIRED_FIELDS[stage]),
            "missing_fields": _missing_fields(fields, STAGE_REQUIRED_FIELDS[stage]),
            "unexpected_type": "" if _stage_type_ok(value) else type(value).__name__,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "self_edit_flow_id": _self_edit_flow_id(flow),
        "checked_stages": list(MAINLINE_STAGES),
        "stages": stage_shapes,
    }


def validate_self_edit_mainline_stages(self_edit_flow: Any) -> Dict[str, Any]:
    shape = collect_self_edit_mainline_contract_shape(self_edit_flow)
    invalid_stages = [
        {
            "stage": stage,
            "missing_fields": copy.deepcopy(stage_shape.get("missing_fields", [])),
            "unexpected_type": _text(stage_shape.get("unexpected_type")),
        }
        for stage, stage_shape in shape["stages"].items()
        if stage_shape.get("missing_fields") or stage_shape.get("unexpected_type")
    ]
    return {
        "ok": not invalid_stages,
        "schema_version": SCHEMA_VERSION,
        "self_edit_flow_id": shape["self_edit_flow_id"],
        "checked_stages": shape["checked_stages"],
        "invalid_stages": invalid_stages,
    }


def detect_missing_convergence_stages(self_edit_flow: Any) -> List[str]:
    shape = collect_self_edit_mainline_contract_shape(self_edit_flow)
    return [
        stage
        for stage, stage_shape in shape["stages"].items()
        if not stage_shape.get("present")
    ]


def detect_incompatible_landing_fields(landing_or_flow: Any) -> List[Dict[str, Any]]:
    report = _landing_consistency_report(landing_or_flow)
    return copy.deepcopy(report.get("incompatible_fields", []))


def detect_missing_forensic_evidence_refs(
    self_edit_flow: Any,
    *,
    forensic_report: Any | None = None,
) -> List[Dict[str, Any]]:
    flow = _mapping(self_edit_flow)
    landing = _landing_source(flow)
    evidence = _stage_sources(flow).get("evidence")
    missing: List[Dict[str, Any]] = []
    if not _text(_mapping(evidence).get("evidence_ref") or landing.get("evidence_ref")):
        missing.append({"kind": "missing_evidence_ref", "stage": "evidence"})
    if not _text(landing.get("audit_ref")):
        missing.append({"kind": "missing_audit_ref", "stage": "landing"})
    if forensic_report is not None:
        summary = summarize_runtime_forensic_stack(_mapping(forensic_report))
        if not _text(summary.get("report_id")):
            missing.append({"kind": "missing_forensic_report_id", "stage": "forensic"})
        if _safe_int(summary.get("source_record_count")) <= 0:
            missing.append({"kind": "missing_forensic_source_records", "stage": "forensic"})
    return missing


def build_self_edit_next_action_recommendations(
    convergence_report: Any,
) -> List[Dict[str, Any]]:
    report = _mapping(convergence_report)
    state = _text(report.get("convergence_state"))
    if state == CONVERGENCE_CONVERGED:
        return [
            {
                "action_type": ACTION_NO_ACTION,
                "reason_codes": [],
                "data_only": True,
            }
        ]
    actions: List[Dict[str, Any]] = []
    if report.get("missing_stages"):
        actions.append(
            {
                "action_type": ACTION_NEEDS_REVIEW,
                "target": "self_edit_mainline_stages",
                "missing_stages": copy.deepcopy(report.get("missing_stages", [])),
                "reason_codes": ["missing_convergence_stages"],
                "data_only": True,
            }
        )
    if report.get("incompatible_fields"):
        actions.append(
            {
                "action_type": ACTION_BLOCKED,
                "target": "execution_landing_consistency",
                "incompatible_fields": copy.deepcopy(report.get("incompatible_fields", [])),
                "reason_codes": ["landing_incompatible_fields"],
                "data_only": True,
            }
        )
    if _text(_mapping(report.get("continuation_recommendation")).get("continuation_state")) == STATE_NEEDS_REVIEW:
        actions.append(
            {
                "action_type": ACTION_REPAIR_RECOMMENDED,
                "target": "autonomous_continuation_policy",
                "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
                "data_only": True,
            }
        )
    if _text(_mapping(report.get("continuation_recommendation")).get("continuation_state")) == STATE_BLOCKED:
        actions.append(
            {
                "action_type": ACTION_BLOCKED,
                "target": "autonomous_continuation_policy",
                "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
                "data_only": True,
            }
        )
    return actions or [
        {
            "action_type": ACTION_REPLAY_RECOMMENDED,
            "target": "self_edit_forensic_evidence",
            "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
            "data_only": True,
        }
    ]


def build_self_edit_convergence_report(
    self_edit_flow: Any,
    *,
    forensic_report: Any | None = None,
    landing_consistency_report: Any | None = None,
    continuation_recommendation: Any | None = None,
) -> Dict[str, Any]:
    """Build a read-only convergence report for self-edit mainline alignment."""

    flow = _mapping(self_edit_flow)
    shape = collect_self_edit_mainline_contract_shape(flow)
    validation = validate_self_edit_mainline_stages(flow)
    missing_stages = detect_missing_convergence_stages(flow)
    landing_consistency = (
        _landing_consistency_report(landing_consistency_report)
        if landing_consistency_report is not None
        else _landing_consistency_report(flow)
    )
    incompatible_fields = copy.deepcopy(landing_consistency.get("incompatible_fields", []))
    missing_refs = detect_missing_forensic_evidence_refs(flow, forensic_report=forensic_report)
    continuation = (
        _mapping(continuation_recommendation)
        if continuation_recommendation is not None
        else (
            build_autonomous_continuation_recommendation(
                _mapping(forensic_report),
                landing_consistency_report=landing_consistency,
            )
            if forensic_report is not None
            else {}
        )
    )
    blocking_issues = _blocking_issues(
        invalid_stages=validation["invalid_stages"],
        landing_consistency=landing_consistency,
        missing_refs=missing_refs,
        continuation_recommendation=continuation,
    )
    state = _convergence_state(
        missing_stages=missing_stages,
        blocking_issues=blocking_issues,
        incompatible_fields=incompatible_fields,
        continuation_recommendation=continuation,
    )
    evidence_refs = _evidence_refs(flow, forensic_report=forensic_report)
    handoff = (
        build_cross_session_handoff_payload(
            source_session_id=_text(_landing_source(flow).get("session_id")),
            forensic_report=_mapping(forensic_report),
            continuation_recommendation=continuation,
        )
        if forensic_report is not None and continuation
        else {}
    )
    handoff_validation = validate_cross_session_handoff_payload(handoff) if handoff else {"ok": False}
    report = {
        "schema_version": SCHEMA_VERSION,
        "convergence_id": "",
        "self_edit_flow_id": shape["self_edit_flow_id"],
        "convergence_state": state,
        "checked_stages": copy.deepcopy(shape["checked_stages"]),
        "missing_stages": missing_stages,
        "incompatible_fields": incompatible_fields,
        "evidence_refs": evidence_refs,
        "landing_consistency": landing_consistency,
        "continuation_recommendation": continuation,
        "cross_session_handoff_ready": bool(handoff_validation.get("ok")) and state != CONVERGENCE_BLOCKED,
        "blocking_issues": blocking_issues,
        "convergence_score": _convergence_score(
            missing_stages=missing_stages,
            blocking_issues=blocking_issues,
            incompatible_fields=incompatible_fields,
            missing_refs=missing_refs,
        ),
        "reason_codes": _reason_codes(
            missing_stages=missing_stages,
            blocking_issues=blocking_issues,
            incompatible_fields=incompatible_fields,
            missing_refs=missing_refs,
            continuation_recommendation=continuation,
        ),
        "contract_shape": shape,
    }
    report["next_action_recommendations"] = build_self_edit_next_action_recommendations(report)
    report["convergence_id"] = _convergence_id(report)
    return report


def validate_self_edit_convergence_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [
        field
        for field in CONVERGENCE_REQUIRED_FIELDS
        if field not in payload
    ]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("convergence_state")) not in {
        CONVERGENCE_CONVERGED,
        CONVERGENCE_NEEDS_REVIEW,
        CONVERGENCE_BLOCKED,
    }:
        invalid_fields.append({"field": "convergence_state", "reason": "invalid_state"})
    for field in (
        "checked_stages",
        "missing_stages",
        "incompatible_fields",
        "blocking_issues",
        "reason_codes",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    for field in ("evidence_refs", "landing_consistency", "continuation_recommendation"):
        if field in payload and not isinstance(payload.get(field), dict):
            invalid_fields.append({"field": field, "reason": "expected_dict"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(CONVERGENCE_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _blocking_issues(
    *,
    invalid_stages: Iterable[Mapping[str, Any]],
    landing_consistency: Mapping[str, Any],
    missing_refs: Iterable[Mapping[str, Any]],
    continuation_recommendation: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for item in invalid_stages:
        if item.get("missing_fields") or item.get("unexpected_type"):
            issues.append(
                {
                    "kind": "invalid_stage",
                    "stage": _text(item.get("stage")),
                    "missing_fields": copy.deepcopy(item.get("missing_fields", [])),
                    "unexpected_type": _text(item.get("unexpected_type")),
                }
            )
    issues.extend(copy.deepcopy(landing_consistency.get("blocking_issues", [])))
    issues.extend(copy.deepcopy(list(missing_refs)))
    issues.extend(copy.deepcopy(continuation_recommendation.get("blocking_issues", [])))
    return issues


def _convergence_state(
    *,
    missing_stages: Iterable[Any],
    blocking_issues: Iterable[Any],
    incompatible_fields: Iterable[Any],
    continuation_recommendation: Mapping[str, Any],
) -> str:
    continuation_state = _text(continuation_recommendation.get("continuation_state"))
    if incompatible_fields or continuation_state == STATE_BLOCKED:
        return CONVERGENCE_BLOCKED
    if blocking_issues:
        blocking_kinds = {
            _text(item.get("kind"))
            for item in blocking_issues
            if isinstance(item, dict)
        }
        hard_blockers = {
            "incompatible_field",
            "missing_required_fields",
            "missing_evidence_ref",
            "missing_audit_ref",
            "contract_validation_failed",
        }
        if blocking_kinds.intersection(hard_blockers):
            return CONVERGENCE_BLOCKED
    if missing_stages or blocking_issues or continuation_state == STATE_NEEDS_REVIEW:
        return CONVERGENCE_NEEDS_REVIEW
    return CONVERGENCE_CONVERGED


def _convergence_score(
    *,
    missing_stages: Iterable[Any],
    blocking_issues: Iterable[Any],
    incompatible_fields: Iterable[Any],
    missing_refs: Iterable[Any],
) -> float:
    penalties = (
        len(list(missing_stages))
        + len(list(blocking_issues))
        + len(list(incompatible_fields))
        + len(list(missing_refs))
    )
    possible = len(MAINLINE_STAGES) + 6
    return round(max(0.0, 1.0 - (penalties / possible)), 4)


def _reason_codes(
    *,
    missing_stages: Iterable[Any],
    blocking_issues: Iterable[Mapping[str, Any]],
    incompatible_fields: Iterable[Any],
    missing_refs: Iterable[Mapping[str, Any]],
    continuation_recommendation: Mapping[str, Any],
) -> List[str]:
    codes: List[Any] = []
    if list(missing_stages):
        codes.append("missing_convergence_stages")
    if list(incompatible_fields):
        codes.append("landing_incompatible_fields")
    codes.extend(item.get("kind") for item in blocking_issues if isinstance(item, dict))
    codes.extend(item.get("kind") for item in missing_refs if isinstance(item, dict))
    codes.extend(_string_list(continuation_recommendation.get("reason_codes")))
    return _sorted_unique(codes)


def _evidence_refs(self_edit_flow: Mapping[str, Any], *, forensic_report: Any | None) -> Dict[str, Any]:
    stages = _stage_sources(self_edit_flow)
    evidence = _mapping(stages.get("evidence"))
    landing = _landing_source(self_edit_flow)
    forensic_summary = summarize_runtime_forensic_stack(_mapping(forensic_report)) if forensic_report is not None else {}
    return {
        "evidence_ref": _text(evidence.get("evidence_ref") or landing.get("evidence_ref")),
        "audit_ref": _text(landing.get("audit_ref")),
        "forensic_report_id": _text(forensic_summary.get("report_id")),
        "snapshot_seal_id": _text(forensic_summary.get("snapshot_seal_id")),
        "repair_chain_ids": _sorted_unique(forensic_summary.get("repair_chain_ids")),
    }


def _landing_consistency_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    if "landing" in payload or "stages" in payload:
        landing = _landing_source(payload)
        return build_execution_landing_consistency_report({"self_edit": landing})
    return build_execution_landing_consistency_report(payload)


def _stage_sources(flow: Mapping[str, Any]) -> Dict[str, Any]:
    stages = _mapping(flow.get("stages"))
    return {
        "policy": flow.get("policy") if "policy" in flow else stages.get("policy"),
        "mutation": flow.get("mutation") if "mutation" in flow else stages.get("mutation"),
        "verification": flow.get("verification") if "verification" in flow else stages.get("verification"),
        "rollback": flow.get("rollback") if "rollback" in flow else stages.get("rollback"),
        "evidence": flow.get("evidence") if "evidence" in flow else stages.get("evidence"),
        "landing": _landing_source(flow),
    }


def _landing_source(flow: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(flow.get("landing"), dict):
        return copy.deepcopy(flow["landing"])
    stages = _mapping(flow.get("stages"))
    if isinstance(stages.get("landing"), dict):
        return copy.deepcopy(stages["landing"])
    return {}


def _shape_fields(value: Any) -> Dict[str, str]:
    if isinstance(value, Mapping):
        if isinstance(value.get("fields"), Mapping):
            return {
                _text(key): _normalize_kind(kind)
                for key, kind in value["fields"].items()
                if _text(key)
            }
        return {
            _text(key): _kind(item)
            for key, item in value.items()
            if _text(key)
        }
    return {}


def _missing_fields(fields: Mapping[str, str], required_fields: Iterable[str]) -> List[str]:
    return [
        field
        for field in required_fields
        if field not in fields
    ]


def _stage_present(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value)


def _stage_type_ok(value: Any) -> bool:
    return value is None or isinstance(value, Mapping)


def _self_edit_flow_id(flow: Mapping[str, Any]) -> str:
    return _text(flow.get("self_edit_flow_id") or flow.get("flow_id") or flow.get("task_id"))


def _convergence_id(report: Mapping[str, Any]) -> str:
    payload = {
        "self_edit_flow_id": report.get("self_edit_flow_id"),
        "convergence_state": report.get("convergence_state"),
        "checked_stages": report.get("checked_stages", []),
        "missing_stages": report.get("missing_stages", []),
        "incompatible_fields": report.get("incompatible_fields", []),
        "evidence_refs": report.get("evidence_refs", {}),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "self-edit-convergence-" + _stable_hash(payload)[:16]


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


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, Mapping):
        return "dict"
    if isinstance(value, list):
        return "list"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, set):
        return "set"
    if value is None:
        return "none"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return type(value).__name__


def _normalize_kind(value: Any) -> str:
    text = _text(value)
    return text or _kind(value)


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
