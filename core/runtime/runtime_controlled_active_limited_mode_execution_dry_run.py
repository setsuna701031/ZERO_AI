from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA = (
    "zero.runtime.controlled_active_limited_mode_execution_dry_run.v1"
)

REQUIRED_EXECUTION_ADMISSION_FIELDS = (
    "execution_admission_id",
    "admission_request_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "admission_decision",
    "executor_ownership",
    "execution_session",
    "execution_lifecycle",
    "result_preview",
    "boundary_locks",
    "audit_required",
)

BOUNDARY_LOCKS = {
    "execution_admission_allowed": False,
    "execution_start_allowed": False,
    "execution_commit_allowed": False,
    "executor_ownership_committed": False,
    "execution_session_opened": False,
    "runtime_mode_transition_allowed": False,
    "controlled_active_mode_enabled": False,
    "runtime_state_mutation_allowed": False,
    "file_mutation_allowed": False,
    "external_tool_execution_allowed": False,
    "network_io_allowed": False,
    "unbounded_autonomy_allowed": False,
    "self_start_allowed": False,
}

REQUIRED_BLOCKERS = (
    "execution_admission_locked",
    "execution_start_locked",
    "execution_commit_locked",
    "executor_ownership_preview_only",
    "execution_session_preview_only",
    "runtime_mode_transition_locked",
    "controlled_active_mode_locked",
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
    return [field for field in REQUIRED_EXECUTION_ADMISSION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_controlled_active_limited_mode_execution_dry_run_admission(
    *,
    execution_admission_id: str,
    admission_request_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
) -> dict[str, Any]:
    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA,
        "execution_admission_id": execution_admission_id,
        "admission_request_id": admission_request_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "source_layer": "controlled_active_limited_mode_admission_dry_run",
        "execution_scope": "dry_run_only",
        "admission_decision": {
            "required": True,
            "expected_decision": "NO_GO_ADMISSION_DRY_RUN_ONLY",
            "admission_allowed": False,
            "admission_commit_allowed": False,
        },
        "executor_ownership": {
            "required": True,
            "preview_only": True,
            "executor_owner_verified": False,
            "executor_ownership_commit_allowed": False,
        },
        "execution_session": {
            "required": True,
            "preview_only": True,
            "session_opened": False,
            "session_commit_allowed": False,
        },
        "execution_lifecycle": {
            "required": True,
            "preview_only": True,
            "start_allowed": False,
            "step_execution_allowed": False,
            "completion_allowed": False,
        },
        "result_preview": {
            "required": True,
            "preview_only": True,
            "result_committed": False,
            "runtime_state_mutated": False,
        },
        "boundary_locks": deepcopy(BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_controlled_active_limited_mode_execution_dry_run_admission(
    admission: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(admission)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))

    decision = _as_mapping(record.get("admission_decision"))
    ownership = _as_mapping(record.get("executor_ownership"))
    session = _as_mapping(record.get("execution_session"))
    lifecycle = _as_mapping(record.get("execution_lifecycle"))
    result_preview = _as_mapping(record.get("result_preview"))

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("execution_scope") != "dry_run_only":
        problems.append("execution_scope_not_dry_run_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if decision.get("admission_allowed") is not False:
        problems.append("admission_allowed")
    if decision.get("admission_commit_allowed") is not False:
        problems.append("admission_commit_allowed")
    if ownership.get("preview_only") is not True:
        problems.append("executor_ownership_not_preview_only")
    if ownership.get("executor_owner_verified") is not False:
        problems.append("executor_owner_verified_in_dry_run")
    if ownership.get("executor_ownership_commit_allowed") is not False:
        problems.append("executor_ownership_commit_allowed")
    if session.get("preview_only") is not True:
        problems.append("execution_session_not_preview_only")
    if session.get("session_opened") is not False:
        problems.append("execution_session_opened")
    if session.get("session_commit_allowed") is not False:
        problems.append("execution_session_commit_allowed")
    if lifecycle.get("start_allowed") is not False:
        problems.append("execution_start_allowed")
    if lifecycle.get("step_execution_allowed") is not False:
        problems.append("step_execution_allowed")
    if lifecycle.get("completion_allowed") is not False:
        problems.append("execution_completion_allowed")
    if result_preview.get("result_committed") is not False:
        problems.append("result_committed")
    if result_preview.get("runtime_state_mutated") is not False:
        problems.append("runtime_state_mutated")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA,
        "valid": not problems,
        "execution_admission_id": record.get("execution_admission_id"),
        "admission_request_id": record.get("admission_request_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_execution_dry_run_admission" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "execution_admission_allowed": False,
        "execution_start_allowed": False,
        "execution_commit_allowed": False,
        "runtime_state_mutated": False,
        "audit_required": True,
    }


def preview_executor_ownership(admission: dict[str, Any]) -> dict[str, Any]:
    ownership = _as_mapping(_as_mapping(admission).get("executor_ownership"))
    attempted_commit = ownership.get("executor_owner_verified") is True or ownership.get(
        "executor_ownership_commit_allowed"
    ) is True

    return {
        "preview": "executor_ownership",
        "preview_only": True,
        "executor_owner_verified": False,
        "executor_ownership_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["executor_ownership_commit_blocked"]
            if attempted_commit
            else ["executor_ownership_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def preview_execution_session(admission: dict[str, Any]) -> dict[str, Any]:
    session = _as_mapping(_as_mapping(admission).get("execution_session"))
    attempted_open = session.get("session_opened") is True or session.get(
        "session_commit_allowed"
    ) is True

    return {
        "preview": "execution_session",
        "preview_only": True,
        "session_opened": False,
        "session_commit_allowed": False,
        "blocked": True,
        "blockers": (
            ["execution_session_open_blocked"]
            if attempted_open
            else ["execution_session_preview_only"]
        ),
        "runtime_state_mutated": False,
    }


def preview_execution_lifecycle(admission: dict[str, Any]) -> dict[str, Any]:
    lifecycle = _as_mapping(_as_mapping(admission).get("execution_lifecycle"))
    attempted_execution = (
        lifecycle.get("start_allowed") is True
        or lifecycle.get("step_execution_allowed") is True
        or lifecycle.get("completion_allowed") is True
    )

    return {
        "preview": "execution_lifecycle",
        "preview_only": True,
        "start_allowed": False,
        "step_execution_allowed": False,
        "completion_allowed": False,
        "blocked": True,
        "blockers": (
            ["execution_lifecycle_start_blocked"]
            if attempted_execution
            else ["execution_start_locked"]
        ),
        "runtime_state_mutated": False,
    }


def preview_execution_result(admission: dict[str, Any]) -> dict[str, Any]:
    result_preview = _as_mapping(_as_mapping(admission).get("result_preview"))
    attempted_commit = result_preview.get("result_committed") is True or result_preview.get(
        "runtime_state_mutated"
    ) is True

    return {
        "preview": "execution_result",
        "preview_only": True,
        "result_committed": False,
        "runtime_state_mutated": False,
        "blocked": True,
        "blockers": (
            ["execution_result_commit_blocked"]
            if attempted_commit
            else ["execution_commit_locked"]
        ),
    }


def decide_controlled_active_limited_mode_execution_dry_run(
    admission: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_controlled_active_limited_mode_execution_dry_run_admission(
        admission
    )
    ownership = preview_executor_ownership(admission)
    session = preview_execution_session(admission)
    lifecycle = preview_execution_lifecycle(admission)
    result_preview = preview_execution_result(admission)

    return {
        "decision_schema": CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA
        + ".decision",
        "decision": "NO_GO_EXECUTION_DRY_RUN_ONLY",
        "request_valid": validation["valid"],
        "execution_admission_id": validation.get("execution_admission_id"),
        "admission_request_id": validation.get("admission_request_id"),
        "candidate_id": validation.get("candidate_id"),
        "executor_ownership_preview": ownership,
        "execution_session_preview": session,
        "execution_lifecycle_preview": lifecycle,
        "execution_result_preview": result_preview,
        "execution_admission_allowed": False,
        "execution_start_allowed": False,
        "execution_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "blockers": list(
            dict.fromkeys(
                validation["problems"]
                + ownership["blockers"]
                + session["blockers"]
                + lifecycle["blockers"]
                + result_preview["blockers"]
                + ["execution_admission_locked"]
            )
        ),
        "audit_required": True,
    }


def build_controlled_active_limited_mode_execution_dry_run_audit_record(
    admission: dict[str, Any],
) -> dict[str, Any]:
    decision = decide_controlled_active_limited_mode_execution_dry_run(admission)

    return {
        "audit_schema": CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA
        + ".audit",
        "decision": "reserved_no_controlled_active_limited_mode_execution",
        "execution_admission_id": decision.get("execution_admission_id"),
        "admission_request_id": decision.get("admission_request_id"),
        "candidate_id": decision.get("candidate_id"),
        "execution_decision": decision,
        "execution_admission_allowed": False,
        "execution_start_allowed": False,
        "execution_commit_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_mode_enabled": False,
        "runtime_state_mutated": False,
        "real_mutation_allowed": False,
        "external_io_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def build_controlled_active_limited_mode_execution_dry_run_milestone_seal(
    admission: dict[str, Any],
) -> dict[str, Any]:
    audit = build_controlled_active_limited_mode_execution_dry_run_audit_record(admission)

    return {
        "seal": "controlled_active_limited_mode_execution_dry_run_milestone",
        "schema": CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_EXECUTION_GO_FOR_DRY_RUN_REVIEW_ONLY",
        "next_package": 1169,
        "execution_admission_id": audit.get("execution_admission_id"),
        "admission_request_id": audit.get("admission_request_id"),
        "candidate_id": audit.get("candidate_id"),
        "execution_admission_allowed": False,
        "execution_start_allowed": False,
        "execution_commit_allowed": False,
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
    "CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA",
    "REQUIRED_EXECUTION_ADMISSION_FIELDS",
    "BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_controlled_active_limited_mode_execution_dry_run_admission",
    "validate_controlled_active_limited_mode_execution_dry_run_admission",
    "preview_executor_ownership",
    "preview_execution_session",
    "preview_execution_lifecycle",
    "preview_execution_result",
    "decide_controlled_active_limited_mode_execution_dry_run",
    "build_controlled_active_limited_mode_execution_dry_run_audit_record",
    "build_controlled_active_limited_mode_execution_dry_run_milestone_seal",
]
