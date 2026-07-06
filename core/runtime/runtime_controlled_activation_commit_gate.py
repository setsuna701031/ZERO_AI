from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA = (
    "zero.runtime.controlled_activation_commit_gate.v1"
)

REQUIRED_COMMIT_GATE_FIELDS = (
    "commit_gate_id",
    "transaction_dry_run_id",
    "switch_authority_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "final_switch_authority_review",
    "transaction_dry_run_evidence",
    "transaction_commit_authority",
    "activation_commit_token",
    "commit_window",
    "post_commit_rollback_binding",
    "limited_runtime_opening_gate",
    "audit_required",
)

COMMIT_GATE_BOUNDARY_LOCKS = {
    "commit_gate_allowed": False,
    "transaction_commit_allowed": False,
    "activation_commit_allowed": False,
    "activation_allowed": False,
    "limited_runtime_open_allowed": False,
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
    "final_switch_authority_review_binding_required",
    "transaction_dry_run_binding_required",
    "transaction_commit_authority_review_only",
    "transaction_commit_locked",
    "activation_commit_token_review_only",
    "activation_commit_locked",
    "commit_window_preview_only",
    "commit_gate_locked",
    "post_commit_rollback_binding_review_only",
    "limited_runtime_opening_gate_preview_only",
    "limited_runtime_open_locked",
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
    return [field for field in REQUIRED_COMMIT_GATE_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in COMMIT_GATE_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_controlled_activation_commit_gate_request(
    *,
    commit_gate_id: str,
    transaction_dry_run_id: str,
    switch_authority_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
    final_switch_authority_review: dict[str, Any] | None = None,
    transaction_dry_run_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    switch_review = (
        deepcopy(final_switch_authority_review)
        if final_switch_authority_review is not None
        else {
            "present": True,
            "closed": True,
            "final_decision": "NO_GO_FOR_REAL_FINAL_SWITCH_AUTHORITY_REVIEW_ONLY",
            "final_switch_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        }
    )
    transaction_evidence = (
        deepcopy(transaction_dry_run_evidence)
        if transaction_dry_run_evidence is not None
        else {
            "present": True,
            "closed": True,
            "final_decision": "NO_GO_FOR_REAL_TRANSACTION_GO_FOR_TRANSACTION_DRY_RUN_ONLY",
            "transaction_allowed": False,
            "transaction_commit_allowed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        }
    )

    return {
        "schema": CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA,
        "commit_gate_id": commit_gate_id,
        "transaction_dry_run_id": transaction_dry_run_id,
        "switch_authority_id": switch_authority_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "gate_scope": "commit_gate_review_only",
        "final_switch_authority_review": switch_review,
        "transaction_dry_run_evidence": transaction_evidence,
        "transaction_commit_authority": {
            "review_only": True,
            "authority_candidate": True,
            "transaction_commit_allowed": False,
            "authority_commit_allowed": False,
        },
        "activation_commit_token": {
            "review_only": True,
            "token_candidate": True,
            "token_verified": False,
            "activation_commit_allowed": False,
            "token_commit_allowed": False,
        },
        "commit_window": {
            "preview_only": True,
            "window_candidate": True,
            "commit_gate_allowed": False,
            "transaction_commit_allowed": False,
            "activation_commit_allowed": False,
        },
        "post_commit_rollback_binding": {
            "review_only": True,
            "rollback_binding_candidate": True,
            "rollback_binding_live": False,
            "rollback_binding_commit_allowed": False,
        },
        "limited_runtime_opening_gate": {
            "preview_only": True,
            "opening_candidate": True,
            "limited_runtime_open_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
        },
        "boundary_locks": deepcopy(COMMIT_GATE_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _review_parent_evidence(request: dict[str, Any]) -> dict[str, Any]:
    switch = _as_mapping(request.get("final_switch_authority_review"))
    transaction = _as_mapping(request.get("transaction_dry_run_evidence"))
    problems: list[str] = []

    if switch.get("present") is not True:
        problems.append("final_switch_authority_review_missing")
    if switch.get("closed") is not True:
        problems.append("final_switch_authority_review_open")
    for key in (
        "final_switch_allowed",
        "activation_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
        "mutation_allowed",
    ):
        if switch.get(key) is not False:
            problems.append(f"final_switch_authority_{key}_unlock_attempt")

    if transaction.get("present") is not True:
        problems.append("transaction_dry_run_evidence_missing")
    if transaction.get("closed") is not True:
        problems.append("transaction_dry_run_evidence_open")
    for key in (
        "transaction_allowed",
        "transaction_commit_allowed",
        "activation_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
        "mutation_allowed",
    ):
        if transaction.get(key) is not False:
            problems.append(f"transaction_dry_run_{key}_unlock_attempt")

    return {
        "review": "commit_gate_parent_evidence",
        "final_switch_authority_bound": not any(
            p.startswith("final_switch_authority") for p in problems
        ),
        "transaction_dry_run_bound": not any(
            p.startswith("transaction_dry_run") for p in problems
        ),
        "blocked": bool(problems),
        "problems": problems,
        "final_switch_allowed": False,
        "transaction_commit_allowed": False,
        "activation_allowed": False,
    }


def review_transaction_commit_authority(request: dict[str, Any]) -> dict[str, Any]:
    authority = _as_mapping(_as_mapping(request).get("transaction_commit_authority"))
    attempted_commit = (
        authority.get("transaction_commit_allowed") is True
        or authority.get("authority_commit_allowed") is True
    )

    return {
        "review": "transaction_commit_authority",
        "review_only": True,
        "authority_candidate": True,
        "transaction_commit_allowed": False,
        "authority_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["transaction_commit_authority_attempt_blocked"]
            if attempted_commit
            else ["transaction_commit_authority_review_only"]
        ),
    }


def review_activation_commit_token(request: dict[str, Any]) -> dict[str, Any]:
    token = _as_mapping(_as_mapping(request).get("activation_commit_token"))
    attempted_commit = (
        token.get("token_verified") is True
        or token.get("activation_commit_allowed") is True
        or token.get("token_commit_allowed") is True
    )

    return {
        "review": "activation_commit_token",
        "review_only": True,
        "token_candidate": True,
        "token_verified": False,
        "activation_commit_allowed": False,
        "token_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["activation_commit_token_attempt_blocked"]
            if attempted_commit
            else ["activation_commit_token_review_only"]
        ),
    }


def preview_commit_window(request: dict[str, Any]) -> dict[str, Any]:
    window = _as_mapping(_as_mapping(request).get("commit_window"))
    attempted_open = (
        window.get("commit_gate_allowed") is True
        or window.get("transaction_commit_allowed") is True
        or window.get("activation_commit_allowed") is True
    )

    return {
        "preview": "commit_window",
        "preview_only": True,
        "window_candidate": True,
        "commit_gate_allowed": False,
        "transaction_commit_allowed": False,
        "activation_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["commit_window_open_attempt_blocked"]
            if attempted_open
            else ["commit_window_preview_only"]
        ),
    }


def review_post_commit_rollback_binding(request: dict[str, Any]) -> dict[str, Any]:
    binding = _as_mapping(_as_mapping(request).get("post_commit_rollback_binding"))
    attempted_live = (
        binding.get("rollback_binding_live") is True
        or binding.get("rollback_binding_commit_allowed") is True
    )

    return {
        "review": "post_commit_rollback_binding",
        "review_only": True,
        "rollback_binding_candidate": True,
        "rollback_binding_live": False,
        "rollback_binding_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["post_commit_rollback_binding_live_attempt_blocked"]
            if attempted_live
            else ["post_commit_rollback_binding_review_only"]
        ),
    }


def preview_limited_runtime_opening_gate(request: dict[str, Any]) -> dict[str, Any]:
    gate = _as_mapping(_as_mapping(request).get("limited_runtime_opening_gate"))
    attempted_open = (
        gate.get("limited_runtime_open_allowed") is True
        or gate.get("runtime_mode_transition_allowed") is True
        or gate.get("execution_allowed") is True
        or gate.get("mutation_allowed") is True
    )

    return {
        "preview": "limited_runtime_opening_gate",
        "preview_only": True,
        "opening_candidate": True,
        "limited_runtime_open_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "blocked": True,
        "blockers": (
            ["limited_runtime_open_attempt_blocked"]
            if attempted_open
            else ["limited_runtime_opening_gate_preview_only"]
        ),
    }


def validate_controlled_activation_commit_gate_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    parent_review = _review_parent_evidence(record)
    transaction_authority = review_transaction_commit_authority(record)
    activation_token = review_activation_commit_token(record)
    commit_window = preview_commit_window(record)
    rollback_binding = review_post_commit_rollback_binding(record)
    opening_gate = preview_limited_runtime_opening_gate(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if parent_review["blocked"]:
        problems.append("parent_evidence_binding_blocked")
    if record.get("gate_scope") != "commit_gate_review_only":
        problems.append("gate_scope_not_review_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    if transaction_authority["blockers"] == [
        "transaction_commit_authority_attempt_blocked"
    ]:
        problems.append("transaction_commit_authority_attempt")
    if activation_token["blockers"] == ["activation_commit_token_attempt_blocked"]:
        problems.append("activation_commit_token_attempt")
    if commit_window["blockers"] == ["commit_window_open_attempt_blocked"]:
        problems.append("commit_window_open_attempt")
    if rollback_binding["blockers"] == [
        "post_commit_rollback_binding_live_attempt_blocked"
    ]:
        problems.append("post_commit_rollback_binding_live_attempt")
    if opening_gate["blockers"] == ["limited_runtime_open_attempt_blocked"]:
        problems.append("limited_runtime_open_attempt")

    return {
        "schema": CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA,
        "valid": not problems,
        "commit_gate_id": record.get("commit_gate_id"),
        "transaction_dry_run_id": record.get("transaction_dry_run_id"),
        "switch_authority_id": record.get("switch_authority_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_commit_gate_review" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "parent_evidence_review": parent_review,
        "transaction_commit_authority": transaction_authority,
        "activation_commit_token": activation_token,
        "commit_window": commit_window,
        "post_commit_rollback_binding": rollback_binding,
        "limited_runtime_opening_gate": opening_gate,
        "commit_gate_allowed": False,
        "transaction_commit_allowed": False,
        "activation_commit_allowed": False,
        "activation_allowed": False,
        "limited_runtime_open_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
    }


def build_controlled_activation_commit_gate_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_activation_commit_gate_request(request)

    return {
        "audit_schema": CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA + ".audit",
        "decision": "reserved_no_controlled_activation_commit_gate",
        "commit_gate_id": validation.get("commit_gate_id"),
        "transaction_dry_run_id": validation.get("transaction_dry_run_id"),
        "switch_authority_id": validation.get("switch_authority_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "parent_evidence_review": validation["parent_evidence_review"],
        "transaction_commit_authority": validation["transaction_commit_authority"],
        "activation_commit_token": validation["activation_commit_token"],
        "commit_window": validation["commit_window"],
        "post_commit_rollback_binding": validation[
            "post_commit_rollback_binding"
        ],
        "limited_runtime_opening_gate": validation["limited_runtime_opening_gate"],
        "commit_gate_happened": False,
        "transaction_committed": False,
        "activation_committed": False,
        "activation_happened": False,
        "limited_runtime_opened": False,
        "commit_gate_allowed": False,
        "transaction_commit_allowed": False,
        "activation_commit_allowed": False,
        "activation_allowed": False,
        "limited_runtime_open_allowed": False,
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


def build_controlled_activation_commit_gate_no_go_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_activation_commit_gate_audit_record(request)

    return {
        "seal": "controlled_activation_commit_gate_no_go",
        "schema": CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_COMMIT_GATE_GO_FOR_REVIEW_ONLY",
        "next_package": 1201,
        "commit_gate_id": audit.get("commit_gate_id"),
        "transaction_dry_run_id": audit.get("transaction_dry_run_id"),
        "switch_authority_id": audit.get("switch_authority_id"),
        "candidate_id": audit.get("candidate_id"),
        "audit_decision": audit["decision"],
        "commit_gate_happened": False,
        "transaction_committed": False,
        "activation_committed": False,
        "activation_happened": False,
        "limited_runtime_opened": False,
        "commit_gate_allowed": False,
        "transaction_commit_allowed": False,
        "activation_commit_allowed": False,
        "activation_allowed": False,
        "limited_runtime_open_allowed": False,
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
    "CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA",
    "REQUIRED_COMMIT_GATE_FIELDS",
    "COMMIT_GATE_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_activation_commit_gate_request",
    "validate_controlled_activation_commit_gate_request",
    "review_transaction_commit_authority",
    "review_activation_commit_token",
    "preview_commit_window",
    "review_post_commit_rollback_binding",
    "preview_limited_runtime_opening_gate",
    "build_controlled_activation_commit_gate_audit_record",
    "build_controlled_activation_commit_gate_no_go_seal",
]
