from __future__ import annotations

from copy import deepcopy
from typing import Any


LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA = (
    "zero.runtime.limited_active_runtime_opening_gate.v1"
)

REQUIRED_OPENING_GATE_FIELDS = (
    "runtime_opening_gate_id",
    "commit_gate_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "commit_gate_evidence",
    "runtime_session_container",
    "limited_execution_lease",
    "capability_scope",
    "step_budget_and_watchdog",
    "live_rollback_and_shutdown",
    "audit_required",
)

OPENING_GATE_BOUNDARY_LOCKS = {
    "runtime_open_allowed": False,
    "limited_runtime_session_created": False,
    "execution_lease_active": False,
    "capability_scope_committed": False,
    "watchdog_live": False,
    "rollback_live": False,
    "shutdown_live": False,
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
}

REQUIRED_BLOCKERS = (
    "commit_gate_evidence_binding_required",
    "runtime_session_container_preview_only",
    "runtime_session_creation_locked",
    "limited_execution_lease_preview_only",
    "execution_lease_activation_locked",
    "capability_scope_preview_only",
    "capability_scope_commit_locked",
    "step_budget_and_watchdog_preview_only",
    "watchdog_live_locked",
    "rollback_and_shutdown_preview_only",
    "rollback_live_locked",
    "shutdown_live_locked",
    "runtime_open_locked",
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
    return [field for field in REQUIRED_OPENING_GATE_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in OPENING_GATE_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def build_limited_active_runtime_opening_gate_request(
    *,
    runtime_opening_gate_id: str,
    commit_gate_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
    commit_gate_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    commit_evidence = (
        deepcopy(commit_gate_evidence)
        if commit_gate_evidence is not None
        else {
            "present": True,
            "closed": True,
            "final_decision": "NO_GO_FOR_REAL_COMMIT_GATE_GO_FOR_REVIEW_ONLY",
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
        }
    )

    return {
        "schema": LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA,
        "runtime_opening_gate_id": runtime_opening_gate_id,
        "commit_gate_id": commit_gate_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "opening_scope": "limited_runtime_opening_gate_review_only",
        "commit_gate_evidence": commit_evidence,
        "runtime_session_container": {
            "preview_only": True,
            "container_candidate": True,
            "limited_runtime_session_created": False,
            "runtime_open_allowed": False,
        },
        "limited_execution_lease": {
            "preview_only": True,
            "lease_candidate": True,
            "execution_lease_active": False,
            "execution_allowed": False,
            "autonomy_allowed": False,
        },
        "capability_scope": {
            "preview_only": True,
            "scope_candidate": True,
            "capability_scope_committed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "external_io_allowed": False,
        },
        "step_budget_and_watchdog": {
            "preview_only": True,
            "step_budget_candidate": True,
            "watchdog_candidate": True,
            "watchdog_live": False,
            "execution_allowed": False,
            "autonomy_allowed": False,
        },
        "live_rollback_and_shutdown": {
            "preview_only": True,
            "rollback_candidate": True,
            "shutdown_candidate": True,
            "rollback_live": False,
            "shutdown_live": False,
        },
        "boundary_locks": deepcopy(OPENING_GATE_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _review_commit_gate_evidence(request: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_mapping(request.get("commit_gate_evidence"))
    problems: list[str] = []

    if evidence.get("present") is not True:
        problems.append("commit_gate_evidence_missing")
    if evidence.get("closed") is not True:
        problems.append("commit_gate_evidence_open")
    for key in (
        "commit_gate_allowed",
        "transaction_commit_allowed",
        "activation_commit_allowed",
        "activation_allowed",
        "limited_runtime_open_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
        "mutation_allowed",
        "external_io_allowed",
        "autonomy_allowed",
        "self_start_allowed",
    ):
        if evidence.get(key) is not False:
            problems.append(f"commit_gate_{key}_unlock_attempt")

    return {
        "review": "commit_gate_evidence_binding",
        "commit_gate_bound": not problems,
        "blocked": bool(problems),
        "problems": problems,
        "commit_gate_allowed": False,
        "limited_runtime_open_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
    }


def preview_runtime_session_container(request: dict[str, Any]) -> dict[str, Any]:
    container = _as_mapping(_as_mapping(request).get("runtime_session_container"))
    attempted_create = (
        container.get("limited_runtime_session_created") is True
        or container.get("runtime_open_allowed") is True
    )

    return {
        "preview": "runtime_session_container",
        "preview_only": True,
        "container_candidate": True,
        "limited_runtime_session_created": False,
        "runtime_open_allowed": False,
        "blocked": True,
        "blockers": (
            ["runtime_session_container_create_attempt_blocked"]
            if attempted_create
            else ["runtime_session_container_preview_only"]
        ),
    }


def preview_limited_execution_lease(request: dict[str, Any]) -> dict[str, Any]:
    lease = _as_mapping(_as_mapping(request).get("limited_execution_lease"))
    attempted_activate = (
        lease.get("execution_lease_active") is True
        or lease.get("execution_allowed") is True
        or lease.get("autonomy_allowed") is True
    )

    return {
        "preview": "limited_execution_lease",
        "preview_only": True,
        "lease_candidate": True,
        "execution_lease_active": False,
        "execution_allowed": False,
        "autonomy_allowed": False,
        "blocked": True,
        "blockers": (
            ["limited_execution_lease_activation_attempt_blocked"]
            if attempted_activate
            else ["limited_execution_lease_preview_only"]
        ),
    }


def preview_capability_scope(request: dict[str, Any]) -> dict[str, Any]:
    scope = _as_mapping(_as_mapping(request).get("capability_scope"))
    attempted_commit = (
        scope.get("capability_scope_committed") is True
        or scope.get("execution_allowed") is True
        or scope.get("mutation_allowed") is True
        or scope.get("external_io_allowed") is True
    )

    return {
        "preview": "capability_scope",
        "preview_only": True,
        "scope_candidate": True,
        "capability_scope_committed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "blocked": True,
        "blockers": (
            ["capability_scope_commit_attempt_blocked"]
            if attempted_commit
            else ["capability_scope_preview_only"]
        ),
    }


def preview_step_budget_and_watchdog_binding(
    request: dict[str, Any],
) -> dict[str, Any]:
    watchdog = _as_mapping(_as_mapping(request).get("step_budget_and_watchdog"))
    attempted_live = (
        watchdog.get("watchdog_live") is True
        or watchdog.get("execution_allowed") is True
        or watchdog.get("autonomy_allowed") is True
    )

    return {
        "preview": "step_budget_and_watchdog_binding",
        "preview_only": True,
        "step_budget_candidate": True,
        "watchdog_candidate": True,
        "watchdog_live": False,
        "execution_allowed": False,
        "autonomy_allowed": False,
        "blocked": True,
        "blockers": (
            ["watchdog_live_attempt_blocked"]
            if attempted_live
            else ["step_budget_and_watchdog_preview_only"]
        ),
    }


def preview_live_rollback_and_shutdown(request: dict[str, Any]) -> dict[str, Any]:
    rollback = _as_mapping(_as_mapping(request).get("live_rollback_and_shutdown"))
    attempted_live = (
        rollback.get("rollback_live") is True
        or rollback.get("shutdown_live") is True
    )

    return {
        "preview": "live_rollback_and_controlled_shutdown",
        "preview_only": True,
        "rollback_candidate": True,
        "shutdown_candidate": True,
        "rollback_live": False,
        "shutdown_live": False,
        "blocked": True,
        "blockers": (
            ["rollback_shutdown_live_attempt_blocked"]
            if attempted_live
            else ["rollback_and_shutdown_preview_only"]
        ),
    }


def validate_limited_active_runtime_opening_gate_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    commit_gate = _review_commit_gate_evidence(record)
    container = preview_runtime_session_container(record)
    lease = preview_limited_execution_lease(record)
    scope = preview_capability_scope(record)
    watchdog = preview_step_budget_and_watchdog_binding(record)
    rollback = preview_live_rollback_and_shutdown(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if commit_gate["blocked"]:
        problems.append("commit_gate_evidence_binding_blocked")
    if record.get("opening_scope") != "limited_runtime_opening_gate_review_only":
        problems.append("opening_scope_not_review_only")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    if container["blockers"] == ["runtime_session_container_create_attempt_blocked"]:
        problems.append("runtime_session_container_create_attempt")
    if lease["blockers"] == ["limited_execution_lease_activation_attempt_blocked"]:
        problems.append("limited_execution_lease_activation_attempt")
    if scope["blockers"] == ["capability_scope_commit_attempt_blocked"]:
        problems.append("capability_scope_commit_attempt")
    if watchdog["blockers"] == ["watchdog_live_attempt_blocked"]:
        problems.append("watchdog_live_attempt")
    if rollback["blockers"] == ["rollback_shutdown_live_attempt_blocked"]:
        problems.append("rollback_shutdown_live_attempt")

    return {
        "schema": LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA,
        "valid": not problems,
        "runtime_opening_gate_id": record.get("runtime_opening_gate_id"),
        "commit_gate_id": record.get("commit_gate_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_limited_runtime_opening_gate_review"
        if not problems
        else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "commit_gate_evidence_review": commit_gate,
        "runtime_session_container": container,
        "limited_execution_lease": lease,
        "capability_scope": scope,
        "step_budget_and_watchdog": watchdog,
        "live_rollback_and_shutdown": rollback,
        "runtime_open_allowed": False,
        "limited_runtime_session_created": False,
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "watchdog_live": False,
        "rollback_live": False,
        "shutdown_live": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
    }


def build_limited_active_runtime_opening_gate_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_limited_active_runtime_opening_gate_request(request)

    return {
        "audit_schema": LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA + ".audit",
        "decision": "reserved_no_limited_active_runtime_opening",
        "runtime_opening_gate_id": validation.get("runtime_opening_gate_id"),
        "commit_gate_id": validation.get("commit_gate_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "commit_gate_evidence_review": validation["commit_gate_evidence_review"],
        "runtime_session_container": validation["runtime_session_container"],
        "limited_execution_lease": validation["limited_execution_lease"],
        "capability_scope": validation["capability_scope"],
        "step_budget_and_watchdog": validation["step_budget_and_watchdog"],
        "live_rollback_and_shutdown": validation["live_rollback_and_shutdown"],
        "runtime_open_happened": False,
        "limited_runtime_session_created": False,
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "watchdog_live": False,
        "rollback_live": False,
        "shutdown_live": False,
        "activation_happened": False,
        "runtime_open_allowed": False,
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


def build_limited_active_runtime_opening_gate_no_go_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_limited_active_runtime_opening_gate_audit_record(request)

    return {
        "seal": "limited_active_runtime_opening_gate_no_go",
        "schema": LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA,
        "closed": True,
        "final_decision": "NO_GO_FOR_REAL_RUNTIME_OPENING_GO_FOR_REVIEW_ONLY",
        "next_package": 1209,
        "runtime_opening_gate_id": audit.get("runtime_opening_gate_id"),
        "commit_gate_id": audit.get("commit_gate_id"),
        "candidate_id": audit.get("candidate_id"),
        "audit_decision": audit["decision"],
        "runtime_open_happened": False,
        "runtime_open_allowed": False,
        "limited_runtime_session_created": False,
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "watchdog_live": False,
        "rollback_live": False,
        "shutdown_live": False,
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
    "LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA",
    "REQUIRED_OPENING_GATE_FIELDS",
    "OPENING_GATE_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_limited_active_runtime_opening_gate_request",
    "validate_limited_active_runtime_opening_gate_request",
    "preview_runtime_session_container",
    "preview_limited_execution_lease",
    "preview_capability_scope",
    "preview_step_budget_and_watchdog_binding",
    "preview_live_rollback_and_shutdown",
    "build_limited_active_runtime_opening_gate_audit_record",
    "build_limited_active_runtime_opening_gate_no_go_seal",
]
