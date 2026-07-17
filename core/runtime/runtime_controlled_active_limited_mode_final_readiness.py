from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA = (
    "zero.runtime.controlled_active_limited_mode_final_readiness.v1"
)

REQUIRED_FINAL_READINESS_FIELDS = (
    "readiness_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "previous_seals",
    "ownership_chain",
    "readiness_candidate",
    "safety_boundary_matrix",
    "go_candidate_evidence",
    "audit_required",
)

REQUIRED_PREVIOUS_SEALS = (
    "controlled_activation_gate_review",
    "controlled_active_limited_mode_candidate",
    "controlled_active_limited_mode_state_dry_run",
    "controlled_active_limited_mode_admission_dry_run",
    "controlled_active_limited_mode_execution_dry_run",
)

SAFETY_BOUNDARY_LOCKS = {
    "mutation_lock": True,
    "file_mutation_lock": True,
    "external_tool_lock": True,
    "network_io_lock": True,
    "autonomy_lock": True,
    "self_start_lock": True,
    "rollback_authority_required": True,
    "rollback_authority_live": False,
    "kill_switch_authority_required": True,
    "kill_switch_authority_live": False,
    "activation_allowed": False,
    "activation_commit_allowed": False,
    "runtime_mode_transition_allowed": False,
    "execution_allowed": False,
    "runtime_state_mutation_allowed": False,
    "file_mutation_allowed": False,
    "external_tool_execution_allowed": False,
    "network_io_allowed": False,
    "unbounded_autonomy_allowed": False,
    "self_start_allowed": False,
}

REQUIRED_BLOCKERS = (
    "previous_seal_aggregation_required",
    "ownership_chain_preview_only",
    "ownership_commit_locked",
    "activation_candidate_preview_only",
    "activation_locked",
    "activation_commit_locked",
    "runtime_mode_transition_locked",
    "mutation_locked",
    "file_mutation_locked",
    "external_tool_execution_locked",
    "network_io_locked",
    "unbounded_autonomy_locked",
    "self_start_locked",
    "go_candidate_evidence_only",
    "real_execution_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_FINAL_READINESS_FIELDS if field not in record]


def _safety_unlock_attempts(matrix: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in SAFETY_BOUNDARY_LOCKS.items()
        if matrix.get(key, expected) is not expected
    ]


def build_controlled_active_limited_mode_final_readiness_request(
    *,
    readiness_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
    previous_seals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seals = (
        deepcopy(previous_seals)
        if previous_seals is not None
        else {
            seal: {"present": True, "closed": True, "sealed": True}
            for seal in REQUIRED_PREVIOUS_SEALS
        }
    )

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA,
        "readiness_id": readiness_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "readiness_scope": "final_readiness_dry_run_only",
        "previous_seals": seals,
        "ownership_chain": {
            "preview_only": True,
            "operator_id": operator_id,
            "executor_id": executor_id,
            "activation_attempt_id": activation_attempt_id,
            "candidate_id": candidate_id,
            "ownership_verified": False,
            "ownership_commit_allowed": False,
        },
        "readiness_candidate": {
            "preview_only": True,
            "activation_ready_candidate": True,
            "activation_allowed": False,
            "activation_commit_allowed": False,
            "runtime_mode_transition_allowed": False,
        },
        "safety_boundary_matrix": deepcopy(SAFETY_BOUNDARY_LOCKS),
        "go_candidate_evidence": {
            "evidence_only": True,
            "go_candidate_created": True,
            "go_allowed": False,
            "activation_allowed": False,
            "execution_allowed": False,
        },
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def aggregate_previous_final_readiness_seals(
    previous_seals: dict[str, Any],
) -> dict[str, Any]:
    seals = _as_mapping(previous_seals)
    missing: list[str] = []
    open_or_unsealed: list[str] = []

    for seal_name in REQUIRED_PREVIOUS_SEALS:
        seal = _as_mapping(seals.get(seal_name))
        if not seal or seal.get("present") is not True:
            missing.append(seal_name)
            continue
        if seal.get("closed") is not True or seal.get("sealed") is not True:
            open_or_unsealed.append(seal_name)

    blockers = []
    if missing:
        blockers.append("missing_previous_seal")
    if open_or_unsealed:
        blockers.append("open_previous_seal")

    return {
        "aggregation": "previous_final_readiness_seals",
        "required_seals": list(REQUIRED_PREVIOUS_SEALS),
        "missing_seals": missing,
        "open_or_unsealed_seals": open_or_unsealed,
        "all_required_present": not missing,
        "all_required_closed_and_sealed": not missing and not open_or_unsealed,
        "readiness_blocked": bool(missing or open_or_unsealed),
        "blockers": blockers,
    }


def preview_final_readiness_ownership_chain(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    chain = _as_mapping(record.get("ownership_chain"))
    attempted_commit = (
        chain.get("ownership_verified") is True
        or chain.get("ownership_commit_allowed") is True
    )

    return {
        "preview": "final_readiness_ownership_chain",
        "preview_only": True,
        "operator_id": record.get("operator_id") or chain.get("operator_id"),
        "executor_id": record.get("executor_id") or chain.get("executor_id"),
        "activation_attempt_id": record.get("activation_attempt_id")
        or chain.get("activation_attempt_id"),
        "candidate_id": record.get("candidate_id") or chain.get("candidate_id"),
        "ownership_verified": False,
        "ownership_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["ownership_commit_attempt_blocked"]
            if attempted_commit
            else ["ownership_chain_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def build_activation_readiness_candidate_preview(
    request: dict[str, Any],
) -> dict[str, Any]:
    candidate = _as_mapping(_as_mapping(request).get("readiness_candidate"))
    attempted_activation = (
        candidate.get("activation_allowed") is True
        or candidate.get("activation_commit_allowed") is True
        or candidate.get("runtime_mode_transition_allowed") is True
    )

    return {
        "preview": "activation_readiness_candidate",
        "preview_only": True,
        "activation_ready_candidate": True,
        "activation_ready_candidate_evidence_only": True,
        "activation_allowed": False,
        "activation_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "blocked": True,
        "blockers": (
            ["activation_unlock_attempt_blocked"]
            if attempted_activation
            else ["activation_candidate_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def evaluate_final_safety_boundary_matrix(request: dict[str, Any]) -> dict[str, Any]:
    matrix = _as_mapping(_as_mapping(request).get("safety_boundary_matrix"))
    unlocks = _safety_unlock_attempts(matrix)

    return {
        "matrix": "final_safety_boundary",
        "locks": deepcopy(SAFETY_BOUNDARY_LOCKS),
        "unlock_attempts": unlocks,
        "unlock_attempt_reported": bool(unlocks),
        "all_execution_surfaces_locked": not unlocks,
        "blockers": ["safety_boundary_unlock_attempt"] if unlocks else [],
        "rollback_authority_required": True,
        "rollback_authority_live": False,
        "kill_switch_authority_required": True,
        "kill_switch_authority_live": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutation_allowed": False,
        "file_mutation_allowed": False,
        "external_tool_execution_allowed": False,
        "network_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
    }


def build_final_go_candidate_evidence(request: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_mapping(_as_mapping(request).get("go_candidate_evidence"))
    attempted_go = (
        evidence.get("go_allowed") is True
        or evidence.get("activation_allowed") is True
        or evidence.get("execution_allowed") is True
    )

    return {
        "evidence": "final_go_candidate",
        "evidence_only": True,
        "go_candidate_created": True,
        "go_allowed": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "blocked": True,
        "blockers": (
            ["go_candidate_unlock_attempt_blocked"]
            if attempted_go
            else ["go_candidate_evidence_only"]
        ),
        "runtime_state_mutated": False,
    }


def validate_controlled_active_limited_mode_final_readiness_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    seal_aggregation = aggregate_previous_final_readiness_seals(
        _as_mapping(record.get("previous_seals"))
    )
    ownership = preview_final_readiness_ownership_chain(record)
    candidate = build_activation_readiness_candidate_preview(record)
    safety = evaluate_final_safety_boundary_matrix(record)
    go_evidence = build_final_go_candidate_evidence(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if seal_aggregation["readiness_blocked"]:
        problems.append("previous_seal_aggregation_blocked")
    if record.get("readiness_scope") != "final_readiness_dry_run_only":
        problems.append("readiness_scope_not_final_dry_run_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    if ownership["blockers"] == ["ownership_commit_attempt_blocked"]:
        problems.append("ownership_commit_attempt")
    if candidate["blockers"] == ["activation_unlock_attempt_blocked"]:
        problems.append("activation_unlock_attempt")
    if safety["unlock_attempts"]:
        problems.append("safety_boundary_unlock_attempt")
    if go_evidence["blockers"] == ["go_candidate_unlock_attempt_blocked"]:
        problems.append("go_candidate_unlock_attempt")

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA,
        "valid": not problems,
        "readiness_id": record.get("readiness_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_final_readiness_dry_run" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "previous_seal_aggregation": seal_aggregation,
        "ownership_preview": ownership,
        "readiness_candidate": candidate,
        "safety_boundary_matrix": safety,
        "go_candidate_evidence": go_evidence,
        "activation_allowed": False,
        "activation_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
        "audit_required": True,
    }


def build_controlled_active_limited_mode_final_readiness_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_active_limited_mode_final_readiness_request(request)

    return {
        "audit_schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA + ".audit",
        "decision": "reserved_no_controlled_active_limited_mode_final_activation",
        "readiness_id": validation.get("readiness_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "previous_seal_aggregation": validation["previous_seal_aggregation"],
        "ownership_preview": validation["ownership_preview"],
        "readiness_candidate": validation["readiness_candidate"],
        "safety_boundary_matrix": validation["safety_boundary_matrix"],
        "go_candidate_evidence": validation["go_candidate_evidence"],
        "activation_happened": False,
        "activation_allowed": False,
        "activation_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_controlled_active_limited_mode_final_readiness_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_active_limited_mode_final_readiness_audit_record(request)

    return {
        "seal": "controlled_active_limited_mode_final_readiness_dry_run_closure",
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_ACTIVATION_GO_FOR_FINAL_READINESS_DRY_RUN_ONLY",
        "next_package": 1177,
        "readiness_id": audit.get("readiness_id"),
        "candidate_id": audit.get("candidate_id"),
        "audit_decision": audit["decision"],
        "activation_happened": False,
        "activation_allowed": False,
        "activation_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "file_mutation_allowed": False,
        "external_tool_execution_allowed": False,
        "network_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "all_execution_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA",
    "REQUIRED_FINAL_READINESS_FIELDS",
    "REQUIRED_PREVIOUS_SEALS",
    "SAFETY_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_active_limited_mode_final_readiness_request",
    "validate_controlled_active_limited_mode_final_readiness_request",
    "aggregate_previous_final_readiness_seals",
    "preview_final_readiness_ownership_chain",
    "build_activation_readiness_candidate_preview",
    "evaluate_final_safety_boundary_matrix",
    "build_final_go_candidate_evidence",
    "build_controlled_active_limited_mode_final_readiness_audit_record",
    "build_controlled_active_limited_mode_final_readiness_milestone_seal",
]
