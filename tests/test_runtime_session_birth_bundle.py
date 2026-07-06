from __future__ import annotations

from core.runtime.runtime_session_birth import (
    RUNTIME_SESSION_BIRTH_SCHEMA,
    SESSION_BIRTH_BOUNDARY_LOCKS,
    TEST_CONTROLLED_OPENING_GO_DECISION,
    build_runtime_session_birth_audit_record,
    build_runtime_session_birth_milestone_seal,
    build_runtime_session_birth_request,
    build_runtime_session_birth_result,
    plan_runtime_session_birth,
    validate_runtime_session_birth_request,
)


def _request(**overrides):
    base = {
        "session_birth_id": "birth-1209",
        "runtime_opening_gate_id": "opening-1209",
        "candidate_id": "candidate-1209",
        "activation_attempt_id": "attempt-1209",
        "operator_id": "operator-zero",
        "executor_id": "executor-zero",
    }
    base.update(overrides)
    return build_runtime_session_birth_request(**base)


def _go_request():
    return _request(
        opening_input={
            "decision": TEST_CONTROLLED_OPENING_GO_DECISION,
            "explicit_test_controlled_opening": True,
            "runtime_open_allowed": True,
        }
    )


def test_1209_contract_schema_and_default_no_go_boundary():
    request = _request()

    assert request["schema"] == RUNTIME_SESSION_BIRTH_SCHEMA
    assert request["birth_scope"] == "disabled_limited_runtime_session_birth"
    for key, expected in SESSION_BIRTH_BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected
    assert request["non_mainline_issue_reporting_required"] is True


def test_1209_default_path_creates_no_session():
    result = build_runtime_session_birth_result(_request())

    assert result["session_created"] is False
    assert result["runtime_session_id"] is None
    assert result["session_record"] is None
    assert result["heartbeat_status_projection"]["status"] == "not_born"


def test_1210_no_go_creates_no_session():
    request = _request(
        opening_input={
            "decision": "NO_GO",
            "explicit_test_controlled_opening": False,
            "runtime_open_allowed": False,
        }
    )

    plan = plan_runtime_session_birth(request)

    assert plan["session_created"] is False
    assert plan["runtime_session_id"] is None
    assert plan["opening_gate_review"]["opening_gate_default_no_go"] is True


def test_1211_go_creates_limited_session_record_only():
    result = build_runtime_session_birth_result(_go_request())

    assert result["session_created"] is True
    assert result["runtime_session_id"] == "limited-runtime-session::birth-1209"
    assert result["session_record"]["session_type"] == "limited"
    assert result["session_record"]["status"] == "born_inert"
    assert result["session_record"]["non_executing"] is True
    assert result["session_record"]["non_mutating"] is True


def test_1212_created_session_has_no_lease():
    session = build_runtime_session_birth_result(_go_request())["session_record"]

    assert session["lease_id"] is None
    assert session["execution_lease_active"] is False


def test_1213_created_session_has_no_capabilities():
    session = build_runtime_session_birth_result(_go_request())["session_record"]

    assert session["capabilities"] == []
    assert session["capability_scope_committed"] is False


def test_1214_created_session_cannot_execute():
    session = build_runtime_session_birth_result(_go_request())["session_record"]

    assert session["executor_started"] is False
    assert session["executor_start_allowed"] is False
    assert session["execution_allowed"] is False
    assert session["tool_call_allowed"] is False


def test_1214_created_session_cannot_mutate_or_io():
    session = build_runtime_session_birth_result(_go_request())["session_record"]

    assert session["mutation_allowed"] is False
    assert session["file_mutation_allowed"] is False
    assert session["io_allowed"] is False
    assert session["network_io_allowed"] is False
    assert session["external_io_allowed"] is False


def test_1215_created_session_has_no_autonomy_or_background_loop():
    session = build_runtime_session_birth_result(_go_request())["session_record"]

    assert session["background_loop_allowed"] is False
    assert session["heartbeat_live"] is False
    assert session["autonomy_allowed"] is False
    assert session["self_start_allowed"] is False


def test_1215_heartbeat_status_projection_is_data_only():
    result = build_runtime_session_birth_result(_go_request())
    projection = result["heartbeat_status_projection"]

    assert projection["projection_only"] is True
    assert projection["runtime_session_id"] == "limited-runtime-session::birth-1209"
    assert projection["heartbeat_live"] is False
    assert projection["background_loop_allowed"] is False


def test_1216_opening_gate_cannot_be_bypassed():
    request = _request(
        opening_input={
            "decision": "GO_BUT_NOT_TEST_CONTROLLED",
            "explicit_test_controlled_opening": False,
            "runtime_open_allowed": True,
        }
    )

    validation = validate_runtime_session_birth_request(request)

    assert validation["session_created"] is False
    assert validation["runtime_session_id"] is None
    assert "opening_gate_blocked" in validation["problems"]
    assert "opening_gate_bypass_attempt" in validation["opening_gate_review"]["problems"]


def test_1216_missing_opening_gate_evidence_blocks_birth():
    request = _go_request()
    request["opening_gate_evidence"]["present"] = False

    validation = validate_runtime_session_birth_request(request)

    assert validation["session_created"] is False
    assert "opening_gate_blocked" in validation["problems"]
    assert "opening_gate_evidence_missing" in validation["opening_gate_review"]["problems"]


def test_1216_audit_and_seal_preserve_inert_boundaries():
    audit = build_runtime_session_birth_audit_record(_go_request())
    seal = build_runtime_session_birth_milestone_seal(_go_request())

    assert audit["decision"] == "reserved_limited_inert_runtime_session_birth_only"
    assert audit["session_created"] is True
    assert audit["execution_lease_active"] is False
    assert audit["capability_scope_committed"] is False
    assert audit["executor_started"] is False
    assert audit["tool_call_performed"] is False
    assert audit["file_mutation_performed"] is False
    assert audit["io_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1217
    assert seal["all_execution_surfaces_locked"] is True
