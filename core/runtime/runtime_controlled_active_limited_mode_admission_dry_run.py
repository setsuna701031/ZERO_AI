from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA = (
    "zero.runtime.controlled_active_limited_mode_admission_dry_run.v1"
)

REQUIRED_ADMISSION_REQUEST_FIELDS = (
    "request_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "requested_mode",
    "source_layer",
    "admission_scope",
    "ownership_verification",
    "operator_approval",
    "state_dry_run_review",
    "boundary_locks",
    "audit_required",
)

BOUNDARY_LOCKS = {
    "runtime_mode_transition_allowed": False,
    "controlled_active_mode_enabled": False,
    "admission_commit_allowed": False,
    "limited_scheduler_enabled": False,
    "internal_execution_enabled": False,
    "runtime_state_mutation_allowed": False,
    "file_mutation_allowed": False,
    "external_tool_execution_allowed": False,
    "network_io_allowed": False,
    "unbounded_autonomy_allowed": False,
    "self_start_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_mode_transition_locked",
    "controlled_active_mode_locked",
    "admission_commit_locked",
    "operator_approval_preview_only",
    "runtime_ownership_preview_only",
    "limited_scheduler_locked",
    "internal_execution_locked",
    "runtime_state_mutation_locked",
    "file_mutation_locked",
    "external_tool_execution_locked",
    "network_io_locked",
    "unbounded_autonomy_locked",
    "self_start_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_ADMISSION_REQUEST_FIELDS if field not in record]


def _unlock_attempts(boundary_locks: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in BOUNDARY_LOCKS.items()
        if boundary_locks.get(key, expected) is not expected
    ]


def build_controlled_active_limited_mode_admission_dry_run_request(
    *,
    request_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
) -> dict[str, Any]:
    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA,
        "request_id": request_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "requested_mode": "controlled_active_limited",
        "source_layer": "controlled_active_limited_mode_state_dry_run",
        "admission_scope": "dry_run_only",
        "ownership_verification": {
            "required": True,
            "preview_only": True,
            "runtime_owner_verified": False,
            "ownership_commit_allowed": False,
        },
        "operator_approval": {
            "required": True,
            "preview_only": True,
            "operator_approved": False,
            "approval_commit_allowed": False,
        },
        "state_dry_run_review": {
            "required": True,
            "accepted_layer": "controlled_active_limited_mode_state_dry_run",
            "runtime_state_mutated": False,
            "review_sealed": True,
        },
        "boundary_locks": deepcopy(BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_controlled_active_limited_mode_admission_dry_run_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))

    ownership = _as_mapping(record.get("ownership_verification"))
    approval = _as_mapping(record.get("operator_approval"))
    review = _as_mapping(record.get("state_dry_run_review"))

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("admission_scope") != "dry_run_only":
        problems.append("admission_scope_not_dry_run_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if ownership.get("preview_only") is not True:
        problems.append("ownership_not_preview_only")
    if ownership.get("runtime_owner_verified") is not False:
        problems.append("runtime_owner_verified_in_dry_run")
    if ownership.get("ownership_commit_allowed") is not False:
        problems.append("ownership_commit_allowed")
    if approval.get("preview_only") is not True:
        problems.append("approval_not_preview_only")
    if approval.get("operator_approved") is not False:
        problems.append("operator_approved_in_dry_run")
    if approval.get("approval_commit_allowed") is not False:
        problems.append("approval_commit_allowed")
    if review.get("runtime_state_mutated") is not False:
        problems.append("runtime_state_mutated")
    if review.get("review_sealed") is not True:
        problems.append("state_dry_run_review_not_sealed")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA,
        "valid": not problems,
        "request_id": record.get("request_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_admission_dry_run_request" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "admission_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "audit_required": True,
    }


def preview_runtime_ownership_verification(request: dict[str, Any]) -> dict[str, Any]:
    ownership = _as_mapping(_as_mapping(request).get("ownership_verification"))
    attempted_commit = ownership.get("runtime_owner_verified") is True or ownership.get(
        "ownership_commit_allowed"
    ) is True

    return {
        "preview": "runtime_ownership_verification",
        "preview_only": True,
        "runtime_owner_verified": False,
        "ownership_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["runtime_ownership_commit_blocked"]
            if attempted_commit
            else ["runtime_ownership_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def preview_operator_approval(request: dict[str, Any]) -> dict[str, Any]:
    approval = _as_mapping(_as_mapping(request).get("operator_approval"))
    attempted_commit = approval.get("operator_approved") is True or approval.get(
        "approval_commit_allowed"
    ) is True

    return {
        "preview": "operator_approval",
        "preview_only": True,
        "operator_approved": False,
        "approval_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["operator_approval_commit_blocked"]
            if attempted_commit
            else ["operator_approval_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def decide_controlled_active_limited_mode_admission_dry_run(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_active_limited_mode_admission_dry_run_request(request)
    ownership = preview_runtime_ownership_verification(request)
    approval = preview_operator_approval(request)

    return {
        "decision_schema": CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA
        + ".decision",
        "decision": "NO_GO_ADMISSION_DRY_RUN_ONLY",
        "request_valid": validation["valid"],
        "request_id": validation.get("request_id"),
        "candidate_id": validation.get("candidate_id"),
        "ownership_preview": ownership,
        "operator_approval_preview": approval,
        "admission_allowed": False,
        "admission_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "blockers": list(
            dict.fromkeys(
                validation["problems"]
                + ownership["blockers"]
                + approval["blockers"]
                + ["admission_commit_locked"]
            )
        ),
        "audit_required": True,
    }


def build_controlled_active_limited_mode_admission_dry_run_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    decision = decide_controlled_active_limited_mode_admission_dry_run(request)

    return {
        "audit_schema": CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA
        + ".audit",
        "decision": "reserved_no_controlled_active_limited_mode_admission",
        "request_id": decision.get("request_id"),
        "candidate_id": decision.get("candidate_id"),
        "admission_decision": decision,
        "admission_allowed": False,
        "admission_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def build_controlled_active_limited_mode_admission_dry_run_no_go_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_active_limited_mode_admission_dry_run_audit_record(request)

    return {
        "seal": "controlled_active_limited_mode_admission_dry_run_no_go",
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_ADMISSION_GO_FOR_DRY_RUN_REVIEW_ONLY",
        "next_package": 1161,
        "request_id": audit.get("request_id"),
        "candidate_id": audit.get("candidate_id"),
        "admission_allowed": False,
        "admission_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_decision": audit["decision"],
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA",
    "REQUIRED_ADMISSION_REQUEST_FIELDS",
    "BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_active_limited_mode_admission_dry_run_request",
    "validate_controlled_active_limited_mode_admission_dry_run_request",
    "preview_runtime_ownership_verification",
    "preview_operator_approval",
    "decide_controlled_active_limited_mode_admission_dry_run",
    "build_controlled_active_limited_mode_admission_dry_run_audit_record",
    "build_controlled_active_limited_mode_admission_dry_run_no_go_seal",
]
