from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA = (
    "zero.runtime.controlled_active_limited_mode_state_dry_run.v1"
)

REQUIRED_CANDIDATE_FIELDS = (
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "source_mode",
    "candidate_mode",
    "candidate_status",
    "gate_review",
    "state_scope",
    "scheduler_preview",
    "execution_preview",
    "transition_preview",
    "mutation_boundary",
    "audit_required",
)

LOCKED_BOUNDARIES = {
    "runtime_mode_transition_allowed": False,
    "controlled_active_mode_enabled": False,
    "limited_scheduler_enabled": False,
    "internal_execution_enabled": False,
    "real_runtime_state_mutation_allowed": False,
    "real_file_mutation_allowed": False,
    "external_tool_execution_allowed": False,
    "network_io_allowed": False,
    "unbounded_autonomy_allowed": False,
    "self_start_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_mode_transition_locked",
    "controlled_active_mode_locked",
    "limited_scheduler_dry_run_only",
    "internal_execution_dry_run_only",
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


def _missing_required_fields(candidate: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_FIELDS if field not in candidate]


def _boundary_unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in LOCKED_BOUNDARIES.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_controlled_active_limited_mode_state_dry_run_candidate(
    *,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    source_mode: str = "controlled_activation_gate_review",
    state_scope: str = "runtime_state_dry_run",
) -> dict[str, Any]:
    """Build a deterministic candidate record without enabling runtime state changes."""

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "source_mode": source_mode,
        "candidate_mode": "controlled_active_limited_mode_state_dry_run",
        "candidate_status": "dry_run_only",
        "state_scope": state_scope,
        "gate_review": {
            "required": True,
            "accepted_status": "sealed_candidate_only",
            "gate_opened": False,
        },
        "scheduler_preview": {
            "preview_only": True,
            "limited_scheduler_enabled": False,
            "unbounded_loop_allowed": False,
            "dispatch_allowed": False,
        },
        "execution_preview": {
            "preview_only": True,
            "internal_execution_enabled": False,
            "external_execution_allowed": False,
            "tool_execution_allowed": False,
        },
        "transition_preview": {
            "preview_only": True,
            "from_mode": source_mode,
            "to_mode": "controlled_active_limited",
            "runtime_mode_transition_allowed": False,
            "runtime_state_mutated": False,
        },
        "mutation_boundary": deepcopy(LOCKED_BOUNDARIES),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_controlled_active_limited_mode_state_dry_run_candidate(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Validate candidate completeness and prove that it is dry-run-only."""

    record = _as_mapping(candidate)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [
        blocker for blocker in REQUIRED_BLOCKERS if blocker not in blockers
    ]
    unlock_attempts = _boundary_unlock_attempts(_as_mapping(record.get("mutation_boundary")))

    gate_review = _as_mapping(record.get("gate_review"))
    scheduler_preview = _as_mapping(record.get("scheduler_preview"))
    execution_preview = _as_mapping(record.get("execution_preview"))
    transition_preview = _as_mapping(record.get("transition_preview"))

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlock_attempts:
        problems.append("boundary_unlock_attempt")
    if record.get("candidate_status") != "dry_run_only":
        problems.append("candidate_not_dry_run_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if gate_review.get("gate_opened") is not False:
        problems.append("gate_opened")
    if scheduler_preview.get("limited_scheduler_enabled") is not False:
        problems.append("limited_scheduler_enabled")
    if execution_preview.get("internal_execution_enabled") is not False:
        problems.append("internal_execution_enabled")
    if transition_preview.get("runtime_mode_transition_allowed") is not False:
        problems.append("runtime_mode_transition_allowed")
    if transition_preview.get("runtime_state_mutated") is not False:
        problems.append("runtime_state_mutated")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA,
        "valid": not problems,
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_dry_run_candidate" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlock_attempts,
        "runtime_mode_transition_allowed": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "audit_required": True,
    }


def evaluate_limited_scheduler_state_preview(candidate: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(candidate)
    scheduler_preview = _as_mapping(record.get("scheduler_preview"))
    attempted_enable = scheduler_preview.get("limited_scheduler_enabled") is True
    attempted_unbounded_loop = scheduler_preview.get("unbounded_loop_allowed") is True

    blockers = []
    if attempted_enable:
        blockers.append("limited_scheduler_enable_blocked")
    if attempted_unbounded_loop:
        blockers.append("unbounded_scheduler_loop_blocked")

    return {
        "preview": "limited_scheduler_state",
        "preview_only": True,
        "limited_scheduler_enabled": False,
        "dispatch_allowed": False,
        "unbounded_loop_allowed": False,
        "blocked": True,
        "blockers": blockers or ["limited_scheduler_dry_run_only"],
        "runtime_state_mutated": False,
    }


def evaluate_internal_execution_state_preview(candidate: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(candidate)
    execution_preview = _as_mapping(record.get("execution_preview"))
    attempted_internal_enable = execution_preview.get("internal_execution_enabled") is True
    attempted_external = (
        execution_preview.get("external_execution_allowed") is True
        or execution_preview.get("tool_execution_allowed") is True
    )

    blockers = []
    if attempted_internal_enable:
        blockers.append("internal_execution_enable_blocked")
    if attempted_external:
        blockers.append("external_execution_escape_blocked")

    return {
        "preview": "internal_execution_state",
        "preview_only": True,
        "internal_execution_enabled": False,
        "external_execution_allowed": False,
        "tool_execution_allowed": False,
        "blocked": True,
        "blockers": blockers or ["internal_execution_dry_run_only"],
        "runtime_state_mutated": False,
    }


def simulate_limited_runtime_state_transition(candidate: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(candidate)
    transition_preview = _as_mapping(record.get("transition_preview"))
    attempted_transition = (
        transition_preview.get("runtime_mode_transition_allowed") is True
        or transition_preview.get("runtime_state_mutated") is True
    )

    return {
        "preview": "limited_runtime_state_transition",
        "preview_only": True,
        "from_mode": transition_preview.get("from_mode", record.get("source_mode")),
        "to_mode": transition_preview.get("to_mode", "controlled_active_limited"),
        "transition_allowed": False,
        "runtime_mode_transition_allowed": False,
        "runtime_state_mutated": False,
        "blocked": True,
        "blockers": (
            ["runtime_state_transition_attempt_blocked"]
            if attempted_transition
            else ["runtime_mode_transition_locked"]
        ),
    }


def evaluate_dry_run_mutation_boundary(candidate: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(candidate)
    mutation_boundary = _as_mapping(record.get("mutation_boundary"))
    unlock_attempts = _boundary_unlock_attempts(mutation_boundary)

    return {
        "preview": "dry_run_mutation_boundary",
        "real_runtime_state_mutation_allowed": False,
        "real_file_mutation_allowed": False,
        "external_tool_execution_allowed": False,
        "network_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "unlock_attempts": unlock_attempts,
        "blocked": True,
        "blockers": unlock_attempts or ["runtime_state_mutation_locked"],
        "runtime_state_mutated": False,
    }


def build_controlled_active_limited_mode_state_dry_run_audit_record(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)
    scheduler = evaluate_limited_scheduler_state_preview(candidate)
    execution = evaluate_internal_execution_state_preview(candidate)
    transition = simulate_limited_runtime_state_transition(candidate)
    mutation = evaluate_dry_run_mutation_boundary(candidate)

    return {
        "audit_schema": CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA + ".audit",
        "decision": "reserved_no_controlled_active_limited_mode_state_transition",
        "candidate_id": validation.get("candidate_id"),
        "candidate_valid": validation["valid"],
        "readiness": "dry_run_only",
        "scheduler_preview": scheduler,
        "execution_preview": execution,
        "transition_preview": transition,
        "mutation_boundary": mutation,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def build_controlled_active_limited_mode_state_dry_run_milestone_seal(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_active_limited_mode_state_dry_run_audit_record(candidate)

    return {
        "seal": "controlled_active_limited_mode_state_dry_run_milestone",
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_DRY_RUN_STATE_REVIEW_ONLY",
        "next_package": 1153,
        "candidate_id": audit.get("candidate_id"),
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "limited_scheduler_enabled": False,
        "internal_execution_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_decision": audit["decision"],
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA",
    "REQUIRED_CANDIDATE_FIELDS",
    "LOCKED_BOUNDARIES",
    "REQUIRED_BLOCKERS",
    "build_controlled_active_limited_mode_state_dry_run_candidate",
    "validate_controlled_active_limited_mode_state_dry_run_candidate",
    "evaluate_limited_scheduler_state_preview",
    "evaluate_internal_execution_state_preview",
    "simulate_limited_runtime_state_transition",
    "evaluate_dry_run_mutation_boundary",
    "build_controlled_active_limited_mode_state_dry_run_audit_record",
    "build_controlled_active_limited_mode_state_dry_run_milestone_seal",
]
