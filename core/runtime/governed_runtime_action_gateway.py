from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.autonomous_continuation_policy import (
    ACTION_BLOCKED,
    ACTION_NEEDS_REVIEW,
    ACTION_NO_ACTION,
    ACTION_PLANNER_HANDOFF_RECOMMENDED,
    ACTION_REPAIR_RECOMMENDED,
    ACTION_REPLAY_RECOMMENDED,
)
from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report
from core.runtime.governance_transition_readiness import (
    TRANSITION_BLOCKED,
    TRANSITION_READY,
    build_governance_transition_readiness_report,
    validate_governance_transition_readiness_report,
)
from core.runtime.runtime_forensic_stack import summarize_runtime_forensic_stack
from core.runtime.runtime_replay_snapshot_seal import (
    generate_replay_snapshot_seal_metadata,
    seal_replay_reconstruction_report,
)


SCHEMA_VERSION = "governed_runtime_action_gateway.v1"

GATEWAY_READY = "ready"
GATEWAY_DRY_RUN_ONLY = "dry_run_only"
GATEWAY_APPROVAL_REQUIRED = "approval_required"
GATEWAY_BLOCKED = "blocked"

REQUEST_NO_ACTION = "no_action"
REQUEST_DRY_RUN_REPAIR = "dry_run_repair"
REQUEST_DRY_RUN_REPLAY = "dry_run_replay"
REQUEST_DRY_RUN_PLANNER_HANDOFF = "dry_run_planner_handoff"
REQUEST_APPROVAL_REQUIRED_REPAIR = "approval_required_repair"
REQUEST_APPROVAL_REQUIRED_REPLAY = "approval_required_replay"
REQUEST_BLOCKED = "blocked"

ACTION_REQUEST_TYPES: tuple[str, ...] = (
    REQUEST_NO_ACTION,
    REQUEST_DRY_RUN_REPAIR,
    REQUEST_DRY_RUN_REPLAY,
    REQUEST_DRY_RUN_PLANNER_HANDOFF,
    REQUEST_APPROVAL_REQUIRED_REPAIR,
    REQUEST_APPROVAL_REQUIRED_REPLAY,
    REQUEST_BLOCKED,
)

GATEWAY_REQUIRED_FIELDS: tuple[str, ...] = (
    "gateway_id",
    "input_readiness_id",
    "gateway_state",
    "action_requests",
    "approval_required",
    "dry_run_only",
    "blocking_issues",
    "evidence_refs",
    "seal_refs",
    "affected_repair_chain_ids",
    "reason_codes",
)


def governed_action_request_types() -> List[str]:
    return list(ACTION_REQUEST_TYPES)


def governed_runtime_action_gateway_required_fields() -> List[str]:
    return list(GATEWAY_REQUIRED_FIELDS)


def validate_readiness_for_action_request_creation(readiness_report: Any) -> Dict[str, Any]:
    readiness = _mapping(readiness_report)
    validation = validate_governance_transition_readiness_report(readiness) if readiness else {"ok": False}
    transition_state = _text(readiness.get("transition_state"))
    blocking_issues = copy.deepcopy(readiness.get("blocking_issues", [])) if readiness else []
    if not readiness:
        blocking_issues.append({"kind": "readiness_report_missing"})
    if not validation.get("ok"):
        blocking_issues.append(
            {
                "kind": "readiness_report_invalid",
                "missing_fields": copy.deepcopy(validation.get("missing_fields", [])),
                "invalid_fields": copy.deepcopy(validation.get("invalid_fields", [])),
            }
        )
    if transition_state == TRANSITION_BLOCKED:
        blocking_issues.append({"kind": "readiness_blocked"})
    return {
        "ok": bool(validation.get("ok")) and transition_state != TRANSITION_BLOCKED,
        "transition_state": transition_state,
        "blocking_issues": _dedupe_issues(blocking_issues),
        "reason_codes": _sorted_unique(
            [
                *_string_list(readiness.get("reason_codes")),
                *[
                    issue.get("kind")
                    for issue in blocking_issues
                    if isinstance(issue, dict)
                ],
            ]
        ),
    }


def build_gateway_evidence_refs(forensic_report: Any | None = None, readiness_report: Any | None = None) -> Dict[str, Any]:
    forensic = _mapping(forensic_report)
    readiness = _mapping(readiness_report)
    summary = summarize_runtime_forensic_stack(forensic) if forensic else {}
    return {
        "forensic_report_id": _text(forensic.get("report_id") or summary.get("report_id")),
        "evidence_schema_version": _text(_mapping(forensic.get("evidence_bundle")).get("schema_version")),
        "source_record_count": _safe_int(summary.get("source_record_count")),
        "repair_chain_ids": _sorted_unique(summary.get("repair_chain_ids")),
        "input_readiness_id": _text(readiness.get("readiness_id")),
    }


def build_gateway_seal_refs(snapshot_seal: Any | None = None, forensic_report: Any | None = None) -> Dict[str, Any]:
    forensic = _mapping(forensic_report)
    seal = _mapping(snapshot_seal) or (
        seal_replay_reconstruction_report(_mapping(forensic.get("reconstruction_report")))
        if forensic.get("reconstruction_report")
        else {}
    )
    metadata = generate_replay_snapshot_seal_metadata(seal) if seal else {}
    return {
        "snapshot_seal_id": _text(metadata.get("snapshot_seal_id")),
        "seal_report_id": _text(metadata.get("report_id")),
        "seal_version": _text(metadata.get("seal_version")),
        "repair_chain_ids": _sorted_unique(metadata.get("repair_chain_ids")),
        "source_record_count": _safe_int(metadata.get("source_record_count")),
        "hashes": copy.deepcopy(metadata.get("hashes", {})),
    }


def map_recommended_actions_to_action_requests(
    recommended_actions: Iterable[Any],
    *,
    dry_run_only: bool = True,
    approval_required: bool = False,
    evidence_refs: Any | None = None,
    seal_refs: Any | None = None,
    affected_repair_chain_ids: Iterable[Any] | None = None,
    reason_codes: Iterable[Any] | None = None,
) -> List[Dict[str, Any]]:
    evidence = _mapping(evidence_refs)
    seal = _mapping(seal_refs)
    repair_chain_ids = _sorted_unique(affected_repair_chain_ids)
    inherited_reasons = _string_list(reason_codes)
    requests: List[Dict[str, Any]] = []
    for action in recommended_actions or []:
        payload = action if isinstance(action, dict) else {}
        action_type = _text(payload.get("action_type"))
        request_type = _request_type_for_action(
            action_type,
            dry_run_only=dry_run_only,
            approval_required=approval_required,
            reason_codes=[*inherited_reasons, *_string_list(payload.get("reason_codes"))],
        )
        requests.append(
            _action_request(
                request_type=request_type,
                source_action=payload,
                dry_run_only=dry_run_only,
                approval_required=approval_required and request_type.startswith("approval_required_"),
                evidence_refs=evidence,
                seal_refs=seal,
                affected_repair_chain_ids=_sorted_unique(
                    [
                        *repair_chain_ids,
                        *_string_list(payload.get("affected_repair_chain_ids")),
                    ]
                ),
                reason_codes=_sorted_unique(
                    [
                        *inherited_reasons,
                        *_string_list(payload.get("reason_codes")),
                    ]
                ),
            )
        )
    if not requests:
        requests.append(
            _action_request(
                request_type=REQUEST_NO_ACTION,
                source_action={},
                dry_run_only=dry_run_only,
                approval_required=False,
                evidence_refs=evidence,
                seal_refs=seal,
                affected_repair_chain_ids=repair_chain_ids,
                reason_codes=inherited_reasons,
            )
        )
    return _dedupe_requests(requests)


def build_dry_run_action_plan(
    readiness_report: Any,
    *,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
) -> Dict[str, Any]:
    readiness = _mapping(readiness_report)
    evidence_refs = build_gateway_evidence_refs(forensic_report, readiness)
    seal_refs = build_gateway_seal_refs(snapshot_seal, forensic_report)
    action_requests = map_recommended_actions_to_action_requests(
        readiness.get("recommended_actions", []),
        dry_run_only=True,
        approval_required=False,
        evidence_refs=evidence_refs,
        seal_refs=seal_refs,
        affected_repair_chain_ids=_affected_repair_chain_ids(readiness, evidence_refs, seal_refs),
        reason_codes=readiness.get("reason_codes", []),
    )
    return {
        "plan_type": "dry_run_only",
        "input_readiness_id": _text(readiness.get("readiness_id")),
        "action_requests": action_requests,
        "dry_run_only": True,
        "approval_required": False,
    }


def build_approval_required_action_requests(
    readiness_report: Any,
    *,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
) -> List[Dict[str, Any]]:
    readiness = _mapping(readiness_report)
    evidence_refs = build_gateway_evidence_refs(forensic_report, readiness)
    seal_refs = build_gateway_seal_refs(snapshot_seal, forensic_report)
    return map_recommended_actions_to_action_requests(
        readiness.get("recommended_actions", []),
        dry_run_only=False,
        approval_required=True,
        evidence_refs=evidence_refs,
        seal_refs=seal_refs,
        affected_repair_chain_ids=_affected_repair_chain_ids(readiness, evidence_refs, seal_refs),
        reason_codes=readiness.get("reason_codes", []),
    )


def build_governed_action_request_gateway_report(
    *,
    readiness_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    approval_required: bool = False,
    dry_run_only: bool = True,
    self_edit_flow: Any | None = None,
    landing_consistency_report: Any | None = None,
    windows_runtime_report: Any | None = None,
) -> Dict[str, Any]:
    """Build governed runtime action requests as data only; no actions are executed."""

    forensic = _mapping(forensic_report)
    readiness = _mapping(readiness_report) or build_governance_transition_readiness_report(
        forensic_report=forensic if forensic else None,
        self_edit_flow=self_edit_flow,
        landing_consistency_report=(
            _normalize_landing(landing_consistency_report)
            if landing_consistency_report is not None
            else None
        ),
        snapshot_seal=snapshot_seal,
        windows_runtime_report=windows_runtime_report,
    )
    validation = validate_readiness_for_action_request_creation(readiness)
    evidence_refs = build_gateway_evidence_refs(forensic, readiness)
    seal_refs = build_gateway_seal_refs(snapshot_seal, forensic)
    affected = _affected_repair_chain_ids(readiness, evidence_refs, seal_refs)
    if not validation["ok"]:
        action_requests = [
            _action_request(
                request_type=REQUEST_BLOCKED,
                source_action={"action_type": ACTION_BLOCKED},
                dry_run_only=True,
                approval_required=False,
                evidence_refs=evidence_refs,
                seal_refs=seal_refs,
                affected_repair_chain_ids=affected,
                reason_codes=validation["reason_codes"],
            )
        ]
        gateway_state = GATEWAY_BLOCKED
        effective_dry_run = True
        effective_approval = False
    else:
        effective_dry_run = bool(dry_run_only)
        effective_approval = bool(approval_required) and not effective_dry_run
        action_requests = map_recommended_actions_to_action_requests(
            readiness.get("recommended_actions", []),
            dry_run_only=effective_dry_run,
            approval_required=effective_approval,
            evidence_refs=evidence_refs,
            seal_refs=seal_refs,
            affected_repair_chain_ids=affected,
            reason_codes=readiness.get("reason_codes", []),
        )
        if effective_approval:
            gateway_state = GATEWAY_APPROVAL_REQUIRED
        elif effective_dry_run:
            gateway_state = GATEWAY_READY if _text(readiness.get("transition_state")) == TRANSITION_READY else GATEWAY_DRY_RUN_ONLY
        else:
            gateway_state = GATEWAY_READY
    report = {
        "schema_version": SCHEMA_VERSION,
        "gateway_id": "",
        "input_readiness_id": _text(readiness.get("readiness_id")),
        "gateway_state": gateway_state,
        "action_requests": action_requests,
        "approval_required": effective_approval,
        "dry_run_only": effective_dry_run,
        "blocking_issues": validation["blocking_issues"],
        "evidence_refs": evidence_refs,
        "seal_refs": seal_refs,
        "affected_repair_chain_ids": affected,
        "reason_codes": _sorted_unique([*validation["reason_codes"], *_string_list(readiness.get("reason_codes"))]),
    }
    report["gateway_id"] = _gateway_id(report)
    return report


def validate_governed_action_gateway_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in GATEWAY_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("gateway_state")) not in {
        GATEWAY_READY,
        GATEWAY_DRY_RUN_ONLY,
        GATEWAY_APPROVAL_REQUIRED,
        GATEWAY_BLOCKED,
    }:
        invalid_fields.append({"field": "gateway_state", "reason": "invalid_state"})
    for field in ("action_requests", "blocking_issues", "affected_repair_chain_ids", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    for field in ("evidence_refs", "seal_refs"):
        if field in payload and not isinstance(payload.get(field), dict):
            invalid_fields.append({"field": field, "reason": "expected_dict"})
    for request in payload.get("action_requests", []) if isinstance(payload.get("action_requests"), list) else []:
        if isinstance(request, dict) and _text(request.get("request_type")) not in ACTION_REQUEST_TYPES:
            invalid_fields.append({"field": "action_requests", "reason": "invalid_request_type"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(GATEWAY_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _request_type_for_action(
    action_type: str,
    *,
    dry_run_only: bool,
    approval_required: bool,
    reason_codes: Iterable[Any],
) -> str:
    if action_type in {ACTION_BLOCKED, REQUEST_BLOCKED}:
        return REQUEST_BLOCKED
    if action_type == ACTION_NO_ACTION:
        return REQUEST_NO_ACTION
    reasons = set(_string_list(reason_codes))
    wants_replay = action_type == ACTION_REPLAY_RECOMMENDED or any("replay" in reason for reason in reasons)
    wants_handoff = action_type == ACTION_PLANNER_HANDOFF_RECOMMENDED or any("planner" in reason for reason in reasons)
    wants_repair = action_type == ACTION_REPAIR_RECOMMENDED or any(
        token in reason
        for reason in reasons
        for token in ("repair", "chain", "parent", "missing")
    )
    if dry_run_only:
        if wants_handoff:
            return REQUEST_DRY_RUN_PLANNER_HANDOFF
        if wants_replay:
            return REQUEST_DRY_RUN_REPLAY
        if wants_repair or action_type == ACTION_NEEDS_REVIEW:
            return REQUEST_DRY_RUN_REPAIR
        return REQUEST_NO_ACTION
    if approval_required:
        if wants_replay:
            return REQUEST_APPROVAL_REQUIRED_REPLAY
        if wants_repair or wants_handoff or action_type == ACTION_NEEDS_REVIEW:
            return REQUEST_APPROVAL_REQUIRED_REPAIR
    return REQUEST_NO_ACTION


def _action_request(
    *,
    request_type: str,
    source_action: Mapping[str, Any],
    dry_run_only: bool,
    approval_required: bool,
    evidence_refs: Mapping[str, Any],
    seal_refs: Mapping[str, Any],
    affected_repair_chain_ids: Iterable[Any],
    reason_codes: Iterable[Any],
) -> Dict[str, Any]:
    payload = {
        "request_id": "",
        "request_type": request_type,
        "source_action_type": _text(source_action.get("action_type")),
        "dry_run_only": bool(dry_run_only),
        "approval_required": bool(approval_required),
        "execute": False,
        "planner_invoked": False,
        "task_enqueued": False,
        "evidence_refs": copy.deepcopy(dict(evidence_refs)),
        "seal_refs": copy.deepcopy(dict(seal_refs)),
        "affected_repair_chain_ids": _sorted_unique(affected_repair_chain_ids),
        "reason_codes": _sorted_unique(reason_codes),
    }
    payload["request_id"] = "governed-action-request-" + _stable_hash(payload)[:16]
    return payload


def _affected_repair_chain_ids(
    readiness: Mapping[str, Any],
    evidence_refs: Mapping[str, Any],
    seal_refs: Mapping[str, Any],
) -> List[str]:
    return _sorted_unique(
        [
            *_string_list(readiness.get("affected_repair_chain_ids")),
            *_string_list(evidence_refs.get("repair_chain_ids")),
            *_string_list(seal_refs.get("repair_chain_ids")),
        ]
    )


def _normalize_landing(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _dedupe_requests(requests: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for request in requests:
        payload = copy.deepcopy(dict(request))
        key = _stable_hash(payload)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(payload)
    return deduped


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _gateway_id(report: Mapping[str, Any]) -> str:
    payload = {
        "input_readiness_id": report.get("input_readiness_id"),
        "gateway_state": report.get("gateway_state"),
        "action_requests": report.get("action_requests", []),
        "blocking_issues": report.get("blocking_issues", []),
        "evidence_refs": report.get("evidence_refs", {}),
        "seal_refs": report.get("seal_refs", {}),
        "affected_repair_chain_ids": report.get("affected_repair_chain_ids", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-action-gateway-" + _stable_hash(payload)[:16]


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
