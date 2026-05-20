from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.governed_runtime_action_gateway import build_governed_action_request_gateway_report
from core.runtime.governed_runtime_dry_run_executor import (
    DRY_RUN_BLOCKED,
    DRY_RUN_COMPLETED,
    DRY_RUN_NEEDS_REVIEW,
    build_governed_runtime_dry_run_report,
    validate_governed_runtime_dry_run_report,
)
from core.runtime.governance_transition_readiness import build_governance_transition_readiness_report
from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report
from core.runtime.runtime_replay_snapshot_seal import generate_replay_snapshot_seal_metadata


SCHEMA_VERSION = "governed_runtime_approval_gate.v1"

APPROVAL_APPROVED = "approved"
APPROVAL_NEEDS_REVIEW = "needs_review"
APPROVAL_BLOCKED = "blocked"

APPROVAL_GATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "approval_gate_id",
    "source_dry_run_id",
    "approval_state",
    "execution_eligible",
    "approval_required",
    "unresolved_approval_actions",
    "evidence_refs",
    "seal_refs",
    "affected_repair_chain_ids",
    "blocking_issues",
    "reason_codes",
)


def governed_runtime_approval_gate_required_fields() -> List[str]:
    return list(APPROVAL_GATE_REQUIRED_FIELDS)


def validate_dry_run_before_approval(dry_run_report: Any) -> Dict[str, Any]:
    dry_run = _mapping(dry_run_report)
    validation = validate_governed_runtime_dry_run_report(dry_run) if dry_run else {"ok": False}
    blocking_issues: List[Dict[str, Any]] = []
    if not dry_run:
        blocking_issues.append({"kind": "dry_run_report_missing"})
    if not validation.get("ok"):
        blocking_issues.append(
            {
                "kind": "dry_run_report_invalid",
                "missing_fields": copy.deepcopy(validation.get("missing_fields", [])),
                "invalid_fields": copy.deepcopy(validation.get("invalid_fields", [])),
            }
        )
    if _text(dry_run.get("dry_run_state")) == DRY_RUN_BLOCKED:
        blocking_issues.append({"kind": "dry_run_blocked"})
    if not _mapping(dry_run.get("evidence_refs")):
        blocking_issues.append({"kind": "missing_evidence_refs"})
    if not _mapping(dry_run.get("seal_refs")):
        blocking_issues.append({"kind": "missing_seal_refs"})
    unresolved = unresolved_approval_actions(dry_run)
    if unresolved:
        blocking_issues.append(
            {
                "kind": "unresolved_approval_actions",
                "count": len(unresolved),
            }
        )
    return {
        "ok": bool(validation.get("ok")) and not blocking_issues,
        "dry_run_state": _text(dry_run.get("dry_run_state")),
        "blocking_issues": _dedupe_issues(blocking_issues),
        "unresolved_approval_actions": unresolved,
        "reason_codes": _sorted_unique(
            [
                *_string_list(dry_run.get("reason_codes")),
                *[
                    issue.get("kind")
                    for issue in blocking_issues
                    if isinstance(issue, dict)
                ],
            ]
        ),
    }


def unresolved_approval_actions(dry_run_report: Any) -> List[Dict[str, Any]]:
    dry_run = _mapping(dry_run_report)
    return [
        copy.deepcopy(item)
        for item in dry_run.get("approval_required_actions", []) or []
        if isinstance(item, dict)
    ]


def build_controlled_execution_eligibility_summary(approval_gate_report: Any) -> Dict[str, Any]:
    report = _mapping(approval_gate_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "approval_gate_id": _text(report.get("approval_gate_id")),
        "source_dry_run_id": _text(report.get("source_dry_run_id")),
        "execution_eligible": bool(report.get("execution_eligible")),
        "approval_state": _text(report.get("approval_state")),
        "approval_required": bool(report.get("approval_required")),
        "unresolved_approval_action_count": len(report.get("unresolved_approval_actions", []) or []),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "affected_repair_chain_ids": copy.deepcopy(report.get("affected_repair_chain_ids", [])),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
        "execute": False,
        "planner_invoked": False,
        "task_enqueued": False,
    }


def build_governed_runtime_approval_gate_report(
    *,
    dry_run_report: Any | None = None,
    gateway_report: Any | None = None,
    readiness_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    governance_closure_report: Any | None = None,
) -> Dict[str, Any]:
    """Determine controlled-execution eligibility from dry-run results, data only."""

    closure = _mapping(governance_closure_report)
    if not closure and forensic_report is not None:
        closure = build_runtime_governance_closure_report(
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    readiness = _mapping(readiness_report)
    if not readiness and (closure or forensic_report is not None):
        readiness = build_governance_transition_readiness_report(
            governance_closure_report=closure if closure else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    gateway = _mapping(gateway_report)
    if not gateway and (readiness or forensic_report is not None):
        gateway = build_governed_action_request_gateway_report(
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    dry_run = _mapping(dry_run_report) or (
        build_governed_runtime_dry_run_report(
            gateway_report=gateway if gateway else None,
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            governance_closure_report=closure if closure else None,
        )
        if gateway or readiness or forensic_report is not None
        else {}
    )
    validation = validate_dry_run_before_approval(dry_run)
    approval_state = _approval_state(dry_run, validation)
    evidence_refs = _mapping(dry_run.get("evidence_refs"))
    seal_refs = _mapping(dry_run.get("seal_refs"))
    if snapshot_seal is not None and not seal_refs:
        seal_refs = generate_replay_snapshot_seal_metadata(snapshot_seal)
    report = {
        "schema_version": SCHEMA_VERSION,
        "approval_gate_id": "",
        "source_dry_run_id": _text(dry_run.get("dry_run_id")),
        "approval_state": approval_state,
        "execution_eligible": approval_state == APPROVAL_APPROVED,
        "approval_required": bool(validation["unresolved_approval_actions"]),
        "unresolved_approval_actions": validation["unresolved_approval_actions"],
        "evidence_refs": evidence_refs,
        "seal_refs": seal_refs,
        "affected_repair_chain_ids": _sorted_unique(dry_run.get("affected_repair_chain_ids")),
        "blocking_issues": validation["blocking_issues"],
        "reason_codes": validation["reason_codes"],
    }
    report["approval_gate_id"] = _approval_gate_id(report)
    report["controlled_execution_eligibility"] = build_controlled_execution_eligibility_summary(report)
    return report


def validate_governed_runtime_approval_gate_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in APPROVAL_GATE_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("approval_state")) not in {
        APPROVAL_APPROVED,
        APPROVAL_NEEDS_REVIEW,
        APPROVAL_BLOCKED,
    }:
        invalid_fields.append({"field": "approval_state", "reason": "invalid_state"})
    for field in (
        "unresolved_approval_actions",
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
        "required_fields": list(APPROVAL_GATE_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _approval_state(dry_run: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    state = _text(dry_run.get("dry_run_state"))
    issue_kinds = {
        _text(item.get("kind"))
        for item in validation.get("blocking_issues", [])
        if isinstance(item, dict)
    }
    hard_blockers = {
        "dry_run_report_missing",
        "dry_run_report_invalid",
        "dry_run_blocked",
        "missing_evidence_refs",
        "missing_seal_refs",
    }
    if issue_kinds.intersection(hard_blockers) or state == DRY_RUN_BLOCKED:
        return APPROVAL_BLOCKED
    if validation.get("unresolved_approval_actions") or state == DRY_RUN_NEEDS_REVIEW:
        return APPROVAL_NEEDS_REVIEW
    if state == DRY_RUN_COMPLETED:
        return APPROVAL_APPROVED
    return APPROVAL_NEEDS_REVIEW


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _approval_gate_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_dry_run_id": report.get("source_dry_run_id"),
        "approval_state": report.get("approval_state"),
        "execution_eligible": report.get("execution_eligible"),
        "approval_required": report.get("approval_required"),
        "unresolved_approval_actions": report.get("unresolved_approval_actions", []),
        "affected_repair_chain_ids": report.get("affected_repair_chain_ids", []),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-approval-gate-" + _stable_hash(payload)[:16]


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
