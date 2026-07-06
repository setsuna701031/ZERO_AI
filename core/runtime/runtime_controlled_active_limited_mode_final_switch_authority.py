from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA = (
    "zero.runtime.controlled_active_limited_mode_final_switch_authority.v1"
)

REQUIRED_FINAL_SWITCH_AUTHORITY_FIELDS = (
    "switch_authority_id",
    "readiness_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "operator_confirmation_token",
    "rollback_authority",
    "kill_switch_authority",
    "bounded_runtime_lease",
    "controlled_activation_transaction",
    "audit_required",
)

FINAL_SWITCH_BOUNDARY_LOCKS = {
    "activation_allowed": False,
    "final_switch_allowed": False,
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
}

REQUIRED_BLOCKERS = (
    "operator_confirmation_token_preview_only",
    "operator_confirmation_commit_locked",
    "rollback_authority_live_preview_only",
    "rollback_authority_commit_locked",
    "kill_switch_authority_live_preview_only",
    "kill_switch_authority_commit_locked",
    "bounded_runtime_lease_preview_only",
    "bounded_runtime_lease_commit_locked",
    "controlled_activation_transaction_preview_only",
    "controlled_activation_transaction_commit_locked",
    "final_switch_locked",
    "activation_locked",
    "runtime_mode_transition_locked",
    "execution_locked",
    "mutation_locked",
    "external_io_locked",
    "autonomy_locked",
    "self_start_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [
        field for field in REQUIRED_FINAL_SWITCH_AUTHORITY_FIELDS if field not in record
    ]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in FINAL_SWITCH_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_controlled_active_limited_mode_final_switch_authority_request(
    *,
    switch_authority_id: str,
    readiness_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
) -> dict[str, Any]:
    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA,
        "switch_authority_id": switch_authority_id,
        "readiness_id": readiness_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "authority_scope": "final_switch_authority_review_only",
        "operator_confirmation_token": {
            "preview_only": True,
            "token_present": True,
            "token_verified": False,
            "token_commit_allowed": False,
        },
        "rollback_authority": {
            "preview_only": True,
            "authority_required": True,
            "live_readiness_candidate": True,
            "authority_live": False,
            "authority_commit_allowed": False,
        },
        "kill_switch_authority": {
            "preview_only": True,
            "authority_required": True,
            "live_readiness_candidate": True,
            "authority_live": False,
            "authority_commit_allowed": False,
        },
        "bounded_runtime_lease": {
            "preview_only": True,
            "lease_candidate_created": True,
            "lease_active": False,
            "lease_commit_allowed": False,
            "unbounded_autonomy_allowed": False,
        },
        "controlled_activation_transaction": {
            "preview_only": True,
            "transaction_candidate_created": True,
            "transaction_opened": False,
            "transaction_commit_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        },
        "boundary_locks": deepcopy(FINAL_SWITCH_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def preview_operator_confirmation_token(request: dict[str, Any]) -> dict[str, Any]:
    token = _as_mapping(_as_mapping(request).get("operator_confirmation_token"))
    attempted_commit = (
        token.get("token_verified") is True
        or token.get("token_commit_allowed") is True
    )

    return {
        "preview": "operator_confirmation_token",
        "preview_only": True,
        "token_present": token.get("token_present") is True,
        "token_verified": False,
        "token_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["operator_confirmation_token_commit_attempt_blocked"]
            if attempted_commit
            else ["operator_confirmation_token_preview_only"]
        ),
    }


def preview_rollback_authority_live_readiness(
    request: dict[str, Any],
) -> dict[str, Any]:
    authority = _as_mapping(_as_mapping(request).get("rollback_authority"))
    attempted_live = (
        authority.get("authority_live") is True
        or authority.get("authority_commit_allowed") is True
    )

    return {
        "preview": "rollback_authority_live_readiness",
        "preview_only": True,
        "authority_required": True,
        "live_readiness_candidate": True,
        "authority_live": False,
        "authority_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["rollback_authority_live_attempt_blocked"]
            if attempted_live
            else ["rollback_authority_live_preview_only"]
        ),
    }


def preview_kill_switch_authority_live_readiness(
    request: dict[str, Any],
) -> dict[str, Any]:
    authority = _as_mapping(_as_mapping(request).get("kill_switch_authority"))
    attempted_live = (
        authority.get("authority_live") is True
        or authority.get("authority_commit_allowed") is True
    )

    return {
        "preview": "kill_switch_authority_live_readiness",
        "preview_only": True,
        "authority_required": True,
        "live_readiness_candidate": True,
        "authority_live": False,
        "authority_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["kill_switch_authority_live_attempt_blocked"]
            if attempted_live
            else ["kill_switch_authority_live_preview_only"]
        ),
    }


def preview_bounded_runtime_lease(request: dict[str, Any]) -> dict[str, Any]:
    lease = _as_mapping(_as_mapping(request).get("bounded_runtime_lease"))
    attempted_commit = (
        lease.get("lease_active") is True
        or lease.get("lease_commit_allowed") is True
        or lease.get("unbounded_autonomy_allowed") is True
    )

    return {
        "preview": "bounded_runtime_lease",
        "preview_only": True,
        "lease_candidate_created": True,
        "lease_active": False,
        "lease_commit_allowed": False,
        "unbounded_autonomy_allowed": False,
        "blocked": True,
        "blockers": (
            ["bounded_runtime_lease_commit_attempt_blocked"]
            if attempted_commit
            else ["bounded_runtime_lease_preview_only"]
        ),
    }


def preview_controlled_activation_transaction(
    request: dict[str, Any],
) -> dict[str, Any]:
    transaction = _as_mapping(
        _as_mapping(request).get("controlled_activation_transaction")
    )
    attempted_commit = (
        transaction.get("transaction_opened") is True
        or transaction.get("transaction_commit_allowed") is True
        or transaction.get("activation_allowed") is True
        or transaction.get("runtime_mode_transition_allowed") is True
        or transaction.get("execution_allowed") is True
        or transaction.get("mutation_allowed") is True
    )

    return {
        "preview": "controlled_activation_transaction",
        "preview_only": True,
        "transaction_candidate_created": True,
        "transaction_opened": False,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "blocked": True,
        "blockers": (
            ["controlled_activation_transaction_commit_attempt_blocked"]
            if attempted_commit
            else ["controlled_activation_transaction_preview_only"]
        ),
    }


def validate_controlled_active_limited_mode_final_switch_authority_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    token = preview_operator_confirmation_token(record)
    rollback = preview_rollback_authority_live_readiness(record)
    kill_switch = preview_kill_switch_authority_live_readiness(record)
    lease = preview_bounded_runtime_lease(record)
    transaction = preview_controlled_activation_transaction(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("authority_scope") != "final_switch_authority_review_only":
        problems.append("authority_scope_not_review_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    if token["blockers"] == ["operator_confirmation_token_commit_attempt_blocked"]:
        problems.append("operator_confirmation_token_commit_attempt")
    if rollback["blockers"] == ["rollback_authority_live_attempt_blocked"]:
        problems.append("rollback_authority_live_attempt")
    if kill_switch["blockers"] == ["kill_switch_authority_live_attempt_blocked"]:
        problems.append("kill_switch_authority_live_attempt")
    if lease["blockers"] == ["bounded_runtime_lease_commit_attempt_blocked"]:
        problems.append("bounded_runtime_lease_commit_attempt")
    if (
        transaction["blockers"]
        == ["controlled_activation_transaction_commit_attempt_blocked"]
    ):
        problems.append("controlled_activation_transaction_commit_attempt")

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA,
        "valid": not problems,
        "switch_authority_id": record.get("switch_authority_id"),
        "readiness_id": record.get("readiness_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_final_switch_authority_review" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "operator_confirmation_token": token,
        "rollback_authority": rollback,
        "kill_switch_authority": kill_switch,
        "bounded_runtime_lease": lease,
        "controlled_activation_transaction": transaction,
        "activation_allowed": False,
        "final_switch_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
    }


def build_controlled_active_limited_mode_final_switch_authority_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = (
        validate_controlled_active_limited_mode_final_switch_authority_request(request)
    )

    return {
        "audit_schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA
        + ".audit",
        "decision": "reserved_no_controlled_active_limited_mode_final_switch",
        "switch_authority_id": validation.get("switch_authority_id"),
        "readiness_id": validation.get("readiness_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "operator_confirmation_token": validation["operator_confirmation_token"],
        "rollback_authority": validation["rollback_authority"],
        "kill_switch_authority": validation["kill_switch_authority"],
        "bounded_runtime_lease": validation["bounded_runtime_lease"],
        "controlled_activation_transaction": validation[
            "controlled_activation_transaction"
        ],
        "activation_happened": False,
        "final_switch_happened": False,
        "activation_allowed": False,
        "final_switch_allowed": False,
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


def build_controlled_active_limited_mode_final_switch_authority_no_go_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_active_limited_mode_final_switch_authority_audit_record(
        request
    )

    return {
        "seal": "controlled_active_limited_mode_final_switch_authority_no_go",
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_FINAL_SWITCH_AUTHORITY_REVIEW_ONLY",
        "next_package": 1185,
        "switch_authority_id": audit.get("switch_authority_id"),
        "readiness_id": audit.get("readiness_id"),
        "candidate_id": audit.get("candidate_id"),
        "audit_decision": audit["decision"],
        "activation_happened": False,
        "final_switch_happened": False,
        "activation_allowed": False,
        "final_switch_allowed": False,
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
    "CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA",
    "REQUIRED_FINAL_SWITCH_AUTHORITY_FIELDS",
    "FINAL_SWITCH_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_active_limited_mode_final_switch_authority_request",
    "validate_controlled_active_limited_mode_final_switch_authority_request",
    "preview_operator_confirmation_token",
    "preview_rollback_authority_live_readiness",
    "preview_kill_switch_authority_live_readiness",
    "preview_bounded_runtime_lease",
    "preview_controlled_activation_transaction",
    "build_controlled_active_limited_mode_final_switch_authority_audit_record",
    "build_controlled_active_limited_mode_final_switch_authority_no_go_seal",
]
