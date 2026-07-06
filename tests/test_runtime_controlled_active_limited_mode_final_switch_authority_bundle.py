from __future__ import annotations

from core.runtime.runtime_controlled_active_limited_mode_final_switch_authority import (
    CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA,
    FINAL_SWITCH_BOUNDARY_LOCKS,
    REQUIRED_FINAL_SWITCH_AUTHORITY_FIELDS,
    build_controlled_active_limited_mode_final_switch_authority_audit_record,
    build_controlled_active_limited_mode_final_switch_authority_no_go_seal,
    build_controlled_active_limited_mode_final_switch_authority_request,
    preview_bounded_runtime_lease,
    preview_controlled_activation_transaction,
    preview_kill_switch_authority_live_readiness,
    preview_operator_confirmation_token,
    preview_rollback_authority_live_readiness,
    validate_controlled_active_limited_mode_final_switch_authority_request,
)


def _request():
    return build_controlled_active_limited_mode_final_switch_authority_request(
        switch_authority_id="switch-1177",
        readiness_id="readiness-1177",
        candidate_id="candidate-1177",
        activation_attempt_id="attempt-1177",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1177_contract_schema_and_required_fields_are_present():
    request = _request()

    assert (
        request["schema"]
        == CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_SWITCH_AUTHORITY_SCHEMA
    )
    for field in REQUIRED_FINAL_SWITCH_AUTHORITY_FIELDS:
        assert field in request
    assert request["authority_scope"] == "final_switch_authority_review_only"


def test_1177_missing_required_field_is_rejected():
    request = _request()
    request.pop("switch_authority_id")

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert result["valid"] is False
    assert "missing_required_fields" in result["problems"]
    assert "switch_authority_id" in result["missing_required_fields"]


def test_1177_all_hard_boundary_flags_are_false():
    request = _request()

    for key, expected in FINAL_SWITCH_BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected
    assert request["non_mainline_issue_reporting_required"] is True


def test_1178_operator_confirmation_token_is_preview_only():
    token = preview_operator_confirmation_token(_request())

    assert token["preview_only"] is True
    assert token["token_present"] is True
    assert token["token_verified"] is False
    assert token["token_commit_allowed"] is False


def test_1178_operator_confirmation_commit_attempt_is_blocked():
    request = _request()
    request["operator_confirmation_token"]["token_verified"] = True
    request["operator_confirmation_token"]["token_commit_allowed"] = True

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert result["valid"] is False
    assert "operator_confirmation_token_commit_attempt" in result["problems"]
    assert result["operator_confirmation_token"]["token_verified"] is False


def test_1179_rollback_authority_live_readiness_is_preview_only():
    rollback = preview_rollback_authority_live_readiness(_request())

    assert rollback["authority_required"] is True
    assert rollback["live_readiness_candidate"] is True
    assert rollback["authority_live"] is False
    assert rollback["authority_commit_allowed"] is False


def test_1179_rollback_authority_live_attempt_is_blocked():
    request = _request()
    request["rollback_authority"]["authority_live"] = True
    request["rollback_authority"]["authority_commit_allowed"] = True

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert "rollback_authority_live_attempt" in result["problems"]
    assert result["rollback_authority"]["authority_live"] is False


def test_1180_kill_switch_authority_live_readiness_is_preview_only():
    kill_switch = preview_kill_switch_authority_live_readiness(_request())

    assert kill_switch["authority_required"] is True
    assert kill_switch["live_readiness_candidate"] is True
    assert kill_switch["authority_live"] is False
    assert kill_switch["authority_commit_allowed"] is False


def test_1180_kill_switch_authority_live_attempt_is_blocked():
    request = _request()
    request["kill_switch_authority"]["authority_live"] = True
    request["kill_switch_authority"]["authority_commit_allowed"] = True

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert "kill_switch_authority_live_attempt" in result["problems"]
    assert result["kill_switch_authority"]["authority_live"] is False


def test_1181_bounded_runtime_lease_is_preview_only():
    lease = preview_bounded_runtime_lease(_request())

    assert lease["preview_only"] is True
    assert lease["lease_candidate_created"] is True
    assert lease["lease_active"] is False
    assert lease["lease_commit_allowed"] is False
    assert lease["unbounded_autonomy_allowed"] is False


def test_1181_bounded_runtime_lease_commit_attempt_is_blocked():
    request = _request()
    request["bounded_runtime_lease"]["lease_active"] = True
    request["bounded_runtime_lease"]["unbounded_autonomy_allowed"] = True

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert "bounded_runtime_lease_commit_attempt" in result["problems"]
    assert result["bounded_runtime_lease"]["lease_active"] is False
    assert result["autonomy_allowed"] is False


def test_1182_controlled_activation_transaction_is_preview_only():
    transaction = preview_controlled_activation_transaction(_request())

    assert transaction["transaction_candidate_created"] is True
    assert transaction["transaction_opened"] is False
    assert transaction["transaction_commit_allowed"] is False
    assert transaction["activation_allowed"] is False
    assert transaction["runtime_mode_transition_allowed"] is False
    assert transaction["execution_allowed"] is False
    assert transaction["mutation_allowed"] is False


def test_1182_controlled_activation_transaction_commit_attempt_is_blocked():
    request = _request()
    request["controlled_activation_transaction"]["transaction_opened"] = True
    request["controlled_activation_transaction"]["activation_allowed"] = True
    request["controlled_activation_transaction"]["execution_allowed"] = True

    result = validate_controlled_active_limited_mode_final_switch_authority_request(
        request
    )

    assert "controlled_activation_transaction_commit_attempt" in result["problems"]
    assert result["activation_allowed"] is False
    assert result["execution_allowed"] is False


def test_1183_audit_record_contains_final_switch_evidence_and_no_go():
    audit = build_controlled_active_limited_mode_final_switch_authority_audit_record(
        _request()
    )

    assert audit["decision"] == "reserved_no_controlled_active_limited_mode_final_switch"
    assert audit["operator_confirmation_token"]["preview"] == "operator_confirmation_token"
    assert audit["rollback_authority"]["preview"] == "rollback_authority_live_readiness"
    assert audit["kill_switch_authority"]["preview"] == "kill_switch_authority_live_readiness"
    assert audit["bounded_runtime_lease"]["preview"] == "bounded_runtime_lease"
    assert (
        audit["controlled_activation_transaction"]["preview"]
        == "controlled_activation_transaction"
    )


def test_1183_audit_proves_no_activation_or_final_switch_happened():
    audit = build_controlled_active_limited_mode_final_switch_authority_audit_record(
        _request()
    )

    assert audit["activation_happened"] is False
    assert audit["final_switch_happened"] is False
    assert audit["activation_allowed"] is False
    assert audit["final_switch_allowed"] is False
    assert audit["runtime_mode_transition_allowed"] is False


def test_1183_audit_represents_non_mainline_issues():
    request = _request()
    request["boundary_locks"]["external_io_allowed"] = True

    audit = build_controlled_active_limited_mode_final_switch_authority_audit_record(
        request
    )

    assert audit["non_mainline_issue_reporting_required"] is True
    assert "boundary_unlock_attempt" in audit["non_mainline_issues"]
    assert audit["external_io_allowed"] is False


def test_1184_no_go_seal_closes_final_switch_authority_review():
    seal = build_controlled_active_limited_mode_final_switch_authority_no_go_seal(
        _request()
    )

    assert seal["closed"] is True
    assert seal["final_decision"] == "NO_GO_FOR_REAL_FINAL_SWITCH_AUTHORITY_REVIEW_ONLY"
    assert seal["next_package"] == 1185
    assert seal["audit_decision"] == "reserved_no_controlled_active_limited_mode_final_switch"


def test_1184_no_go_seal_keeps_all_surfaces_locked():
    seal = build_controlled_active_limited_mode_final_switch_authority_no_go_seal(
        _request()
    )

    assert seal["activation_happened"] is False
    assert seal["final_switch_happened"] is False
    assert seal["activation_allowed"] is False
    assert seal["final_switch_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["execution_allowed"] is False
    assert seal["mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False
    assert seal["all_execution_surfaces_locked"] is True
