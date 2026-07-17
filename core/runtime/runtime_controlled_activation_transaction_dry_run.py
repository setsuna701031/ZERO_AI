from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA = (
    "zero.runtime.controlled_activation_transaction_dry_run.v1"
)

REQUIRED_TRANSACTION_DRY_RUN_FIELDS = (
    "transaction_dry_run_id",
    "switch_authority_id",
    "readiness_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "final_readiness_evidence",
    "final_switch_authority_review",
    "transaction_plan",
    "pre_commit_safety_check",
    "commit_boundary",
    "rollback_path",
    "audit_required",
)

TRANSACTION_BOUNDARY_LOCKS = {
    "transaction_allowed": False,
    "transaction_commit_allowed": False,
    "activation_allowed": False,
    "runtime_mode_transition_allowed": False,
    "execution_allowed": False,
    "mutation_allowed": False,
    "file_mutation_allowed": False,
    "external_io_allowed": False,
    "external_tool_execution_allowed": False,
    "network_io_allowed": False,
    "autonomy_allowed": False,
    "unbounded_autonomy_allowed": False,
    "self_start_allowed": False,
    "final_switch_allowed": False,
}

REQUIRED_BLOCKERS = (
    "final_readiness_dry_run_binding_required",
    "final_switch_authority_review_binding_required",
    "transaction_plan_preview_only",
    "pre_commit_safety_check_preview_only",
    "commit_boundary_preview_only",
    "transaction_commit_locked",
    "rollback_path_preview_only",
    "transaction_locked",
    "activation_locked",
    "runtime_mode_transition_locked",
    "execution_locked",
    "mutation_locked",
    "external_io_locked",
    "autonomy_locked",
    "self_start_locked",
    "final_switch_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_TRANSACTION_DRY_RUN_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in TRANSACTION_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_controlled_activation_transaction_dry_run_request(
    *,
    transaction_dry_run_id: str,
    switch_authority_id: str,
    readiness_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
    final_readiness_evidence: dict[str, Any] | None = None,
    final_switch_authority_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = (
        deepcopy(final_readiness_evidence)
        if final_readiness_evidence is not None
        else {
            "present": True,
            "closed": True,
            "schema": "zero.runtime.controlled_active_limited_mode_final_readiness.v1",
            "final_decision": "NO_GO_FOR_REAL_ACTIVATION_GO_FOR_FINAL_READINESS_DRY_RUN_ONLY",
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
        }
    )
    switch_review = (
        deepcopy(final_switch_authority_review)
        if final_switch_authority_review is not None
        else {
            "present": True,
            "closed": True,
            "schema": "zero.runtime.controlled_active_limited_mode_final_switch_authority.v1",
            "final_decision": "NO_GO_FOR_REAL_FINAL_SWITCH_AUTHORITY_REVIEW_ONLY",
            "final_switch_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        }
    )

    return {
        "schema": CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA,
        "transaction_dry_run_id": transaction_dry_run_id,
        "switch_authority_id": switch_authority_id,
        "readiness_id": readiness_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "transaction_scope": "transaction_dry_run_only",
        "final_readiness_evidence": readiness,
        "final_switch_authority_review": switch_review,
        "transaction_plan": {
            "preview_only": True,
            "plan_created": True,
            "transaction_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        },
        "pre_commit_safety_check": {
            "preview_only": True,
            "safety_check_created": True,
            "safety_pass_candidate": True,
            "commit_allowed": False,
            "unlock_detected": False,
        },
        "commit_boundary": {
            "preview_only": True,
            "boundary_created": True,
            "transaction_commit_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        },
        "rollback_path": {
            "preview_only": True,
            "rollback_path_created": True,
            "rollback_live": False,
            "rollback_commit_allowed": False,
        },
        "boundary_locks": deepcopy(TRANSACTION_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def bind_final_switch_authority_review(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    readiness = _as_mapping(record.get("final_readiness_evidence"))
    switch_review = _as_mapping(record.get("final_switch_authority_review"))

    readiness_problems: list[str] = []
    if readiness.get("present") is not True:
        readiness_problems.append("final_readiness_evidence_missing")
    if readiness.get("closed") is not True:
        readiness_problems.append("final_readiness_evidence_open")
    for key in (
        "activation_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
    ):
        if readiness.get(key) is not False:
            readiness_problems.append(f"final_readiness_{key}_unlock_attempt")

    switch_problems: list[str] = []
    if switch_review.get("present") is not True:
        switch_problems.append("final_switch_authority_review_missing")
    if switch_review.get("closed") is not True:
        switch_problems.append("final_switch_authority_review_open")
    for key in (
        "final_switch_allowed",
        "activation_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
        "mutation_allowed",
    ):
        if switch_review.get(key) is not False:
            switch_problems.append(f"final_switch_authority_{key}_unlock_attempt")

    return {
        "binding": "final_switch_authority_review",
        "final_readiness_bound": not readiness_problems,
        "final_switch_authority_bound": not switch_problems,
        "readiness_id": record.get("readiness_id"),
        "switch_authority_id": record.get("switch_authority_id"),
        "blocked": bool(readiness_problems or switch_problems),
        "problems": readiness_problems + switch_problems,
        "final_switch_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def preview_controlled_activation_transaction_plan(
    request: dict[str, Any],
) -> dict[str, Any]:
    plan = _as_mapping(_as_mapping(request).get("transaction_plan"))
    attempted_unlock = (
        plan.get("transaction_allowed") is True
        or plan.get("activation_allowed") is True
        or plan.get("runtime_mode_transition_allowed") is True
        or plan.get("execution_allowed") is True
        or plan.get("mutation_allowed") is True
    )

    return {
        "preview": "controlled_activation_transaction_plan",
        "preview_only": True,
        "plan_created": True,
        "transaction_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "blocked": True,
        "blockers": (
            ["transaction_plan_unlock_attempt_blocked"]
            if attempted_unlock
            else ["transaction_plan_preview_only"]
        ),
    }


def preview_pre_commit_safety_check(request: dict[str, Any]) -> dict[str, Any]:
    safety = _as_mapping(_as_mapping(request).get("pre_commit_safety_check"))
    attempted_commit = (
        safety.get("commit_allowed") is True
        or safety.get("unlock_detected") is True
    )

    return {
        "preview": "pre_commit_safety_check",
        "preview_only": True,
        "safety_check_created": True,
        "safety_pass_candidate": safety.get("safety_pass_candidate") is True,
        "commit_allowed": False,
        "unlock_detected": attempted_commit,
        "blocked": True,
        "blockers": (
            ["pre_commit_safety_unlock_attempt_blocked"]
            if attempted_commit
            else ["pre_commit_safety_check_preview_only"]
        ),
    }


def preview_transaction_commit_boundary(request: dict[str, Any]) -> dict[str, Any]:
    boundary = _as_mapping(_as_mapping(request).get("commit_boundary"))
    attempted_commit = (
        boundary.get("transaction_commit_allowed") is True
        or boundary.get("activation_allowed") is True
        or boundary.get("runtime_mode_transition_allowed") is True
        or boundary.get("execution_allowed") is True
        or boundary.get("mutation_allowed") is True
    )

    return {
        "preview": "transaction_commit_boundary",
        "preview_only": True,
        "boundary_created": True,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "blocked": True,
        "blockers": (
            ["transaction_commit_boundary_attempt_blocked"]
            if attempted_commit
            else ["commit_boundary_preview_only"]
        ),
    }


def preview_transaction_rollback_path(request: dict[str, Any]) -> dict[str, Any]:
    rollback = _as_mapping(_as_mapping(request).get("rollback_path"))
    attempted_live = (
        rollback.get("rollback_live") is True
        or rollback.get("rollback_commit_allowed") is True
    )

    return {
        "preview": "transaction_rollback_path",
        "preview_only": True,
        "rollback_path_created": True,
        "rollback_live": False,
        "rollback_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["rollback_path_live_attempt_blocked"]
            if attempted_live
            else ["rollback_path_preview_only"]
        ),
    }


def validate_controlled_activation_transaction_dry_run_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    binding = bind_final_switch_authority_review(record)
    plan = preview_controlled_activation_transaction_plan(record)
    safety = preview_pre_commit_safety_check(record)
    commit_boundary = preview_transaction_commit_boundary(record)
    rollback = preview_transaction_rollback_path(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if binding["blocked"]:
        problems.append("final_switch_authority_binding_blocked")
    if record.get("transaction_scope") != "transaction_dry_run_only":
        problems.append("transaction_scope_not_dry_run_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    if plan["blockers"] == ["transaction_plan_unlock_attempt_blocked"]:
        problems.append("transaction_plan_unlock_attempt")
    if safety["blockers"] == ["pre_commit_safety_unlock_attempt_blocked"]:
        problems.append("pre_commit_safety_unlock_attempt")
    if commit_boundary["blockers"] == ["transaction_commit_boundary_attempt_blocked"]:
        problems.append("transaction_commit_boundary_attempt")
    if rollback["blockers"] == ["rollback_path_live_attempt_blocked"]:
        problems.append("rollback_path_live_attempt")

    return {
        "schema": CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA,
        "valid": not problems,
        "transaction_dry_run_id": record.get("transaction_dry_run_id"),
        "switch_authority_id": record.get("switch_authority_id"),
        "readiness_id": record.get("readiness_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_transaction_dry_run" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "final_switch_authority_binding": binding,
        "transaction_plan": plan,
        "pre_commit_safety_check": safety,
        "commit_boundary": commit_boundary,
        "rollback_path": rollback,
        "transaction_allowed": False,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
    }


def build_controlled_activation_transaction_dry_run_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_activation_transaction_dry_run_request(request)

    return {
        "audit_schema": CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA + ".audit",
        "decision": "reserved_no_controlled_activation_transaction_commit",
        "transaction_dry_run_id": validation.get("transaction_dry_run_id"),
        "switch_authority_id": validation.get("switch_authority_id"),
        "readiness_id": validation.get("readiness_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "final_switch_authority_binding": validation[
            "final_switch_authority_binding"
        ],
        "transaction_plan": validation["transaction_plan"],
        "pre_commit_safety_check": validation["pre_commit_safety_check"],
        "commit_boundary": validation["commit_boundary"],
        "rollback_path": validation["rollback_path"],
        "transaction_happened": False,
        "transaction_committed": False,
        "activation_happened": False,
        "final_switch_happened": False,
        "transaction_allowed": False,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_controlled_activation_transaction_dry_run_no_go_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_activation_transaction_dry_run_audit_record(request)

    return {
        "seal": "controlled_activation_transaction_dry_run_no_go",
        "schema": CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_TRANSACTION_GO_FOR_TRANSACTION_DRY_RUN_ONLY",
        "next_package": 1193,
        "transaction_dry_run_id": audit.get("transaction_dry_run_id"),
        "switch_authority_id": audit.get("switch_authority_id"),
        "readiness_id": audit.get("readiness_id"),
        "candidate_id": audit.get("candidate_id"),
        "audit_decision": audit["decision"],
        "transaction_happened": False,
        "transaction_committed": False,
        "activation_happened": False,
        "final_switch_happened": False,
        "transaction_allowed": False,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "all_execution_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA",
    "REQUIRED_TRANSACTION_DRY_RUN_FIELDS",
    "TRANSACTION_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_activation_transaction_dry_run_request",
    "validate_controlled_activation_transaction_dry_run_request",
    "bind_final_switch_authority_review",
    "preview_controlled_activation_transaction_plan",
    "preview_pre_commit_safety_check",
    "preview_transaction_commit_boundary",
    "preview_transaction_rollback_path",
    "build_controlled_activation_transaction_dry_run_audit_record",
    "build_controlled_activation_transaction_dry_run_no_go_seal",
]
