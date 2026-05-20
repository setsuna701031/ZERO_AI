from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report
from core.runtime.governance_transition_readiness import build_governance_transition_readiness_report
from core.runtime.governed_runtime_action_gateway import (
    ACTION_REQUEST_TYPES,
    REQUEST_APPROVAL_REQUIRED_REPAIR,
    REQUEST_APPROVAL_REQUIRED_REPLAY,
    REQUEST_BLOCKED,
    REQUEST_DRY_RUN_PLANNER_HANDOFF,
    REQUEST_DRY_RUN_REPAIR,
    REQUEST_DRY_RUN_REPLAY,
    REQUEST_NO_ACTION,
    build_governed_action_request_gateway_report,
    validate_governed_action_gateway_report,
)
from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report
from core.runtime.runtime_replay_snapshot_seal import generate_replay_snapshot_seal_metadata


SCHEMA_VERSION = "governed_runtime_dry_run_executor.v1"

DRY_RUN_COMPLETED = "dry_run_completed"
DRY_RUN_NEEDS_REVIEW = "needs_review"
DRY_RUN_BLOCKED = "blocked"

DRY_RUN_REQUIRED_FIELDS: tuple[str, ...] = (
    "dry_run_id",
    "source_gateway_id",
    "dry_run_state",
    "simulated_actions",
    "rejected_actions",
    "approval_required_actions",
    "evidence_refs",
    "seal_refs",
    "affected_repair_chain_ids",
    "blocking_issues",
    "reason_codes",
)


def governed_runtime_dry_run_required_fields() -> List[str]:
    return list(DRY_RUN_REQUIRED_FIELDS)


def validate_governed_action_request(action_request: Any) -> Dict[str, Any]:
    request = _mapping(action_request)
    missing = [
        field
        for field in (
            "request_id",
            "request_type",
            "dry_run_only",
            "approval_required",
            "execute",
            "planner_invoked",
            "task_enqueued",
            "evidence_refs",
            "seal_refs",
            "affected_repair_chain_ids",
            "reason_codes",
        )
        if field not in request
    ]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(request.get("request_type")) not in ACTION_REQUEST_TYPES:
        invalid_fields.append({"field": "request_type", "reason": "invalid_request_type"})
    for field in ("evidence_refs", "seal_refs"):
        if field in request and not isinstance(request.get(field), dict):
            invalid_fields.append({"field": field, "reason": "expected_dict"})
    for field in ("affected_repair_chain_ids", "reason_codes"):
        if field in request and not isinstance(request.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    return {
        "ok": not missing and not invalid_fields,
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "request_type": _text(request.get("request_type")),
    }


def reject_non_dry_run_execution_requests(action_requests: Iterable[Any]) -> List[Dict[str, Any]]:
    rejected: List[Dict[str, Any]] = []
    for request in action_requests or []:
        payload = _mapping(request)
        validation = validate_governed_action_request(payload)
        reasons: List[str] = []
        if not validation["ok"]:
            reasons.append("invalid_action_request")
        if payload.get("execute") is True:
            reasons.append("execute_true_not_allowed")
        if payload.get("planner_invoked") is True:
            reasons.append("planner_invoked_not_allowed")
        if payload.get("task_enqueued") is True:
            reasons.append("task_enqueued_not_allowed")
        if payload.get("dry_run_only") is not True and payload.get("approval_required") is not True:
            reasons.append("non_dry_run_request")
        if _text(payload.get("request_type")) == REQUEST_BLOCKED:
            reasons.append("blocked_request")
        if reasons:
            rejected.append(
                {
                    "request_id": _text(payload.get("request_id")),
                    "request_type": _text(payload.get("request_type")),
                    "rejection_reasons": _sorted_unique(reasons),
                    "validation": validation,
                }
            )
    return rejected


def simulate_governed_action_request(action_request: Any) -> Dict[str, Any]:
    request = _mapping(action_request)
    request_type = _text(request.get("request_type"))
    simulation_type = {
        REQUEST_NO_ACTION: "no_action_simulation",
        REQUEST_DRY_RUN_REPAIR: "repair_dry_run_simulation",
        REQUEST_DRY_RUN_REPLAY: "replay_dry_run_simulation",
        REQUEST_DRY_RUN_PLANNER_HANDOFF: "planner_handoff_dry_run_simulation",
    }.get(request_type, "")
    return {
        "request_id": _text(request.get("request_id")),
        "request_type": request_type,
        "simulation_type": simulation_type,
        "simulated": bool(simulation_type),
        "execute": False,
        "planner_invoked": False,
        "task_enqueued": False,
        "evidence_refs": copy.deepcopy(request.get("evidence_refs", {})),
        "seal_refs": copy.deepcopy(request.get("seal_refs", {})),
        "affected_repair_chain_ids": _sorted_unique(request.get("affected_repair_chain_ids")),
        "reason_codes": _sorted_unique(request.get("reason_codes")),
    }


def summarize_approval_required_actions(action_requests: Iterable[Any]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for request in action_requests or []:
        payload = _mapping(request)
        if payload.get("approval_required") is True or _text(payload.get("request_type")) in {
            REQUEST_APPROVAL_REQUIRED_REPAIR,
            REQUEST_APPROVAL_REQUIRED_REPLAY,
        }:
            summaries.append(
                {
                    "request_id": _text(payload.get("request_id")),
                    "request_type": _text(payload.get("request_type")),
                    "approval_required": True,
                    "approval_flow_invoked": False,
                    "execute": False,
                    "reason_codes": _sorted_unique(payload.get("reason_codes")),
                }
            )
    return summaries


def build_governed_runtime_dry_run_report(
    *,
    gateway_report: Any | None = None,
    action_requests: Iterable[Any] | None = None,
    readiness_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    landing_consistency_report: Any | None = None,
    governance_closure_report: Any | None = None,
) -> Dict[str, Any]:
    """Execute governed runtime action requests in dry-run mode only."""

    closure = _mapping(governance_closure_report)
    if not closure and forensic_report is not None:
        closure = build_runtime_governance_closure_report(
            forensic_report=forensic_report,
            landing_consistency_report=(
                _normalize_landing(landing_consistency_report)
                if landing_consistency_report is not None
                else None
            ),
            snapshot_seal=snapshot_seal,
        )
    readiness = _mapping(readiness_report)
    if not readiness and (forensic_report is not None or closure):
        readiness = build_governance_transition_readiness_report(
            governance_closure_report=closure if closure else None,
            forensic_report=forensic_report,
            landing_consistency_report=(
                _normalize_landing(landing_consistency_report)
                if landing_consistency_report is not None
                else None
            ),
            snapshot_seal=snapshot_seal,
        )
    gateway = _mapping(gateway_report) or (
        build_governed_action_request_gateway_report(
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
        if readiness or forensic_report is not None
        else {}
    )
    requests = [
        copy.deepcopy(item)
        for item in (list(action_requests) if action_requests is not None else gateway.get("action_requests", []))
        if isinstance(item, dict)
    ]
    gateway_validation = validate_governed_action_gateway_report(gateway) if gateway else {"ok": False}
    rejected = reject_non_dry_run_execution_requests(requests)
    rejected_ids = {_text(item.get("request_id")) for item in rejected}
    approval_required = summarize_approval_required_actions(requests)
    approval_ids = {_text(item.get("request_id")) for item in approval_required}
    simulated = [
        simulate_governed_action_request(request)
        for request in requests
        if _text(request.get("request_id")) not in rejected_ids
        and _text(request.get("request_id")) not in approval_ids
        and _text(request.get("request_type")) in {
            REQUEST_NO_ACTION,
            REQUEST_DRY_RUN_REPAIR,
            REQUEST_DRY_RUN_REPLAY,
            REQUEST_DRY_RUN_PLANNER_HANDOFF,
        }
    ]
    blocking_issues = _dedupe_issues(
        [
            *(_mapping(gateway).get("blocking_issues", []) or []),
            *[
                {"kind": reason, "request_id": item.get("request_id")}
                for item in rejected
                for reason in item.get("rejection_reasons", [])
            ],
            *([] if gateway_validation.get("ok") else [{"kind": "gateway_report_invalid"}]),
        ]
    )
    state = _dry_run_state(
        simulated_actions=simulated,
        rejected_actions=rejected,
        approval_required_actions=approval_required,
        blocking_issues=blocking_issues,
    )
    evidence_refs = _merged_refs("evidence_refs", gateway, requests, simulated)
    seal_refs = _merged_refs("seal_refs", gateway, requests, simulated)
    if snapshot_seal is not None and not seal_refs:
        seal_refs = generate_replay_snapshot_seal_metadata(snapshot_seal)
    report = {
        "schema_version": SCHEMA_VERSION,
        "dry_run_id": "",
        "source_gateway_id": _text(gateway.get("gateway_id")),
        "dry_run_state": state,
        "simulated_actions": simulated,
        "rejected_actions": rejected,
        "approval_required_actions": approval_required,
        "evidence_refs": evidence_refs,
        "seal_refs": seal_refs,
        "affected_repair_chain_ids": _affected_repair_chain_ids(gateway, requests, simulated),
        "blocking_issues": blocking_issues,
        "reason_codes": _reason_codes(gateway, requests, rejected, approval_required, blocking_issues),
    }
    report["dry_run_id"] = _dry_run_id(report)
    return report


def validate_governed_runtime_dry_run_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in DRY_RUN_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("dry_run_state")) not in {
        DRY_RUN_COMPLETED,
        DRY_RUN_NEEDS_REVIEW,
        DRY_RUN_BLOCKED,
    }:
        invalid_fields.append({"field": "dry_run_state", "reason": "invalid_state"})
    for field in (
        "simulated_actions",
        "rejected_actions",
        "approval_required_actions",
        "affected_repair_chain_ids",
        "blocking_issues",
        "reason_codes",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    for field in ("evidence_refs", "seal_refs"):
        if field in payload and not isinstance(payload.get(field), dict):
            invalid_fields.append({"field": field, "reason": "expected_dict"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(DRY_RUN_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _dry_run_state(
    *,
    simulated_actions: Iterable[Any],
    rejected_actions: Iterable[Any],
    approval_required_actions: Iterable[Any],
    blocking_issues: Iterable[Any],
) -> str:
    if list(rejected_actions) or any(_hard_blocker(issue) for issue in blocking_issues):
        return DRY_RUN_BLOCKED
    if list(approval_required_actions):
        return DRY_RUN_NEEDS_REVIEW
    if list(simulated_actions):
        return DRY_RUN_COMPLETED
    return DRY_RUN_NEEDS_REVIEW


def _hard_blocker(issue: Any) -> bool:
    if not isinstance(issue, dict):
        return False
    return _text(issue.get("kind")) in {
        "execute_true_not_allowed",
        "planner_invoked_not_allowed",
        "task_enqueued_not_allowed",
        "non_dry_run_request",
        "blocked_request",
        "gateway_report_invalid",
    }


def _normalize_landing(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _merged_refs(
    field: str,
    gateway: Mapping[str, Any],
    requests: Iterable[Mapping[str, Any]],
    simulated: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    if isinstance(gateway.get(field), dict) and gateway.get(field):
        return copy.deepcopy(gateway[field])
    for item in [*list(simulated), *list(requests)]:
        refs = item.get(field)
        if isinstance(refs, dict) and refs:
            return copy.deepcopy(refs)
    return {}


def _affected_repair_chain_ids(
    gateway: Mapping[str, Any],
    requests: Iterable[Mapping[str, Any]],
    simulated: Iterable[Mapping[str, Any]],
) -> List[str]:
    return _sorted_unique(
        [
            *_string_list(gateway.get("affected_repair_chain_ids")),
            *[
                chain_id
                for item in [*list(requests), *list(simulated)]
                for chain_id in _string_list(item.get("affected_repair_chain_ids"))
            ],
        ]
    )


def _reason_codes(
    gateway: Mapping[str, Any],
    requests: Iterable[Mapping[str, Any]],
    rejected: Iterable[Mapping[str, Any]],
    approval_required: Iterable[Mapping[str, Any]],
    blocking_issues: Iterable[Mapping[str, Any]],
) -> List[str]:
    return _sorted_unique(
        [
            *_string_list(gateway.get("reason_codes")),
            *[
                code
                for item in requests
                for code in _string_list(item.get("reason_codes"))
            ],
            *[
                reason
                for item in rejected
                for reason in _string_list(item.get("rejection_reasons"))
            ],
            *[
                code
                for item in approval_required
                for code in _string_list(item.get("reason_codes"))
            ],
            *[
                item.get("kind")
                for item in blocking_issues
                if isinstance(item, dict)
            ],
        ]
    )


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _dry_run_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_gateway_id": report.get("source_gateway_id"),
        "dry_run_state": report.get("dry_run_state"),
        "simulated_actions": report.get("simulated_actions", []),
        "rejected_actions": report.get("rejected_actions", []),
        "approval_required_actions": report.get("approval_required_actions", []),
        "affected_repair_chain_ids": report.get("affected_repair_chain_ids", []),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-dry-run-" + _stable_hash(payload)[:16]


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
