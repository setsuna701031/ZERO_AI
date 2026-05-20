from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report
from core.runtime.governed_runtime_action_gateway import build_governed_action_request_gateway_report
from core.runtime.governed_runtime_approval_gate import (
    APPROVAL_APPROVED,
    APPROVAL_BLOCKED,
    build_governed_runtime_approval_gate_report,
    validate_governed_runtime_approval_gate_report,
)
from core.runtime.governed_runtime_dry_run_executor import (
    DRY_RUN_COMPLETED,
    build_governed_runtime_dry_run_report,
    validate_governed_runtime_dry_run_report,
)
from core.runtime.governance_transition_readiness import build_governance_transition_readiness_report
from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report
from core.runtime.runtime_replay_snapshot_seal import (
    SEAL_VERSION,
    generate_replay_snapshot_seal_metadata,
)


SCHEMA_VERSION = "controlled_runtime_execution_contract.v1"

CONTRACT_READY = "contract_ready"
CONTRACT_NEEDS_REVIEW = "needs_review"
CONTRACT_BLOCKED = "blocked"

CONTROLLED_EXECUTION_CONTRACT_REQUIRED_FIELDS: tuple[str, ...] = (
    "execution_contract_id",
    "source_approval_gate_id",
    "execution_contract_state",
    "execution_eligible",
    "approval_valid",
    "dry_run_valid",
    "evidence_ready",
    "seal_ready",
    "rollback_ready",
    "landing_ready",
    "blocking_issues",
    "affected_repair_chain_ids",
    "reason_codes",
)


def controlled_runtime_execution_contract_required_fields() -> List[str]:
    return list(CONTROLLED_EXECUTION_CONTRACT_REQUIRED_FIELDS)


def validate_approval_gate_state(approval_gate_report: Any) -> Dict[str, Any]:
    gate = _mapping(approval_gate_report)
    validation = validate_governed_runtime_approval_gate_report(gate) if gate else {"ok": False}
    issues: List[Dict[str, Any]] = []
    if not gate:
        issues.append({"kind": "approval_gate_missing"})
    if not validation.get("ok"):
        issues.append(
            {
                "kind": "approval_gate_invalid",
                "missing_fields": copy.deepcopy(validation.get("missing_fields", [])),
                "invalid_fields": copy.deepcopy(validation.get("invalid_fields", [])),
            }
        )
    if _text(gate.get("approval_state")) == APPROVAL_BLOCKED:
        issues.append({"kind": "approval_gate_blocked"})
    if _text(gate.get("approval_state")) != APPROVAL_APPROVED:
        issues.append({"kind": "approval_not_approved"})
    if gate.get("execution_eligible") is not True:
        issues.append({"kind": "approval_execution_not_eligible"})
    return {
        "ok": bool(validation.get("ok")) and not issues,
        "approval_state": _text(gate.get("approval_state")),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _sorted_unique([*_string_list(gate.get("reason_codes")), *[item["kind"] for item in issues]]),
    }


def validate_dry_run_completion(dry_run_report: Any) -> Dict[str, Any]:
    dry_run = _mapping(dry_run_report)
    validation = validate_governed_runtime_dry_run_report(dry_run) if dry_run else {"ok": False}
    issues: List[Dict[str, Any]] = []
    if not dry_run:
        issues.append({"kind": "dry_run_missing"})
    if not validation.get("ok"):
        issues.append(
            {
                "kind": "dry_run_invalid",
                "missing_fields": copy.deepcopy(validation.get("missing_fields", [])),
                "invalid_fields": copy.deepcopy(validation.get("invalid_fields", [])),
            }
        )
    if _text(dry_run.get("dry_run_state")) != DRY_RUN_COMPLETED:
        issues.append({"kind": "dry_run_not_completed"})
    if dry_run.get("rejected_actions"):
        issues.append({"kind": "dry_run_has_rejected_actions"})
    if dry_run.get("approval_required_actions"):
        issues.append({"kind": "dry_run_has_unresolved_approval_actions"})
    return {
        "ok": bool(validation.get("ok")) and not issues,
        "dry_run_state": _text(dry_run.get("dry_run_state")),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _sorted_unique([*_string_list(dry_run.get("reason_codes")), *[item["kind"] for item in issues]]),
    }


def validate_execution_evidence_and_seal_refs(
    *,
    evidence_refs: Any,
    seal_refs: Any,
) -> Dict[str, Any]:
    evidence = _mapping(evidence_refs)
    seal = _mapping(seal_refs)
    issues: List[Dict[str, Any]] = []
    if not evidence:
        issues.append({"kind": "missing_evidence_refs"})
    if not _text(evidence.get("forensic_report_id")):
        issues.append({"kind": "missing_forensic_report_ref"})
    if not seal:
        issues.append({"kind": "missing_seal_refs"})
    if not _text(seal.get("snapshot_seal_id")):
        issues.append({"kind": "missing_snapshot_seal_id"})
    if _text(seal.get("seal_version")) and _text(seal.get("seal_version")) != SEAL_VERSION:
        issues.append({"kind": "unexpected_snapshot_seal_version"})
    return {
        "ok": not issues,
        "evidence_ready": bool(evidence) and not any(item["kind"].startswith("missing_forensic") for item in issues),
        "seal_ready": bool(seal) and not any("seal" in item["kind"] for item in issues),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _sorted_unique(item["kind"] for item in issues),
    }


def validate_rollback_evidence_readiness(landing_or_report: Any) -> Dict[str, Any]:
    landing = _normalize_landing(landing_or_report)
    issues: List[Dict[str, Any]] = []
    if not landing:
        issues.append({"kind": "landing_contract_missing"})
    if landing.get("blocking_issues"):
        issues.extend(copy.deepcopy(landing.get("blocking_issues", [])))
    checked = landing.get("checked_contracts", []) if isinstance(landing.get("checked_contracts"), list) else []
    missing_fields = landing.get("missing_fields", {}) if isinstance(landing.get("missing_fields"), dict) else {}
    for contract in checked:
        missing = missing_fields.get(contract, []) or []
        if "rollback_result" in missing:
            issues.append({"kind": "rollback_result_missing", "contract": contract})
        if "evidence_ref" in missing:
            issues.append({"kind": "evidence_ref_missing", "contract": contract})
    return {
        "ok": not issues,
        "rollback_ready": bool(landing) and not any(
            _text(item.get("kind")) in {"rollback_result_missing", "missing_required_fields"}
            and ("rollback_result" in item.get("fields", []) or _text(item.get("kind")) == "rollback_result_missing")
            for item in issues
            if isinstance(item, dict)
        ),
        "evidence_ready": bool(landing) and not any(
            _text(item.get("kind")) in {"evidence_ref_missing", "missing_required_fields"}
            and ("evidence_ref" in item.get("fields", []) or _text(item.get("kind")) == "evidence_ref_missing")
            for item in issues
            if isinstance(item, dict)
        ),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
        "landing_consistency": landing,
    }


def validate_execution_landing_contract_compatibility(landing_or_report: Any) -> Dict[str, Any]:
    landing = _normalize_landing(landing_or_report)
    issues = copy.deepcopy(landing.get("blocking_issues", [])) if landing else [{"kind": "landing_contract_missing"}]
    return {
        "ok": bool(landing) and not issues,
        "landing_ready": bool(landing) and not issues,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
        "landing_consistency": landing,
    }


def build_execution_eligibility_summary(contract_report: Any) -> Dict[str, Any]:
    report = _mapping(contract_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_contract_id": _text(report.get("execution_contract_id")),
        "source_approval_gate_id": _text(report.get("source_approval_gate_id")),
        "execution_contract_state": _text(report.get("execution_contract_state")),
        "execution_eligible": bool(report.get("execution_eligible")),
        "approval_valid": bool(report.get("approval_valid")),
        "dry_run_valid": bool(report.get("dry_run_valid")),
        "evidence_ready": bool(report.get("evidence_ready")),
        "seal_ready": bool(report.get("seal_ready")),
        "rollback_ready": bool(report.get("rollback_ready")),
        "landing_ready": bool(report.get("landing_ready")),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "affected_repair_chain_ids": copy.deepcopy(report.get("affected_repair_chain_ids", [])),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
        "execute": False,
        "planner_invoked": False,
        "task_enqueued": False,
    }


def build_controlled_runtime_execution_contract_report(
    *,
    approval_gate_report: Any | None = None,
    dry_run_report: Any | None = None,
    gateway_report: Any | None = None,
    readiness_report: Any | None = None,
    governance_closure_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    landing_consistency_report: Any | None = None,
) -> Dict[str, Any]:
    """Validate the contract required before controlled execution can be considered."""

    closure = _mapping(governance_closure_report)
    if not closure and forensic_report is not None:
        closure = build_runtime_governance_closure_report(
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            landing_consistency_report=landing_consistency_report,
        )
    readiness = _mapping(readiness_report)
    if not readiness and (closure or forensic_report is not None):
        readiness = build_governance_transition_readiness_report(
            governance_closure_report=closure if closure else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            landing_consistency_report=landing_consistency_report,
        )
    gateway = _mapping(gateway_report)
    if not gateway and (readiness or forensic_report is not None):
        gateway = build_governed_action_request_gateway_report(
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    dry_run = _mapping(dry_run_report)
    if not dry_run and (gateway or readiness or forensic_report is not None):
        dry_run = build_governed_runtime_dry_run_report(
            gateway_report=gateway if gateway else None,
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            governance_closure_report=closure if closure else None,
            landing_consistency_report=landing_consistency_report,
        )
    approval_gate = _mapping(approval_gate_report)
    if not approval_gate and (dry_run or gateway or readiness or forensic_report is not None):
        approval_gate = build_governed_runtime_approval_gate_report(
            dry_run_report=dry_run if dry_run else None,
            gateway_report=gateway if gateway else None,
            readiness_report=readiness if readiness else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            governance_closure_report=closure if closure else None,
        )
    evidence_refs = _mapping(approval_gate.get("evidence_refs") or dry_run.get("evidence_refs"))
    seal_refs = _mapping(approval_gate.get("seal_refs") or dry_run.get("seal_refs"))
    if snapshot_seal is not None and not seal_refs:
        seal_refs = generate_replay_snapshot_seal_metadata(snapshot_seal)
    landing = _normalize_landing(landing_consistency_report) or _landing_from_refs_or_empty()

    approval_validation = validate_approval_gate_state(approval_gate)
    dry_run_validation = validate_dry_run_completion(dry_run)
    ref_validation = validate_execution_evidence_and_seal_refs(
        evidence_refs=evidence_refs,
        seal_refs=seal_refs,
    )
    rollback_validation = validate_rollback_evidence_readiness(landing)
    landing_validation = validate_execution_landing_contract_compatibility(landing)
    blocking_issues = _dedupe_issues(
        [
            *approval_validation["blocking_issues"],
            *dry_run_validation["blocking_issues"],
            *ref_validation["blocking_issues"],
            *rollback_validation["blocking_issues"],
            *landing_validation["blocking_issues"],
        ]
    )
    state = _contract_state(
        approval_valid=approval_validation["ok"],
        dry_run_valid=dry_run_validation["ok"],
        evidence_ready=ref_validation["evidence_ready"] and rollback_validation["evidence_ready"],
        seal_ready=ref_validation["seal_ready"],
        rollback_ready=rollback_validation["rollback_ready"],
        landing_ready=landing_validation["landing_ready"],
        blocking_issues=blocking_issues,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "execution_contract_id": "",
        "source_approval_gate_id": _text(approval_gate.get("approval_gate_id")),
        "execution_contract_state": state,
        "execution_eligible": state == CONTRACT_READY,
        "approval_valid": approval_validation["ok"],
        "dry_run_valid": dry_run_validation["ok"],
        "evidence_ready": ref_validation["evidence_ready"] and rollback_validation["evidence_ready"],
        "seal_ready": ref_validation["seal_ready"],
        "rollback_ready": rollback_validation["rollback_ready"],
        "landing_ready": landing_validation["landing_ready"],
        "blocking_issues": blocking_issues,
        "affected_repair_chain_ids": _sorted_unique(
            [
                *_string_list(approval_gate.get("affected_repair_chain_ids")),
                *_string_list(dry_run.get("affected_repair_chain_ids")),
                *_string_list(evidence_refs.get("repair_chain_ids")),
                *_string_list(seal_refs.get("repair_chain_ids")),
            ]
        ),
        "reason_codes": _sorted_unique(
            [
                *approval_validation["reason_codes"],
                *dry_run_validation["reason_codes"],
                *ref_validation["reason_codes"],
                *rollback_validation["reason_codes"],
                *landing_validation["reason_codes"],
            ]
        ),
        "evidence_refs": evidence_refs,
        "seal_refs": seal_refs,
        "landing_consistency": landing,
    }
    report["execution_contract_id"] = _execution_contract_id(report)
    report["execution_eligibility"] = build_execution_eligibility_summary(report)
    return report


def validate_controlled_runtime_execution_contract_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in CONTROLLED_EXECUTION_CONTRACT_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("execution_contract_state")) not in {
        CONTRACT_READY,
        CONTRACT_NEEDS_REVIEW,
        CONTRACT_BLOCKED,
    }:
        invalid_fields.append({"field": "execution_contract_state", "reason": "invalid_state"})
    for field in ("blocking_issues", "affected_repair_chain_ids", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(CONTROLLED_EXECUTION_CONTRACT_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _contract_state(
    *,
    approval_valid: bool,
    dry_run_valid: bool,
    evidence_ready: bool,
    seal_ready: bool,
    rollback_ready: bool,
    landing_ready: bool,
    blocking_issues: Iterable[Mapping[str, Any]],
) -> str:
    if not all([approval_valid, dry_run_valid, evidence_ready, seal_ready, rollback_ready, landing_ready]):
        hard = {
            _text(issue.get("kind"))
            for issue in blocking_issues
            if isinstance(issue, dict)
        }
        if hard.intersection(
            {
                "approval_gate_blocked",
                "approval_gate_invalid",
                "dry_run_invalid",
                "dry_run_not_completed",
                "missing_evidence_refs",
                "missing_seal_refs",
                "missing_snapshot_seal_id",
                "missing_required_fields",
                "incompatible_field",
                "rollback_result_missing",
                "evidence_ref_missing",
            }
        ):
            return CONTRACT_BLOCKED
        return CONTRACT_NEEDS_REVIEW
    return CONTRACT_READY


def _normalize_landing(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _landing_from_refs_or_empty() -> Dict[str, Any]:
    return {}


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _execution_contract_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_approval_gate_id": report.get("source_approval_gate_id"),
        "execution_contract_state": report.get("execution_contract_state"),
        "execution_eligible": report.get("execution_eligible"),
        "approval_valid": report.get("approval_valid"),
        "dry_run_valid": report.get("dry_run_valid"),
        "evidence_ready": report.get("evidence_ready"),
        "seal_ready": report.get("seal_ready"),
        "rollback_ready": report.get("rollback_ready"),
        "landing_ready": report.get("landing_ready"),
        "blocking_issues": report.get("blocking_issues", []),
        "affected_repair_chain_ids": report.get("affected_repair_chain_ids", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "controlled-runtime-execution-contract-" + _stable_hash(payload)[:16]


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
