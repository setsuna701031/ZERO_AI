from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_SESSION_BIRTH_SCHEMA = "zero.runtime.session_birth.v1"

TEST_CONTROLLED_OPENING_GO_DECISION = "GO_TEST_CONTROLLED_LIMITED_SESSION_BIRTH_ONLY"

REQUIRED_SESSION_BIRTH_FIELDS = (
    "session_birth_id",
    "runtime_opening_gate_id",
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "executor_id",
    "opening_gate_evidence",
    "opening_input",
    "session_birth_plan",
    "heartbeat_status_projection",
    "audit_required",
)

SESSION_BIRTH_BOUNDARY_LOCKS = {
    "runtime_open_allowed": False,
    "limited_runtime_session_created": False,
    "execution_lease_active": False,
    "capability_scope_committed": False,
    "executor_start_allowed": False,
    "tool_call_allowed": False,
    "file_mutation_allowed": False,
    "io_allowed": False,
    "background_loop_allowed": False,
    "activation_allowed": False,
    "runtime_mode_transition_allowed": False,
    "execution_allowed": False,
    "mutation_allowed": False,
    "external_io_allowed": False,
    "autonomy_allowed": False,
    "self_start_allowed": False,
}

REQUIRED_BLOCKERS = (
    "opening_gate_evidence_required",
    "opening_gate_no_go_by_default",
    "explicit_test_controlled_go_required",
    "runtime_session_birth_planner_data_only",
    "runtime_session_inert_if_created",
    "execution_lease_locked",
    "capability_scope_locked",
    "executor_start_locked",
    "tool_call_locked",
    "file_mutation_locked",
    "io_locked",
    "background_loop_locked",
    "activation_locked",
    "runtime_mode_transition_locked",
    "execution_locked",
    "mutation_locked",
    "autonomy_locked",
    "self_start_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_SESSION_BIRTH_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in SESSION_BIRTH_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _runtime_session_id(session_birth_id: str) -> str:
    return f"limited-runtime-session::{session_birth_id}"


def build_runtime_session_birth_request(
    *,
    session_birth_id: str,
    runtime_opening_gate_id: str,
    candidate_id: str,
    activation_attempt_id: str,
    operator_id: str,
    executor_id: str,
    opening_gate_evidence: dict[str, Any] | None = None,
    opening_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_evidence = (
        deepcopy(opening_gate_evidence)
        if opening_gate_evidence is not None
        else {
            "present": True,
            "closed": True,
            "final_decision": "NO_GO_FOR_REAL_RUNTIME_OPENING_GO_FOR_REVIEW_ONLY",
            "runtime_open_allowed": False,
            "limited_runtime_session_created": False,
            "execution_lease_active": False,
            "capability_scope_committed": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "external_io_allowed": False,
            "autonomy_allowed": False,
            "self_start_allowed": False,
        }
    )
    controlled_input = (
        deepcopy(opening_input)
        if opening_input is not None
        else {
            "decision": "NO_GO",
            "explicit_test_controlled_opening": False,
            "runtime_open_allowed": False,
        }
    )

    return {
        "schema": RUNTIME_SESSION_BIRTH_SCHEMA,
        "session_birth_id": session_birth_id,
        "runtime_opening_gate_id": runtime_opening_gate_id,
        "candidate_id": candidate_id,
        "activation_attempt_id": activation_attempt_id,
        "operator_id": operator_id,
        "executor_id": executor_id,
        "birth_scope": "disabled_limited_runtime_session_birth",
        "opening_gate_evidence": gate_evidence,
        "opening_input": controlled_input,
        "session_birth_plan": {
            "planner": "runtime_session_birth",
            "data_only": True,
            "default_no_go": True,
            "session_birth_allowed": False,
        },
        "heartbeat_status_projection": {
            "projection_only": True,
            "heartbeat_live": False,
            "status": "not_born",
            "background_loop_allowed": False,
        },
        "boundary_locks": deepcopy(SESSION_BIRTH_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def evaluate_runtime_session_birth_opening(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    gate = _as_mapping(record.get("opening_gate_evidence"))
    opening = _as_mapping(record.get("opening_input"))
    problems: list[str] = []

    if gate.get("present") is not True:
        problems.append("opening_gate_evidence_missing")
    if gate.get("closed") is not True:
        problems.append("opening_gate_evidence_open")
    for key in (
        "limited_runtime_session_created",
        "execution_lease_active",
        "capability_scope_committed",
        "activation_allowed",
        "runtime_mode_transition_allowed",
        "execution_allowed",
        "mutation_allowed",
        "external_io_allowed",
        "autonomy_allowed",
        "self_start_allowed",
    ):
        if gate.get(key) is not False:
            problems.append(f"opening_gate_{key}_unlock_attempt")

    explicit_go = (
        opening.get("decision") == TEST_CONTROLLED_OPENING_GO_DECISION
        and opening.get("explicit_test_controlled_opening") is True
        and opening.get("runtime_open_allowed") is True
    )
    bypass_attempt = opening.get("runtime_open_allowed") is True and not explicit_go
    if bypass_attempt:
        problems.append("opening_gate_bypass_attempt")

    return {
        "review": "runtime_session_birth_opening_gate",
        "explicit_test_controlled_go": explicit_go,
        "opening_gate_bound": not problems,
        "opening_gate_default_no_go": not explicit_go,
        "runtime_session_birth_allowed": explicit_go and not problems,
        "blocked": bool(problems) or not explicit_go,
        "problems": problems,
        "runtime_open_allowed": bool(explicit_go and not problems),
        "limited_runtime_session_created": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def plan_runtime_session_birth(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    opening = evaluate_runtime_session_birth_opening(record)
    session_id = (
        _runtime_session_id(str(record.get("session_birth_id")))
        if opening["runtime_session_birth_allowed"]
        else None
    )

    return {
        "plan": "runtime_session_birth",
        "schema": RUNTIME_SESSION_BIRTH_SCHEMA,
        "data_only": True,
        "session_birth_id": record.get("session_birth_id"),
        "runtime_session_id": session_id,
        "session_birth_allowed": opening["runtime_session_birth_allowed"],
        "session_created": session_id is not None,
        "opening_gate_review": opening,
        "default_path_creates_session": False,
        "no_go_creates_session": False,
        "runtime_open_allowed": bool(session_id),
        "executor_start_allowed": False,
        "tool_call_allowed": False,
        "file_mutation_allowed": False,
        "io_allowed": False,
        "background_loop_allowed": False,
    }


def build_runtime_session_birth_result(request: dict[str, Any]) -> dict[str, Any]:
    plan = plan_runtime_session_birth(request)
    session_record = None
    if plan["session_created"]:
        session_record = {
            "runtime_session_id": plan["runtime_session_id"],
            "session_type": "limited",
            "status": "born_inert",
            "non_executing": True,
            "non_mutating": True,
            "lease_id": None,
            "execution_lease_active": False,
            "capabilities": [],
            "capability_scope_committed": False,
            "executor_started": False,
            "executor_start_allowed": False,
            "tool_call_allowed": False,
            "file_mutation_allowed": False,
            "io_allowed": False,
            "network_io_allowed": False,
            "background_loop_allowed": False,
            "heartbeat_live": False,
            "activation_allowed": False,
            "runtime_mode_transition_allowed": False,
            "execution_allowed": False,
            "mutation_allowed": False,
            "external_io_allowed": False,
            "autonomy_allowed": False,
            "self_start_allowed": False,
        }

    return {
        "result": "runtime_session_birth",
        "schema": RUNTIME_SESSION_BIRTH_SCHEMA,
        "session_created": plan["session_created"],
        "runtime_session_id": plan["runtime_session_id"],
        "session_record": session_record,
        "heartbeat_status_projection": build_runtime_session_heartbeat_status_projection(
            session_record
        ),
        "executor_started": False,
        "tool_call_performed": False,
        "file_mutation_performed": False,
        "io_performed": False,
        "background_loop_started": False,
    }


def build_runtime_session_heartbeat_status_projection(
    session_record: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "projection": "runtime_session_heartbeat_status",
        "projection_only": True,
        "runtime_session_id": (
            _as_mapping(session_record).get("runtime_session_id")
            if session_record is not None
            else None
        ),
        "status": "born_inert" if session_record is not None else "not_born",
        "heartbeat_live": False,
        "background_loop_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
    }


def validate_runtime_session_birth_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    opening = evaluate_runtime_session_birth_opening(record)
    plan = plan_runtime_session_birth(record)
    result = build_runtime_session_birth_result(record)

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if opening["problems"]:
        problems.append("opening_gate_blocked")
    if record.get("birth_scope") != "disabled_limited_runtime_session_birth":
        problems.append("birth_scope_invalid")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": RUNTIME_SESSION_BIRTH_SCHEMA,
        "valid": not problems,
        "session_birth_id": record.get("session_birth_id"),
        "runtime_opening_gate_id": record.get("runtime_opening_gate_id"),
        "candidate_id": record.get("candidate_id"),
        "status": "accepted_session_birth_request" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "opening_gate_review": opening,
        "session_birth_plan": plan,
        "session_birth_result": result,
        "runtime_session_id": result["runtime_session_id"],
        "session_created": result["session_created"],
        "limited_runtime_session_created": result["session_created"],
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "executor_start_allowed": False,
        "tool_call_allowed": False,
        "file_mutation_allowed": False,
        "io_allowed": False,
        "background_loop_allowed": False,
        "activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "external_io_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "audit_required": True,
    }


def build_runtime_session_birth_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_session_birth_request(request)

    return {
        "audit_schema": RUNTIME_SESSION_BIRTH_SCHEMA + ".audit",
        "decision": "reserved_limited_inert_runtime_session_birth_only",
        "session_birth_id": validation.get("session_birth_id"),
        "runtime_opening_gate_id": validation.get("runtime_opening_gate_id"),
        "candidate_id": validation.get("candidate_id"),
        "request_valid": validation["valid"],
        "opening_gate_review": validation["opening_gate_review"],
        "session_birth_plan": validation["session_birth_plan"],
        "session_birth_result": validation["session_birth_result"],
        "runtime_session_id": validation["runtime_session_id"],
        "session_created": validation["session_created"],
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "executor_started": False,
        "tool_call_performed": False,
        "file_mutation_performed": False,
        "io_performed": False,
        "background_loop_started": False,
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


def build_runtime_session_birth_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_session_birth_audit_record(request)

    return {
        "seal": "runtime_session_birth_bundle",
        "schema": RUNTIME_SESSION_BIRTH_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_INERT_LIMITED_SESSION_BIRTH_ONLY_WHEN_TEST_CONTROLLED_OPENING_GO",
        "next_package": 1217,
        "session_birth_id": audit.get("session_birth_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "session_created": audit["session_created"],
        "audit_decision": audit["decision"],
        "execution_lease_active": False,
        "capability_scope_committed": False,
        "executor_started": False,
        "tool_call_performed": False,
        "file_mutation_performed": False,
        "io_performed": False,
        "background_loop_started": False,
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
    "RUNTIME_SESSION_BIRTH_SCHEMA",
    "TEST_CONTROLLED_OPENING_GO_DECISION",
    "REQUIRED_SESSION_BIRTH_FIELDS",
    "SESSION_BIRTH_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_session_birth_request",
    "evaluate_runtime_session_birth_opening",
    "plan_runtime_session_birth",
    "build_runtime_session_birth_result",
    "build_runtime_session_heartbeat_status_projection",
    "validate_runtime_session_birth_request",
    "build_runtime_session_birth_audit_record",
    "build_runtime_session_birth_milestone_seal",
]
