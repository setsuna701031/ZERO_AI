from __future__ import annotations

from core.runtime.runtime_limited_active_runtime_opening_gate import (
    LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA,
    OPENING_GATE_BOUNDARY_LOCKS,
    REQUIRED_OPENING_GATE_FIELDS,
    build_limited_active_runtime_opening_gate_audit_record,
    build_limited_active_runtime_opening_gate_no_go_seal,
    build_limited_active_runtime_opening_gate_request,
    preview_capability_scope,
    preview_limited_execution_lease,
    preview_live_rollback_and_shutdown,
    preview_runtime_session_container,
    preview_step_budget_and_watchdog_binding,
    validate_limited_active_runtime_opening_gate_request,
)


def _request():
    return build_limited_active_runtime_opening_gate_request(
        runtime_opening_gate_id="opening-1201",
        commit_gate_id="commit-gate-1201",
        candidate_id="candidate-1201",
        activation_attempt_id="attempt-1201",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1201_contract_schema_and_required_fields_are_present():
    request = _request()

    assert request["schema"] == LIMITED_ACTIVE_RUNTIME_OPENING_GATE_SCHEMA
    for field in REQUIRED_OPENING_GATE_FIELDS:
        assert field in request
    assert request["opening_scope"] == "limited_runtime_opening_gate_review_only"


def test_1201_missing_required_field_is_rejected():
    request = _request()
    request.pop("runtime_opening_gate_id")

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert result["valid"] is False
    assert "missing_required_fields" in result["problems"]
    assert "runtime_opening_gate_id" in result["missing_required_fields"]


def test_1201_all_hard_boundary_flags_are_false():
    request = _request()

    for key, expected in OPENING_GATE_BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected
    assert request["non_mainline_issue_reporting_required"] is True


def test_1201_commit_gate_unlock_evidence_blocks_opening():
    request = _request()
    request["commit_gate_evidence"]["limited_runtime_open_allowed"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert result["valid"] is False
    assert "commit_gate_evidence_binding_blocked" in result["problems"]
    assert "commit_gate_limited_runtime_open_allowed_unlock_attempt" in result[
        "commit_gate_evidence_review"
    ]["problems"]


def test_1202_runtime_session_container_is_preview_only():
    container = preview_runtime_session_container(_request())

    assert container["preview_only"] is True
    assert container["container_candidate"] is True
    assert container["limited_runtime_session_created"] is False
    assert container["runtime_open_allowed"] is False


def test_1202_runtime_session_create_attempt_is_blocked():
    request = _request()
    request["runtime_session_container"]["limited_runtime_session_created"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert "runtime_session_container_create_attempt" in result["problems"]
    assert result["limited_runtime_session_created"] is False
    assert result["runtime_open_allowed"] is False


def test_1203_limited_execution_lease_is_preview_only():
    lease = preview_limited_execution_lease(_request())

    assert lease["preview_only"] is True
    assert lease["lease_candidate"] is True
    assert lease["execution_lease_active"] is False
    assert lease["execution_allowed"] is False
    assert lease["autonomy_allowed"] is False


def test_1203_execution_lease_activation_attempt_is_blocked():
    request = _request()
    request["limited_execution_lease"]["execution_lease_active"] = True
    request["limited_execution_lease"]["execution_allowed"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert "limited_execution_lease_activation_attempt" in result["problems"]
    assert result["execution_lease_active"] is False
    assert result["execution_allowed"] is False


def test_1204_capability_scope_is_preview_only():
    scope = preview_capability_scope(_request())

    assert scope["preview_only"] is True
    assert scope["scope_candidate"] is True
    assert scope["capability_scope_committed"] is False
    assert scope["execution_allowed"] is False
    assert scope["mutation_allowed"] is False
    assert scope["external_io_allowed"] is False


def test_1204_capability_scope_commit_attempt_is_blocked():
    request = _request()
    request["capability_scope"]["capability_scope_committed"] = True
    request["capability_scope"]["external_io_allowed"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert "capability_scope_commit_attempt" in result["problems"]
    assert result["capability_scope_committed"] is False
    assert result["external_io_allowed"] is False


def test_1205_step_budget_and_watchdog_binding_is_preview_only():
    watchdog = preview_step_budget_and_watchdog_binding(_request())

    assert watchdog["preview_only"] is True
    assert watchdog["step_budget_candidate"] is True
    assert watchdog["watchdog_candidate"] is True
    assert watchdog["watchdog_live"] is False
    assert watchdog["execution_allowed"] is False
    assert watchdog["autonomy_allowed"] is False


def test_1205_watchdog_live_attempt_is_blocked():
    request = _request()
    request["step_budget_and_watchdog"]["watchdog_live"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert "watchdog_live_attempt" in result["problems"]
    assert result["watchdog_live"] is False


def test_1206_live_rollback_and_shutdown_are_preview_only():
    rollback = preview_live_rollback_and_shutdown(_request())

    assert rollback["preview_only"] is True
    assert rollback["rollback_candidate"] is True
    assert rollback["shutdown_candidate"] is True
    assert rollback["rollback_live"] is False
    assert rollback["shutdown_live"] is False


def test_1206_rollback_or_shutdown_live_attempt_is_blocked():
    request = _request()
    request["live_rollback_and_shutdown"]["rollback_live"] = True
    request["live_rollback_and_shutdown"]["shutdown_live"] = True

    result = validate_limited_active_runtime_opening_gate_request(request)

    assert "rollback_shutdown_live_attempt" in result["problems"]
    assert result["rollback_live"] is False
    assert result["shutdown_live"] is False


def test_1207_audit_contains_runtime_opening_evidence():
    audit = build_limited_active_runtime_opening_gate_audit_record(_request())

    assert audit["decision"] == "reserved_no_limited_active_runtime_opening"
    assert audit["commit_gate_evidence_review"]["review"] == "commit_gate_evidence_binding"
    assert audit["runtime_session_container"]["preview"] == "runtime_session_container"
    assert audit["limited_execution_lease"]["preview"] == "limited_execution_lease"
    assert audit["capability_scope"]["preview"] == "capability_scope"
    assert audit["step_budget_and_watchdog"]["preview"] == "step_budget_and_watchdog_binding"
    assert audit["live_rollback_and_shutdown"]["preview"] == "live_rollback_and_controlled_shutdown"


def test_1207_audit_proves_no_runtime_opening_or_live_surface():
    audit = build_limited_active_runtime_opening_gate_audit_record(_request())

    assert audit["runtime_open_happened"] is False
    assert audit["limited_runtime_session_created"] is False
    assert audit["execution_lease_active"] is False
    assert audit["capability_scope_committed"] is False
    assert audit["watchdog_live"] is False
    assert audit["rollback_live"] is False
    assert audit["shutdown_live"] is False


def test_1207_audit_represents_non_mainline_issues():
    request = _request()
    request["boundary_locks"]["network_io_allowed"] = True

    audit = build_limited_active_runtime_opening_gate_audit_record(request)

    assert audit["non_mainline_issue_reporting_required"] is True
    assert "boundary_unlock_attempt" in audit["non_mainline_issues"]
    assert audit["external_io_allowed"] is False


def test_1208_no_go_seal_closes_runtime_opening_gate_review():
    seal = build_limited_active_runtime_opening_gate_no_go_seal(_request())

    assert seal["closed"] is True
    assert seal["final_decision"] == "NO_GO_FOR_REAL_RUNTIME_OPENING_GO_FOR_REVIEW_ONLY"
    assert seal["next_package"] == 1209
    assert seal["audit_decision"] == "reserved_no_limited_active_runtime_opening"


def test_1208_no_go_seal_keeps_all_surfaces_locked():
    seal = build_limited_active_runtime_opening_gate_no_go_seal(_request())

    assert seal["runtime_open_happened"] is False
    assert seal["runtime_open_allowed"] is False
    assert seal["limited_runtime_session_created"] is False
    assert seal["execution_lease_active"] is False
    assert seal["capability_scope_committed"] is False
    assert seal["watchdog_live"] is False
    assert seal["rollback_live"] is False
    assert seal["shutdown_live"] is False
    assert seal["activation_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["execution_allowed"] is False
    assert seal["mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False
    assert seal["all_execution_surfaces_locked"] is True
