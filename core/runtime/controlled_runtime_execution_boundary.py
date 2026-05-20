from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.controlled_runtime_execution_contract import (
    CONTRACT_BLOCKED,
    CONTRACT_READY,
    build_controlled_runtime_execution_contract_report,
    validate_controlled_runtime_execution_contract_report,
)
from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report
from core.runtime.governed_runtime_action_gateway import (
    REQUEST_APPROVAL_REQUIRED_REPAIR,
    REQUEST_APPROVAL_REQUIRED_REPLAY,
    REQUEST_DRY_RUN_PLANNER_HANDOFF,
    REQUEST_DRY_RUN_REPAIR,
    REQUEST_DRY_RUN_REPLAY,
    REQUEST_NO_ACTION,
    build_governed_action_request_gateway_report,
)
from core.runtime.governed_runtime_approval_gate import build_governed_runtime_approval_gate_report
from core.runtime.governed_runtime_dry_run_executor import build_governed_runtime_dry_run_report
from core.runtime.governed_runtime_mutation_transaction import (
    validate_governed_runtime_mutation_transaction_lifecycle,
)
from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain
from core.runtime.runtime_recovery_reconstruction import validate_runtime_recovery_reconstruction
from core.runtime.runtime_governance_chain_seal import (
    GOVERNANCE_CHAIN_BLOCKED,
    GOVERNANCE_CHAIN_SEALABLE,
    GOVERNANCE_CHAIN_WARNING,
    build_runtime_governance_chain_seal_report,
    validate_runtime_governance_chain_seal_report,
)
from core.runtime.runtime_replay_snapshot_seal import SEAL_VERSION


SCHEMA_VERSION = "controlled_runtime_execution_boundary.v1"

BOUNDARY_READY = "boundary_ready"
BOUNDARY_NEEDS_REVIEW = "needs_review"
BOUNDARY_BLOCKED = "blocked"

CAPABILITY_GRANT_VALID = "grant_valid"
CAPABILITY_GRANT_MISSING = "grant_missing"
CAPABILITY_GRANT_EXPIRED = "grant_expired"
CAPABILITY_GRANT_INVALID_DELEGATION = "invalid_delegation"
CAPABILITY_GRANT_UNAUTHORIZED = "unauthorized"

APPROVAL_VALID = "approval_valid"
APPROVAL_MISSING = "approval_missing"
APPROVAL_EXPIRED = "approval_expired"
APPROVAL_MISMATCH = "approval_mismatch"
APPROVAL_FORGED = "approval_forged"

INTENT_READ_ONLY = "read_only"
INTENT_LOCAL_MUTATION = "local_mutation"
INTENT_GOVERNED_MUTATION = "governed_mutation"
INTENT_EXTERNAL_SIDE_EFFECT = "external_side_effect"
INTENT_PERSISTENCE_WRITE = "persistence_write"
INTENT_SCHEDULER_CONTROL = "scheduler_control"
INTENT_EXECUTOR_CONTROL = "executor_control"

EXECUTION_INTENTS: tuple[str, ...] = (
    INTENT_READ_ONLY,
    INTENT_LOCAL_MUTATION,
    INTENT_GOVERNED_MUTATION,
    INTENT_EXTERNAL_SIDE_EFFECT,
    INTENT_PERSISTENCE_WRITE,
    INTENT_SCHEDULER_CONTROL,
    INTENT_EXECUTOR_CONTROL,
)

ALLOWED_ACTION_TYPES: tuple[str, ...] = (
    REQUEST_NO_ACTION,
    REQUEST_DRY_RUN_REPAIR,
    REQUEST_DRY_RUN_REPLAY,
    REQUEST_DRY_RUN_PLANNER_HANDOFF,
    REQUEST_APPROVAL_REQUIRED_REPAIR,
    REQUEST_APPROVAL_REQUIRED_REPLAY,
)

FORBIDDEN_FLAGS: tuple[str, ...] = (
    "execute",
    "planner_invoked",
    "task_enqueued",
    "scheduler_mutated",
    "executor_mutated",
    "persistence_written",
    "ui_invoked",
)

BOUNDARY_REQUIRED_FIELDS: tuple[str, ...] = (
    "boundary_id",
    "source_execution_contract_id",
    "boundary_state",
    "allowed_action_types",
    "forbidden_flags_detected",
    "boundary_ready",
    "execution_allowed",
    "evidence_boundary_ready",
    "seal_boundary_ready",
    "rollback_boundary_ready",
    "blocking_issues",
    "reason_codes",
    "execution_intent",
    "governance_reason",
    "violated_constraints",
    "required_capabilities",
    "missing_capabilities",
    "unauthorized_capabilities",
    "delegation_chain_valid",
    "capability_grant_state",
    "approval_chain_valid",
    "approval_required",
    "approval_state",
    "approval_mismatch_reason",
    "approved_execution_scope",
    "transaction_state",
    "transition_valid",
    "rollback_state",
    "verification_state",
    "seal_state",
    "replay_consistency_state",
    "evidence_chain_valid",
    "evidence_integrity_state",
    "replay_evidence_consistent",
    "evidence_tamper_detected",
    "evidence_seal_valid",
    "reconstruction_state",
    "reconstruction_consistent",
    "replay_order_valid",
    "reconstruction_divergence_detected",
    "rollback_reconstruction_valid",
    "seal_reconstruction_valid",
    "governance_chain_sealable",
    "governance_chain_state",
    "seal_blockers",
    "seal_warnings",
)


def controlled_runtime_execution_boundary_required_fields() -> List[str]:
    return list(BOUNDARY_REQUIRED_FIELDS)


def controlled_runtime_allowed_action_types() -> List[str]:
    return list(ALLOWED_ACTION_TYPES)


def controlled_runtime_forbidden_flags() -> List[str]:
    return list(FORBIDDEN_FLAGS)


def controlled_runtime_execution_intents() -> List[str]:
    return list(EXECUTION_INTENTS)


def validate_controlled_execution_boundary_inputs(
    execution_contract_report: Any,
    *,
    action_requests: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    contract = _mapping(execution_contract_report)
    validation = validate_controlled_runtime_execution_contract_report(contract) if contract else {"ok": False}
    issues: List[Dict[str, Any]] = []
    if not contract:
        issues.append({"kind": "execution_contract_missing"})
    if not validation.get("ok"):
        issues.append(
            {
                "kind": "execution_contract_invalid",
                "missing_fields": copy.deepcopy(validation.get("missing_fields", [])),
                "invalid_fields": copy.deepcopy(validation.get("invalid_fields", [])),
            }
        )
    if _text(contract.get("execution_contract_state")) == CONTRACT_BLOCKED:
        issues.append({"kind": "execution_contract_blocked"})
    if _text(contract.get("execution_contract_state")) != CONTRACT_READY:
        issues.append({"kind": "execution_contract_not_ready"})
    if contract.get("execution_eligible") is not True:
        issues.append({"kind": "execution_contract_not_eligible"})
    action_validation = validate_allowed_action_request_types(action_requests or [])
    issues.extend(action_validation["blocking_issues"])
    return {
        "ok": bool(validation.get("ok")) and not issues,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def detect_forbidden_execution_side_effects(payloads: Iterable[Any]) -> List[Dict[str, Any]]:
    detected: List[Dict[str, Any]] = []
    for index, payload in enumerate(payloads or []):
        item = payload if isinstance(payload, dict) else {}
        request_id = _text(item.get("request_id"))
        for flag in FORBIDDEN_FLAGS:
            if item.get(flag) is True:
                detected.append(
                    {
                        "kind": "forbidden_flag_detected",
                        "flag": flag,
                        "index": index,
                        "request_id": request_id,
                    }
                )
    return _dedupe_issues(detected)


def classify_runtime_execution_intent(action_requests: Iterable[Any]) -> Dict[str, Any]:
    request_intents: List[Dict[str, Any]] = []
    inferred_intents: List[str] = []
    declared_intents: List[str] = []
    issues: List[Dict[str, Any]] = []

    for index, request in enumerate(action_requests or []):
        payload = request if isinstance(request, dict) else {}
        declared = _text(payload.get("execution_intent") or payload.get("intent"))
        inferred = _infer_request_intent(payload)
        if declared:
            if declared not in EXECUTION_INTENTS:
                issues.append(
                    {
                        "kind": "invalid_execution_intent",
                        "execution_intent": declared,
                        "index": index,
                        "request_id": _text(payload.get("request_id")),
                    }
                )
            else:
                declared_intents.append(declared)
        inferred_intents.append(inferred)
        request_intents.append(
            {
                "index": index,
                "request_id": _text(payload.get("request_id")),
                "request_type": _text(payload.get("request_type")),
                "declared_intent": declared,
                "inferred_intent": inferred,
            }
        )
        if declared == INTENT_READ_ONLY and inferred != INTENT_READ_ONLY:
            issues.append(
                {
                    "kind": "hidden_mutation_escalation",
                    "declared_intent": declared,
                    "inferred_intent": inferred,
                    "index": index,
                    "request_id": _text(payload.get("request_id")),
                }
            )

    execution_intent = _highest_intent([*declared_intents, *inferred_intents])
    return {
        "execution_intent": execution_intent,
        "request_intents": request_intents,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def build_execution_intent_governance(
    *,
    execution_intent: str,
    action_requests: Iterable[Any],
    blocking_issues: Iterable[Any],
    forbidden_flags: Iterable[Any],
) -> Dict[str, Any]:
    issues = [item for item in blocking_issues or [] if isinstance(item, dict)]
    forbidden = [item for item in forbidden_flags or [] if isinstance(item, dict)]
    requests = [item for item in action_requests or [] if isinstance(item, dict)]

    violated_constraints: List[str] = []
    governance_reason: List[str] = []
    for issue in [*issues, *forbidden]:
        kind = _text(issue.get("kind"))
        flag = _text(issue.get("flag"))
        if kind:
            governance_reason.append(kind)
        if kind == "hidden_mutation_escalation":
            violated_constraints.append("hidden_mutation_escalation")
        if kind == "action_type_not_allowed":
            violated_constraints.append("allowed_action_types")
        if kind == "forbidden_flag_detected":
            if flag in {"execute", "executor_mutated"}:
                violated_constraints.append("executor_ownership_boundary")
            elif flag in {"planner_invoked", "task_enqueued", "scheduler_mutated"}:
                violated_constraints.append("scheduler_control_boundary")
            elif flag == "persistence_written":
                violated_constraints.append("persistence_ownership_boundary")
            else:
                violated_constraints.append("runtime_side_effect_boundary")
    if execution_intent in {INTENT_LOCAL_MUTATION, INTENT_GOVERNED_MUTATION}:
        governance_reason.append("mutation_intent_requires_governance")
    if execution_intent == INTENT_EXTERNAL_SIDE_EFFECT:
        governance_reason.append("external_side_effect_requires_review")
    if execution_intent == INTENT_PERSISTENCE_WRITE:
        governance_reason.append("persistence_write_requires_runtime_persistence_service")
        violated_constraints.append("persistence_ownership_boundary")
    if execution_intent == INTENT_SCHEDULER_CONTROL:
        governance_reason.append("scheduler_control_requires_scheduler_owner")
        violated_constraints.append("scheduler_control_boundary")
    if execution_intent == INTENT_EXECUTOR_CONTROL:
        governance_reason.append("executor_control_requires_executor_owner")
        violated_constraints.append("executor_ownership_boundary")
    if any(_text(request.get("request_type")) in {REQUEST_APPROVAL_REQUIRED_REPAIR, REQUEST_APPROVAL_REQUIRED_REPLAY} for request in requests):
        governance_reason.append("approval_required_action_present")

    return {
        "governance_reason": _sorted_unique(governance_reason),
        "violated_constraints": _sorted_unique(violated_constraints),
        "required_capabilities": _required_capabilities_for_intent(execution_intent),
    }


def validate_runtime_capability_grant_contract(
    capability_grant_contract: Any,
    *,
    required_capabilities: Iterable[Any],
    action_requests: Iterable[Any] | None = None,
    now: datetime | None = None,
) -> Dict[str, Any]:
    grant = _mapping(capability_grant_contract)
    required = _sorted_unique(required_capabilities)
    granted = _sorted_unique(grant.get("granted_capabilities"))
    requested = _sorted_unique(
        capability
        for request in (action_requests or [])
        if isinstance(request, dict)
        for capability in _string_list(request.get("requested_capabilities") or request.get("capabilities"))
    )
    missing = [capability for capability in required if capability not in granted]
    unauthorized = [capability for capability in requested if capability not in granted]
    issues: List[Dict[str, Any]] = []

    if required and not grant:
        issues.append({"kind": "capability_grant_missing"})
    for field in ("grant_source", "grant_scope", "grant_expiration"):
        if grant and not _text(grant.get(field)):
            issues.append({"kind": "capability_grant_field_missing", "field": field})
    if grant and not isinstance(grant.get("granted_capabilities"), list):
        issues.append({"kind": "capability_grant_field_invalid", "field": "granted_capabilities"})
    if grant and not isinstance(grant.get("delegation_allowed"), bool):
        issues.append({"kind": "capability_grant_field_invalid", "field": "delegation_allowed"})
    for capability in missing:
        issues.append({"kind": "missing_capability", "capability": capability})
    for capability in unauthorized:
        issues.append({"kind": "unauthorized_capability", "capability": capability})

    expiration_ok = True
    if grant:
        expiration_ok = _grant_expiration_valid(_text(grant.get("grant_expiration")), now=now)
        if not expiration_ok:
            issues.append({"kind": "capability_grant_expired", "grant_expiration": _text(grant.get("grant_expiration"))})

    delegation = _validate_delegation_chain(grant)
    issues.extend(delegation["blocking_issues"])

    state = CAPABILITY_GRANT_VALID
    if any(item.get("kind") == "capability_grant_expired" for item in issues):
        state = CAPABILITY_GRANT_EXPIRED
    elif not delegation["delegation_chain_valid"]:
        state = CAPABILITY_GRANT_INVALID_DELEGATION
    elif missing or unauthorized or any(item.get("kind") in {"capability_grant_missing", "capability_grant_field_missing", "capability_grant_field_invalid"} for item in issues):
        state = CAPABILITY_GRANT_UNAUTHORIZED if grant else CAPABILITY_GRANT_MISSING

    return {
        "ok": state == CAPABILITY_GRANT_VALID,
        "capability_grant_state": state,
        "granted_capabilities": granted,
        "missing_capabilities": missing,
        "unauthorized_capabilities": unauthorized,
        "delegation_chain_valid": delegation["delegation_chain_valid"],
        "grant_source": _text(grant.get("grant_source")),
        "grant_scope": _text(grant.get("grant_scope")),
        "grant_expiration": _text(grant.get("grant_expiration")),
        "delegation_allowed": bool(grant.get("delegation_allowed")) if isinstance(grant.get("delegation_allowed"), bool) else False,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def build_runtime_approval_signature(approval_contract: Any) -> str:
    approval = _mapping(approval_contract)
    payload = {
        "approval_id": _text(approval.get("approval_id")),
        "approval_source": _text(approval.get("approval_source")),
        "approval_scope": _text(approval.get("approval_scope")),
        "approved_intents": _sorted_unique(approval.get("approved_intents")),
        "approved_capabilities": _sorted_unique(approval.get("approved_capabilities")),
        "approval_timestamp": _text(approval.get("approval_timestamp")),
        "approval_expiration": _text(approval.get("approval_expiration")),
        "review_required": bool(approval.get("review_required")),
    }
    return "runtime-approval-" + _stable_hash(payload)[:24]


def validate_runtime_approval_chain_contract(
    approval_chain_contract: Any,
    *,
    execution_intent: str,
    required_capabilities: Iterable[Any],
    grant_scope: str = "",
    now: datetime | None = None,
) -> Dict[str, Any]:
    approval = _mapping(approval_chain_contract)
    required = _sorted_unique(required_capabilities)
    approval_required = _approval_required_for_intent(execution_intent)
    approved_intents = _sorted_unique(approval.get("approved_intents"))
    approved_capabilities = _sorted_unique(approval.get("approved_capabilities"))
    mismatch_reasons: List[str] = []
    issues: List[Dict[str, Any]] = []

    if approval_required and not approval:
        issues.append({"kind": "approval_chain_missing"})
    if approval:
        for field in (
            "approval_id",
            "approval_source",
            "approval_scope",
            "approval_timestamp",
            "approval_expiration",
            "approval_signature",
        ):
            if not _text(approval.get(field)):
                issues.append({"kind": "approval_metadata_missing", "field": field})
        for field in ("approved_intents", "approved_capabilities"):
            if not isinstance(approval.get(field), list):
                issues.append({"kind": "approval_metadata_invalid", "field": field})
        if not isinstance(approval.get("review_required"), bool):
            issues.append({"kind": "approval_metadata_invalid", "field": "review_required"})

        if execution_intent not in approved_intents:
            mismatch_reasons.append("intent_not_approved")
            issues.append({"kind": "approval_intent_mismatch", "execution_intent": execution_intent})
        missing_approved_capabilities = [capability for capability in required if capability not in approved_capabilities]
        for capability in missing_approved_capabilities:
            mismatch_reasons.append("capability_not_approved")
            issues.append({"kind": "approval_capability_mismatch", "capability": capability})
        if grant_scope and _text(approval.get("approval_scope")) != grant_scope:
            mismatch_reasons.append("scope_mismatch")
            issues.append(
                {
                    "kind": "approval_scope_mismatch",
                    "approval_scope": _text(approval.get("approval_scope")),
                    "required_scope": grant_scope,
                }
            )
        if not _grant_expiration_valid(_text(approval.get("approval_expiration")), now=now):
            issues.append({"kind": "approval_expired", "approval_expiration": _text(approval.get("approval_expiration"))})
        if _text(approval.get("approval_signature")) != build_runtime_approval_signature(approval):
            issues.append({"kind": "approval_signature_invalid"})

    state = APPROVAL_VALID
    if approval_required and not approval:
        state = APPROVAL_MISSING
    elif any(item.get("kind") == "approval_expired" for item in issues):
        state = APPROVAL_EXPIRED
    elif any(item.get("kind") in {"approval_signature_invalid", "approval_metadata_missing", "approval_metadata_invalid"} for item in issues):
        state = APPROVAL_FORGED
    elif mismatch_reasons:
        state = APPROVAL_MISMATCH

    return {
        "ok": state == APPROVAL_VALID,
        "approval_chain_valid": state == APPROVAL_VALID,
        "approval_required": approval_required,
        "approval_state": state,
        "approval_mismatch_reason": _sorted_unique(mismatch_reasons),
        "approved_execution_scope": _text(approval.get("approval_scope")),
        "approved_intents": approved_intents,
        "approved_capabilities": approved_capabilities,
        "approval_id": _text(approval.get("approval_id")),
        "approval_source": _text(approval.get("approval_source")),
        "review_required": bool(approval.get("review_required")) if isinstance(approval.get("review_required"), bool) else False,
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def detect_forbidden_runtime_coupling(payloads: Iterable[Any]) -> List[Dict[str, Any]]:
    coupling_flags = {
        "planner_invoked",
        "task_enqueued",
        "scheduler_mutated",
        "executor_mutated",
        "persistence_written",
        "ui_invoked",
    }
    return [
        copy.deepcopy(item)
        for item in detect_forbidden_execution_side_effects(payloads)
        if item.get("flag") in coupling_flags
    ]


def validate_allowed_action_request_types(action_requests: Iterable[Any]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    for index, request in enumerate(action_requests or []):
        payload = request if isinstance(request, dict) else {}
        request_type = _text(payload.get("request_type"))
        if request_type not in ALLOWED_ACTION_TYPES:
            issues.append(
                {
                    "kind": "action_type_not_allowed",
                    "request_type": request_type,
                    "index": index,
                    "request_id": _text(payload.get("request_id")),
                }
            )
    return {
        "ok": not issues,
        "allowed_action_types": list(ALLOWED_ACTION_TYPES),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def validate_boundary_evidence_seal_rollback_readiness(
    execution_contract_report: Any,
    *,
    landing_consistency_report: Any | None = None,
) -> Dict[str, Any]:
    contract = _mapping(execution_contract_report)
    evidence = _mapping(contract.get("evidence_refs"))
    seal = _mapping(contract.get("seal_refs"))
    landing = _normalize_landing(landing_consistency_report) or _mapping(contract.get("landing_consistency"))
    issues: List[Dict[str, Any]] = []
    if contract.get("evidence_ready") is not True or not evidence:
        issues.append({"kind": "evidence_boundary_not_ready"})
    if not _text(evidence.get("forensic_report_id")):
        issues.append({"kind": "missing_forensic_report_ref"})
    if contract.get("seal_ready") is not True or not seal:
        issues.append({"kind": "seal_boundary_not_ready"})
    if not _text(seal.get("snapshot_seal_id")):
        issues.append({"kind": "missing_snapshot_seal_id"})
    if _text(seal.get("seal_version")) and _text(seal.get("seal_version")) != SEAL_VERSION:
        issues.append({"kind": "unexpected_snapshot_seal_version"})
    if contract.get("rollback_ready") is not True:
        issues.append({"kind": "rollback_boundary_not_ready"})
    if landing and landing.get("blocking_issues"):
        issues.extend(copy.deepcopy(landing.get("blocking_issues", [])))
    return {
        "ok": not issues,
        "evidence_boundary_ready": bool(evidence) and not any("evidence" in item["kind"] or "forensic" in item["kind"] for item in issues),
        "seal_boundary_ready": bool(seal) and not any("seal" in item["kind"] for item in issues),
        "rollback_boundary_ready": contract.get("rollback_ready") is True
        and not any("rollback" in item["kind"] for item in issues),
        "blocking_issues": _dedupe_issues(issues),
        "reason_codes": _reason_codes_from_issues(issues),
    }


def build_controlled_execution_boundary_summary(boundary_report: Any) -> Dict[str, Any]:
    report = _mapping(boundary_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "boundary_id": _text(report.get("boundary_id")),
        "source_execution_contract_id": _text(report.get("source_execution_contract_id")),
        "boundary_state": _text(report.get("boundary_state")),
        "boundary_ready": bool(report.get("boundary_ready")),
        "execution_allowed": bool(report.get("execution_allowed")),
        "execution_intent": _text(report.get("execution_intent")),
        "governance_reason": copy.deepcopy(report.get("governance_reason", [])),
        "violated_constraints": copy.deepcopy(report.get("violated_constraints", [])),
        "required_capabilities": copy.deepcopy(report.get("required_capabilities", [])),
        "missing_capabilities": copy.deepcopy(report.get("missing_capabilities", [])),
        "unauthorized_capabilities": copy.deepcopy(report.get("unauthorized_capabilities", [])),
        "delegation_chain_valid": bool(report.get("delegation_chain_valid")),
        "capability_grant_state": _text(report.get("capability_grant_state")),
        "approval_chain_valid": bool(report.get("approval_chain_valid")),
        "approval_required": bool(report.get("approval_required")),
        "approval_state": _text(report.get("approval_state")),
        "approval_mismatch_reason": copy.deepcopy(report.get("approval_mismatch_reason", [])),
        "approved_execution_scope": _text(report.get("approved_execution_scope")),
        "transaction_state": _text(report.get("transaction_state")),
        "transition_valid": bool(report.get("transition_valid")),
        "rollback_state": _text(report.get("rollback_state")),
        "verification_state": _text(report.get("verification_state")),
        "seal_state": _text(report.get("seal_state")),
        "replay_consistency_state": _text(report.get("replay_consistency_state")),
        "evidence_chain_valid": bool(report.get("evidence_chain_valid")),
        "evidence_integrity_state": _text(report.get("evidence_integrity_state")),
        "replay_evidence_consistent": bool(report.get("replay_evidence_consistent")),
        "evidence_tamper_detected": bool(report.get("evidence_tamper_detected")),
        "evidence_seal_valid": bool(report.get("evidence_seal_valid")),
        "reconstruction_state": _text(report.get("reconstruction_state")),
        "reconstruction_consistent": bool(report.get("reconstruction_consistent")),
        "replay_order_valid": bool(report.get("replay_order_valid")),
        "reconstruction_divergence_detected": bool(report.get("reconstruction_divergence_detected")),
        "rollback_reconstruction_valid": bool(report.get("rollback_reconstruction_valid")),
        "seal_reconstruction_valid": bool(report.get("seal_reconstruction_valid")),
        "forbidden_flag_count": len(report.get("forbidden_flags_detected", []) or []),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "allowed_action_types": copy.deepcopy(report.get("allowed_action_types", [])),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
        "execute": False,
        "planner_invoked": False,
        "task_enqueued": False,
    }


def build_controlled_runtime_execution_boundary_report(
    *,
    execution_contract_report: Any | None = None,
    action_requests: Iterable[Any] | None = None,
    approval_gate_report: Any | None = None,
    dry_run_report: Any | None = None,
    gateway_report: Any | None = None,
    readiness_report: Any | None = None,
    forensic_report: Any | None = None,
    snapshot_seal: Any | None = None,
    landing_consistency_report: Any | None = None,
    capability_grant_contract: Any | None = None,
    approval_chain_contract: Any | None = None,
    mutation_transaction_contract: Any | None = None,
    previous_transaction_state: str | None = None,
    transaction_verification_report: Any | None = None,
    transaction_rollback_report: Any | None = None,
    transaction_seal_report: Any | None = None,
    transaction_replay_report: Any | None = None,
    evidence_chain_records: Iterable[Any] | None = None,
    replay_evidence: Any | None = None,
    seal_evidence: Any | None = None,
    reconstruction_contract: Any | None = None,
    reconstruction_expected_evidence_chain: Iterable[Any] | None = None,
    rollback_reconstruction: Any | None = None,
    seal_reconstruction: Any | None = None,
    governance_chain_seal_report: Any | None = None,
) -> Dict[str, Any]:
    """Validate controlled execution boundaries as data only."""

    gateway = _mapping(gateway_report)
    if not gateway and (readiness_report is not None or forensic_report is not None):
        gateway = build_governed_action_request_gateway_report(
            readiness_report=readiness_report,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    requests = [
        copy.deepcopy(item)
        for item in (list(action_requests) if action_requests is not None else gateway.get("action_requests", []))
        if isinstance(item, dict)
    ]
    dry_run = _mapping(dry_run_report)
    if not dry_run and (gateway or requests):
        dry_run = build_governed_runtime_dry_run_report(
            gateway_report=gateway if gateway else None,
            action_requests=requests if requests else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            landing_consistency_report=landing_consistency_report,
        )
    approval_gate = _mapping(approval_gate_report)
    if not approval_gate and (dry_run or gateway or forensic_report is not None):
        approval_gate = build_governed_runtime_approval_gate_report(
            dry_run_report=dry_run if dry_run else None,
            gateway_report=gateway if gateway else None,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
        )
    contract = _mapping(execution_contract_report)
    if not contract and (approval_gate or dry_run or gateway or forensic_report is not None):
        contract = build_controlled_runtime_execution_contract_report(
            approval_gate_report=approval_gate if approval_gate else None,
            dry_run_report=dry_run if dry_run else None,
            gateway_report=gateway if gateway else None,
            readiness_report=readiness_report,
            forensic_report=forensic_report,
            snapshot_seal=snapshot_seal,
            landing_consistency_report=landing_consistency_report,
        )
    input_validation = validate_controlled_execution_boundary_inputs(
        contract,
        action_requests=requests,
    )
    intent = classify_runtime_execution_intent(requests)
    forbidden = detect_forbidden_execution_side_effects([*requests, contract])
    boundary_refs = validate_boundary_evidence_seal_rollback_readiness(
        contract,
        landing_consistency_report=landing_consistency_report,
    )
    blocking_issues = _dedupe_issues(
        [
            *input_validation["blocking_issues"],
            *intent["blocking_issues"],
            *forbidden,
            *boundary_refs["blocking_issues"],
        ]
    )
    intent_governance = build_execution_intent_governance(
        execution_intent=intent["execution_intent"],
        action_requests=requests,
        blocking_issues=blocking_issues,
        forbidden_flags=forbidden,
    )
    capability_grant = validate_runtime_capability_grant_contract(
        capability_grant_contract,
        required_capabilities=intent_governance["required_capabilities"],
        action_requests=requests,
    )
    approval_chain = validate_runtime_approval_chain_contract(
        approval_chain_contract,
        execution_intent=intent["execution_intent"],
        required_capabilities=intent_governance["required_capabilities"],
        grant_scope=capability_grant["grant_scope"],
    )
    transaction = _transaction_validation_for_boundary(
        mutation_transaction_contract=mutation_transaction_contract,
        previous_transaction_state=previous_transaction_state,
        verification_report=transaction_verification_report,
        rollback_report=transaction_rollback_report,
        seal_report=transaction_seal_report,
        replay_report=transaction_replay_report,
    )
    evidence = _evidence_validation_for_boundary(
        evidence_chain_records=evidence_chain_records,
        transaction_id=transaction["transaction_id"],
        replay_evidence=replay_evidence,
        seal_evidence=seal_evidence,
    )
    reconstruction = _reconstruction_validation_for_boundary(
        reconstruction_contract=reconstruction_contract,
        transaction_contract=mutation_transaction_contract,
        expected_evidence_chain=reconstruction_expected_evidence_chain,
        rollback_reconstruction=rollback_reconstruction,
        seal_reconstruction=seal_reconstruction,
    )
    blocking_issues = _dedupe_issues(
        [
            *blocking_issues,
            *capability_grant["blocking_issues"],
            *approval_chain["blocking_issues"],
            *transaction["blocking_issues"],
            *evidence["blocking_issues"],
            *reconstruction["blocking_issues"],
        ]
    )
    intent_governance = build_execution_intent_governance(
        execution_intent=intent["execution_intent"],
        action_requests=requests,
        blocking_issues=blocking_issues,
        forbidden_flags=forbidden,
    )
    state = _boundary_state(
        contract=contract,
        forbidden_flags=forbidden,
        boundary_refs=boundary_refs,
        blocking_issues=blocking_issues,
        violated_constraints=intent_governance["violated_constraints"],
        capability_grant_state=capability_grant["capability_grant_state"],
        approval_state=approval_chain["approval_state"],
        transaction_ok=transaction["ok"],
        evidence_ok=evidence["ok"],
        reconstruction_ok=reconstruction["ok"],
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "boundary_id": "",
        "source_execution_contract_id": _text(contract.get("execution_contract_id")),
        "boundary_state": state,
        "allowed_action_types": list(ALLOWED_ACTION_TYPES),
        "forbidden_flags_detected": forbidden,
        "boundary_ready": state == BOUNDARY_READY,
        "execution_allowed": state == BOUNDARY_READY,
        "evidence_boundary_ready": boundary_refs["evidence_boundary_ready"],
        "seal_boundary_ready": boundary_refs["seal_boundary_ready"],
        "rollback_boundary_ready": boundary_refs["rollback_boundary_ready"],
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                *_string_list(contract.get("reason_codes")),
                *input_validation["reason_codes"],
                *intent["reason_codes"],
                *capability_grant["reason_codes"],
                *approval_chain["reason_codes"],
                *transaction["reason_codes"],
                *evidence["reason_codes"],
                *reconstruction["reason_codes"],
                *boundary_refs["reason_codes"],
                *_reason_codes_from_issues(forbidden),
                *_reason_codes_from_issues(blocking_issues),
            ]
        ),
        "execution_intent": intent["execution_intent"],
        "execution_intent_details": copy.deepcopy(intent["request_intents"]),
        "governance_reason": intent_governance["governance_reason"],
        "violated_constraints": intent_governance["violated_constraints"],
        "required_capabilities": intent_governance["required_capabilities"],
        "capability_grant": capability_grant,
        "missing_capabilities": capability_grant["missing_capabilities"],
        "unauthorized_capabilities": capability_grant["unauthorized_capabilities"],
        "delegation_chain_valid": capability_grant["delegation_chain_valid"],
        "capability_grant_state": capability_grant["capability_grant_state"],
        "approval_chain": approval_chain,
        "approval_chain_valid": approval_chain["approval_chain_valid"],
        "approval_required": approval_chain["approval_required"],
        "approval_state": approval_chain["approval_state"],
        "approval_mismatch_reason": approval_chain["approval_mismatch_reason"],
        "approved_execution_scope": approval_chain["approved_execution_scope"],
        "mutation_transaction": transaction,
        "transaction_state": transaction["transaction_state"],
        "transition_valid": transaction["transition_valid"],
        "rollback_state": transaction["rollback_state"],
        "verification_state": transaction["verification_state"],
        "seal_state": transaction["seal_state"],
        "replay_consistency_state": transaction["replay_consistency_state"],
        "runtime_evidence_chain": evidence,
        "evidence_chain_valid": evidence["evidence_chain_valid"],
        "evidence_integrity_state": evidence["evidence_integrity_state"],
        "replay_evidence_consistent": evidence["replay_evidence_consistent"],
        "evidence_tamper_detected": evidence["evidence_tamper_detected"],
        "evidence_seal_valid": evidence["evidence_seal_valid"],
        "runtime_recovery_reconstruction": reconstruction,
        "reconstruction_state": reconstruction["reconstruction_state"],
        "reconstruction_consistent": reconstruction["reconstruction_consistent"],
        "replay_order_valid": reconstruction["replay_order_valid"],
        "reconstruction_divergence_detected": reconstruction["reconstruction_divergence_detected"],
        "rollback_reconstruction_valid": reconstruction["rollback_reconstruction_valid"],
        "seal_reconstruction_valid": reconstruction["seal_reconstruction_valid"],
    }
    report["boundary_id"] = _boundary_id(report)
    supplied_seal = _mapping(governance_chain_seal_report)
    governance_chain_seal = supplied_seal if supplied_seal else build_runtime_governance_chain_seal_report(boundary_report=report)
    report["runtime_governance_chain_seal"] = governance_chain_seal
    report["governance_chain_sealable"] = governance_chain_seal.get("governance_chain_sealable") is True
    report["governance_chain_state"] = _text(governance_chain_seal.get("governance_chain_state"))
    report["seal_blockers"] = [copy.deepcopy(item) for item in governance_chain_seal.get("seal_blockers", []) if isinstance(item, dict)]
    report["seal_warnings"] = [copy.deepcopy(item) for item in governance_chain_seal.get("seal_warnings", []) if isinstance(item, dict)]
    report["boundary_id"] = _boundary_id(report)
    if isinstance(report["runtime_governance_chain_seal"], dict):
        report["runtime_governance_chain_seal"]["source_boundary_id"] = report["boundary_id"]
    report["boundary_summary"] = build_controlled_execution_boundary_summary(report)
    return report


def validate_controlled_runtime_execution_boundary_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in BOUNDARY_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []
    if _text(payload.get("boundary_state")) not in {
        BOUNDARY_READY,
        BOUNDARY_NEEDS_REVIEW,
        BOUNDARY_BLOCKED,
    }:
        invalid_fields.append({"field": "boundary_state", "reason": "invalid_state"})
    if _text(payload.get("execution_intent")) not in EXECUTION_INTENTS:
        invalid_fields.append({"field": "execution_intent", "reason": "invalid_intent"})
    for field in (
        "allowed_action_types",
        "forbidden_flags_detected",
        "blocking_issues",
        "reason_codes",
        "governance_reason",
        "violated_constraints",
        "required_capabilities",
        "missing_capabilities",
        "unauthorized_capabilities",
        "approval_mismatch_reason",
        "seal_blockers",
        "seal_warnings",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})
    if "delegation_chain_valid" in payload and not isinstance(payload.get("delegation_chain_valid"), bool):
        invalid_fields.append({"field": "delegation_chain_valid", "reason": "expected_bool"})
    if _text(payload.get("capability_grant_state")) not in {
        CAPABILITY_GRANT_VALID,
        CAPABILITY_GRANT_MISSING,
        CAPABILITY_GRANT_EXPIRED,
        CAPABILITY_GRANT_INVALID_DELEGATION,
        CAPABILITY_GRANT_UNAUTHORIZED,
    }:
        invalid_fields.append({"field": "capability_grant_state", "reason": "invalid_state"})
    if "approval_chain_valid" in payload and not isinstance(payload.get("approval_chain_valid"), bool):
        invalid_fields.append({"field": "approval_chain_valid", "reason": "expected_bool"})
    if "approval_required" in payload and not isinstance(payload.get("approval_required"), bool):
        invalid_fields.append({"field": "approval_required", "reason": "expected_bool"})
    if _text(payload.get("approval_state")) not in {
        APPROVAL_VALID,
        APPROVAL_MISSING,
        APPROVAL_EXPIRED,
        APPROVAL_MISMATCH,
        APPROVAL_FORGED,
    }:
        invalid_fields.append({"field": "approval_state", "reason": "invalid_state"})
    if "transition_valid" in payload and not isinstance(payload.get("transition_valid"), bool):
        invalid_fields.append({"field": "transition_valid", "reason": "expected_bool"})
    for field in ("evidence_chain_valid", "replay_evidence_consistent", "evidence_tamper_detected", "evidence_seal_valid"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})
    for field in (
        "reconstruction_consistent",
        "replay_order_valid",
        "reconstruction_divergence_detected",
        "rollback_reconstruction_valid",
        "seal_reconstruction_valid",
        "governance_chain_sealable",
    ):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})
    if "governance_chain_state" in payload and _text(payload.get("governance_chain_state")) not in {
        GOVERNANCE_CHAIN_SEALABLE,
        GOVERNANCE_CHAIN_BLOCKED,
        GOVERNANCE_CHAIN_WARNING,
    }:
        invalid_fields.append({"field": "governance_chain_state", "reason": "invalid_state"})
    if "runtime_governance_chain_seal" in payload:
        seal_validation = validate_runtime_governance_chain_seal_report(payload.get("runtime_governance_chain_seal"))
        if not seal_validation.get("ok"):
            invalid_fields.append(
                {
                    "field": "runtime_governance_chain_seal",
                    "reason": "invalid_contract",
                    "missing_fields": copy.deepcopy(seal_validation.get("missing_fields", [])),
                    "invalid_fields": copy.deepcopy(seal_validation.get("invalid_fields", [])),
                }
            )
    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(BOUNDARY_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def _boundary_state(
    *,
    contract: Mapping[str, Any],
    forbidden_flags: Iterable[Any],
    boundary_refs: Mapping[str, Any],
    blocking_issues: Iterable[Mapping[str, Any]],
    violated_constraints: Iterable[Any] | None = None,
    capability_grant_state: str = CAPABILITY_GRANT_VALID,
    approval_state: str = APPROVAL_VALID,
    transaction_ok: bool = True,
    evidence_ok: bool = True,
    reconstruction_ok: bool = True,
) -> str:
    constraints = set(_string_list(violated_constraints or []))
    if forbidden_flags:
        return BOUNDARY_BLOCKED
    if constraints.intersection(
        {
            "executor_ownership_boundary",
            "scheduler_control_boundary",
            "persistence_ownership_boundary",
            "hidden_mutation_escalation",
        }
    ):
        return BOUNDARY_BLOCKED
    if _text(capability_grant_state) != CAPABILITY_GRANT_VALID:
        return BOUNDARY_BLOCKED
    if _text(approval_state) != APPROVAL_VALID:
        return BOUNDARY_BLOCKED
    if transaction_ok is not True:
        return BOUNDARY_BLOCKED
    if evidence_ok is not True:
        return BOUNDARY_BLOCKED
    if reconstruction_ok is not True:
        return BOUNDARY_BLOCKED
    if _text(contract.get("execution_contract_state")) == CONTRACT_BLOCKED:
        return BOUNDARY_BLOCKED
    if contract.get("execution_eligible") is not True:
        return BOUNDARY_NEEDS_REVIEW
    if not boundary_refs.get("ok"):
        return BOUNDARY_BLOCKED
    if list(blocking_issues):
        return BOUNDARY_BLOCKED
    return BOUNDARY_READY


def _normalize_landing(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    if payload.get("schema_version") == "execution_landing_consistency.v1":
        return payload
    return build_execution_landing_consistency_report(payload)


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _boundary_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_execution_contract_id": report.get("source_execution_contract_id"),
        "boundary_state": report.get("boundary_state"),
        "execution_intent": report.get("execution_intent"),
        "allowed_action_types": report.get("allowed_action_types", []),
        "forbidden_flags_detected": report.get("forbidden_flags_detected", []),
        "boundary_ready": report.get("boundary_ready"),
        "execution_allowed": report.get("execution_allowed"),
        "evidence_boundary_ready": report.get("evidence_boundary_ready"),
        "seal_boundary_ready": report.get("seal_boundary_ready"),
        "rollback_boundary_ready": report.get("rollback_boundary_ready"),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
        "governance_reason": report.get("governance_reason", []),
        "violated_constraints": report.get("violated_constraints", []),
        "required_capabilities": report.get("required_capabilities", []),
        "missing_capabilities": report.get("missing_capabilities", []),
        "unauthorized_capabilities": report.get("unauthorized_capabilities", []),
        "delegation_chain_valid": report.get("delegation_chain_valid"),
        "capability_grant_state": report.get("capability_grant_state"),
        "approval_chain_valid": report.get("approval_chain_valid"),
        "approval_required": report.get("approval_required"),
        "approval_state": report.get("approval_state"),
        "approval_mismatch_reason": report.get("approval_mismatch_reason", []),
        "approved_execution_scope": report.get("approved_execution_scope"),
        "transaction_state": report.get("transaction_state"),
        "transition_valid": report.get("transition_valid"),
        "rollback_state": report.get("rollback_state"),
        "verification_state": report.get("verification_state"),
        "seal_state": report.get("seal_state"),
        "replay_consistency_state": report.get("replay_consistency_state"),
        "evidence_chain_valid": report.get("evidence_chain_valid"),
        "evidence_integrity_state": report.get("evidence_integrity_state"),
        "replay_evidence_consistent": report.get("replay_evidence_consistent"),
        "evidence_tamper_detected": report.get("evidence_tamper_detected"),
        "evidence_seal_valid": report.get("evidence_seal_valid"),
        "reconstruction_state": report.get("reconstruction_state"),
        "reconstruction_consistent": report.get("reconstruction_consistent"),
        "replay_order_valid": report.get("replay_order_valid"),
        "reconstruction_divergence_detected": report.get("reconstruction_divergence_detected"),
        "rollback_reconstruction_valid": report.get("rollback_reconstruction_valid"),
        "seal_reconstruction_valid": report.get("seal_reconstruction_valid"),
        "governance_chain_sealable": report.get("governance_chain_sealable"),
        "governance_chain_state": report.get("governance_chain_state"),
        "seal_blockers": report.get("seal_blockers", []),
        "seal_warnings": report.get("seal_warnings", []),
    }
    return "controlled-runtime-execution-boundary-" + _stable_hash(payload)[:16]


def _transaction_validation_for_boundary(
    *,
    mutation_transaction_contract: Any | None,
    previous_transaction_state: str | None,
    verification_report: Any | None,
    rollback_report: Any | None,
    seal_report: Any | None,
    replay_report: Any | None,
) -> Dict[str, Any]:
    if not isinstance(mutation_transaction_contract, dict):
        return {
            "ok": True,
            "schema_version": "governed_runtime_mutation_transaction.v1",
            "transaction_id": "",
            "transaction_state": "",
            "previous_transaction_state": _text(previous_transaction_state),
            "transition_valid": True,
            "rollback_state": "not_applicable",
            "verification_state": "not_applicable",
            "seal_state": "not_applicable",
            "replay_consistency_state": "not_applicable",
            "blocking_issues": [],
            "reason_codes": [],
        }
    return validate_governed_runtime_mutation_transaction_lifecycle(
        mutation_transaction_contract,
        previous_transaction_state=previous_transaction_state,
        verification_report=verification_report,
        rollback_report=rollback_report,
        seal_report=seal_report,
        replay_report=replay_report,
    )


def _evidence_validation_for_boundary(
    *,
    evidence_chain_records: Iterable[Any] | None,
    transaction_id: str,
    replay_evidence: Any | None,
    seal_evidence: Any | None,
) -> Dict[str, Any]:
    if evidence_chain_records is None:
        return {
            "ok": True,
            "schema_version": "runtime_evidence_chain.v1",
            "evidence_chain_valid": True,
            "evidence_integrity_state": "not_applicable",
            "replay_evidence_consistent": True,
            "evidence_tamper_detected": False,
            "evidence_seal_valid": True,
            "latest_evidence_id": "",
            "evidence_count": 0,
            "blocking_issues": [],
            "reason_codes": [],
        }
    return validate_runtime_evidence_chain(
        evidence_chain_records,
        transaction_id=transaction_id,
        replay_evidence=replay_evidence,
        seal_evidence=seal_evidence,
    )


def _reconstruction_validation_for_boundary(
    *,
    reconstruction_contract: Any | None,
    transaction_contract: Any | None,
    expected_evidence_chain: Iterable[Any] | None,
    rollback_reconstruction: Any | None,
    seal_reconstruction: Any | None,
) -> Dict[str, Any]:
    if not isinstance(reconstruction_contract, dict):
        return {
            "ok": True,
            "schema_version": "runtime_recovery_reconstruction.v1",
            "reconstruction_id": "",
            "source_transaction_id": "",
            "reconstruction_state": "not_applicable",
            "reconstruction_consistent": True,
            "replay_order_valid": True,
            "reconstruction_divergence_detected": False,
            "rollback_reconstruction_valid": True,
            "seal_reconstruction_valid": True,
            "replay_source_count": 0,
            "blocking_issues": [],
            "reason_codes": [],
        }
    return validate_runtime_recovery_reconstruction(
        reconstruction_contract,
        transaction_contract=transaction_contract,
        expected_evidence_chain=expected_evidence_chain,
        rollback_reconstruction=rollback_reconstruction,
        seal_reconstruction=seal_reconstruction,
    )


def _infer_request_intent(payload: Mapping[str, Any]) -> str:
    explicit = _text(payload.get("execution_intent") or payload.get("intent"))
    if explicit in EXECUTION_INTENTS and explicit != INTENT_READ_ONLY:
        return explicit

    request_type = _text(payload.get("request_type")).lower()
    action_type = _text(payload.get("action_type") or payload.get("action") or payload.get("type")).lower()
    operation = _text(payload.get("operation") or payload.get("effect_type")).lower()
    text = " ".join([request_type, action_type, operation])

    if payload.get("execute") is True or payload.get("executor_mutated") is True or "executor_control" in text:
        return INTENT_EXECUTOR_CONTROL
    if payload.get("scheduler_mutated") is True or payload.get("task_enqueued") is True or payload.get("planner_invoked") is True:
        return INTENT_SCHEDULER_CONTROL
    if "scheduler" in text or "enqueue" in text or "planner_control" in text:
        return INTENT_SCHEDULER_CONTROL
    if payload.get("persistence_written") is True or "persistence" in text:
        return INTENT_PERSISTENCE_WRITE
    if payload.get("network") is True or payload.get("external") is True or "external" in text or "network" in text:
        return INTENT_EXTERNAL_SIDE_EFFECT
    if request_type in {REQUEST_DRY_RUN_REPAIR, REQUEST_DRY_RUN_REPLAY, REQUEST_DRY_RUN_PLANNER_HANDOFF, REQUEST_APPROVAL_REQUIRED_REPAIR, REQUEST_APPROVAL_REQUIRED_REPLAY}:
        return INTENT_GOVERNED_MUTATION
    if any(token in text for token in ("mutation", "repair", "replay", "apply_patch", "apply_unified_diff")):
        return INTENT_GOVERNED_MUTATION
    if any(token in text for token in ("write", "append", "delete", "mkdir", "local_mutation")):
        return INTENT_LOCAL_MUTATION
    return INTENT_READ_ONLY


def _highest_intent(intents: Iterable[Any]) -> str:
    priority = {
        INTENT_READ_ONLY: 0,
        INTENT_LOCAL_MUTATION: 1,
        INTENT_GOVERNED_MUTATION: 2,
        INTENT_EXTERNAL_SIDE_EFFECT: 3,
        INTENT_PERSISTENCE_WRITE: 4,
        INTENT_SCHEDULER_CONTROL: 5,
        INTENT_EXECUTOR_CONTROL: 6,
    }
    highest = INTENT_READ_ONLY
    for intent in intents or []:
        value = _text(intent)
        if priority.get(value, -1) > priority.get(highest, 0):
            highest = value
    return highest


def _required_capabilities_for_intent(execution_intent: str) -> List[str]:
    mapping = {
        INTENT_READ_ONLY: [],
        INTENT_LOCAL_MUTATION: ["runtime.local_mutation", "runtime.rollback"],
        INTENT_GOVERNED_MUTATION: ["runtime.governed_mutation", "runtime.approval", "runtime.rollback", "runtime.replay"],
        INTENT_EXTERNAL_SIDE_EFFECT: ["runtime.external_side_effect", "runtime.approval", "runtime.audit"],
        INTENT_PERSISTENCE_WRITE: ["runtime.persistence_service_write", "runtime.audit"],
        INTENT_SCHEDULER_CONTROL: ["runtime.scheduler_owner", "runtime.approval", "runtime.audit"],
        INTENT_EXECUTOR_CONTROL: ["runtime.executor_owner", "runtime.approval", "runtime.audit"],
    }
    return list(mapping.get(_text(execution_intent), ["runtime.review"]))


def _approval_required_for_intent(execution_intent: str) -> bool:
    return _text(execution_intent) in {
        INTENT_GOVERNED_MUTATION,
        INTENT_EXTERNAL_SIDE_EFFECT,
        INTENT_PERSISTENCE_WRITE,
        INTENT_SCHEDULER_CONTROL,
    }


def _grant_expiration_valid(value: str, *, now: datetime | None = None) -> bool:
    if not value:
        return False
    try:
        normalized = value.replace("Z", "+00:00")
        expires_at = datetime.fromisoformat(normalized)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
    except Exception:
        return False
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return expires_at > current


def _validate_delegation_chain(grant: Mapping[str, Any]) -> Dict[str, Any]:
    chain = grant.get("delegation_chain")
    if chain is None:
        return {"delegation_chain_valid": True, "blocking_issues": []}
    if not isinstance(chain, list):
        return {
            "delegation_chain_valid": False,
            "blocking_issues": [{"kind": "invalid_delegation_chain", "reason": "expected_list"}],
        }
    if chain and grant.get("delegation_allowed") is not True:
        return {
            "delegation_chain_valid": False,
            "blocking_issues": [{"kind": "delegation_not_allowed"}],
        }
    issues: List[Dict[str, Any]] = []
    for index, item in enumerate(chain):
        payload = item if isinstance(item, dict) else {}
        if not _text(payload.get("delegator")) or not _text(payload.get("delegate")):
            issues.append({"kind": "invalid_delegation_chain", "index": index, "reason": "missing_party"})
        if payload.get("delegation_allowed") is False and index < len(chain) - 1:
            issues.append({"kind": "delegation_chain_broken", "index": index})
    return {
        "delegation_chain_valid": not issues,
        "blocking_issues": _dedupe_issues(issues),
    }


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
