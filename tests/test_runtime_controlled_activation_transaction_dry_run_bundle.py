from __future__ import annotations

from core.runtime.runtime_controlled_activation_transaction_dry_run import (
    CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA,
    REQUIRED_TRANSACTION_DRY_RUN_FIELDS,
    TRANSACTION_BOUNDARY_LOCKS,
    bind_final_switch_authority_review,
    build_controlled_activation_transaction_dry_run_audit_record,
    build_controlled_activation_transaction_dry_run_no_go_seal,
    build_controlled_activation_transaction_dry_run_request,
    preview_controlled_activation_transaction_plan,
    preview_pre_commit_safety_check,
    preview_transaction_commit_boundary,
    preview_transaction_rollback_path,
    validate_controlled_activation_transaction_dry_run_request,
)


def _request():
    return build_controlled_activation_transaction_dry_run_request(
        transaction_dry_run_id="transaction-1185",
        switch_authority_id="switch-1185",
        readiness_id="readiness-1185",
        candidate_id="candidate-1185",
        activation_attempt_id="attempt-1185",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1185_contract_schema_and_required_fields_are_present():
    request = _request()

    assert request["schema"] == CONTROLLED_ACTIVATION_TRANSACTION_DRY_RUN_SCHEMA
    for field in REQUIRED_TRANSACTION_DRY_RUN_FIELDS:
        assert field in request
    assert request["transaction_scope"] == "transaction_dry_run_only"


def test_1185_missing_required_field_is_rejected():
    request = _request()
    request.pop("transaction_dry_run_id")

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert result["valid"] is False
    assert "missing_required_fields" in result["problems"]
    assert "transaction_dry_run_id" in result["missing_required_fields"]


def test_1185_all_hard_boundary_flags_are_false():
    request = _request()

    for key, expected in TRANSACTION_BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected
    assert request["non_mainline_issue_reporting_required"] is True


def test_1186_final_switch_authority_binding_accepts_closed_no_go_inputs():
    binding = bind_final_switch_authority_review(_request())

    assert binding["final_readiness_bound"] is True
    assert binding["final_switch_authority_bound"] is True
    assert binding["blocked"] is False
    assert binding["final_switch_allowed"] is False
    assert binding["activation_allowed"] is False


def test_1186_final_switch_authority_binding_blocks_unlock_attempts():
    request = _request()
    request["final_switch_authority_review"]["final_switch_allowed"] = True
    request["final_readiness_evidence"]["activation_allowed"] = True

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert result["valid"] is False
    assert "final_switch_authority_binding_blocked" in result["problems"]
    assert "final_switch_authority_final_switch_allowed_unlock_attempt" in result[
        "final_switch_authority_binding"
    ]["problems"]
    assert "final_readiness_activation_allowed_unlock_attempt" in result[
        "final_switch_authority_binding"
    ]["problems"]


def test_1187_transaction_plan_is_preview_only():
    plan = preview_controlled_activation_transaction_plan(_request())

    assert plan["preview_only"] is True
    assert plan["plan_created"] is True
    assert plan["transaction_allowed"] is False
    assert plan["activation_allowed"] is False
    assert plan["runtime_mode_transition_allowed"] is False
    assert plan["execution_allowed"] is False
    assert plan["mutation_allowed"] is False


def test_1187_transaction_plan_unlock_attempt_is_blocked():
    request = _request()
    request["transaction_plan"]["transaction_allowed"] = True
    request["transaction_plan"]["execution_allowed"] = True

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert "transaction_plan_unlock_attempt" in result["problems"]
    assert result["transaction_plan"]["transaction_allowed"] is False
    assert result["execution_allowed"] is False


def test_1188_pre_commit_safety_check_is_preview_only():
    safety = preview_pre_commit_safety_check(_request())

    assert safety["preview_only"] is True
    assert safety["safety_check_created"] is True
    assert safety["safety_pass_candidate"] is True
    assert safety["commit_allowed"] is False
    assert safety["unlock_detected"] is False


def test_1188_pre_commit_safety_unlock_attempt_is_blocked():
    request = _request()
    request["pre_commit_safety_check"]["commit_allowed"] = True

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert "pre_commit_safety_unlock_attempt" in result["problems"]
    assert result["pre_commit_safety_check"]["commit_allowed"] is False
    assert result["transaction_commit_allowed"] is False


def test_1189_commit_boundary_is_preview_only():
    boundary = preview_transaction_commit_boundary(_request())

    assert boundary["preview_only"] is True
    assert boundary["boundary_created"] is True
    assert boundary["transaction_commit_allowed"] is False
    assert boundary["activation_allowed"] is False
    assert boundary["runtime_mode_transition_allowed"] is False
    assert boundary["execution_allowed"] is False
    assert boundary["mutation_allowed"] is False


def test_1189_commit_boundary_attempt_is_blocked():
    request = _request()
    request["commit_boundary"]["transaction_commit_allowed"] = True
    request["commit_boundary"]["runtime_mode_transition_allowed"] = True

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert "transaction_commit_boundary_attempt" in result["problems"]
    assert result["transaction_commit_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False


def test_1190_rollback_path_is_preview_only():
    rollback = preview_transaction_rollback_path(_request())

    assert rollback["preview_only"] is True
    assert rollback["rollback_path_created"] is True
    assert rollback["rollback_live"] is False
    assert rollback["rollback_commit_allowed"] is False


def test_1190_rollback_live_attempt_is_blocked():
    request = _request()
    request["rollback_path"]["rollback_live"] = True
    request["rollback_path"]["rollback_commit_allowed"] = True

    result = validate_controlled_activation_transaction_dry_run_request(request)

    assert "rollback_path_live_attempt" in result["problems"]
    assert result["rollback_path"]["rollback_live"] is False


def test_1191_audit_contains_transaction_dry_run_evidence():
    audit = build_controlled_activation_transaction_dry_run_audit_record(_request())

    assert audit["decision"] == "reserved_no_controlled_activation_transaction_commit"
    assert audit["final_switch_authority_binding"]["binding"] == "final_switch_authority_review"
    assert audit["transaction_plan"]["preview"] == "controlled_activation_transaction_plan"
    assert audit["pre_commit_safety_check"]["preview"] == "pre_commit_safety_check"
    assert audit["commit_boundary"]["preview"] == "transaction_commit_boundary"
    assert audit["rollback_path"]["preview"] == "transaction_rollback_path"


def test_1191_audit_proves_no_transaction_or_activation_happened():
    audit = build_controlled_activation_transaction_dry_run_audit_record(_request())

    assert audit["transaction_happened"] is False
    assert audit["transaction_committed"] is False
    assert audit["activation_happened"] is False
    assert audit["final_switch_happened"] is False
    assert audit["transaction_allowed"] is False
    assert audit["activation_allowed"] is False


def test_1191_audit_represents_non_mainline_issues():
    request = _request()
    request["boundary_locks"]["network_io_allowed"] = True

    audit = build_controlled_activation_transaction_dry_run_audit_record(request)

    assert audit["non_mainline_issue_reporting_required"] is True
    assert "boundary_unlock_attempt" in audit["non_mainline_issues"]
    assert audit["external_io_allowed"] is False


def test_1192_no_go_seal_closes_transaction_dry_run():
    seal = build_controlled_activation_transaction_dry_run_no_go_seal(_request())

    assert seal["closed"] is True
    assert (
        seal["final_decision"]
        == "NO_GO_FOR_REAL_TRANSACTION_GO_FOR_TRANSACTION_DRY_RUN_ONLY"
    )
    assert seal["next_package"] == 1193
    assert seal["audit_decision"] == "reserved_no_controlled_activation_transaction_commit"


def test_1192_no_go_seal_keeps_all_surfaces_locked():
    seal = build_controlled_activation_transaction_dry_run_no_go_seal(_request())

    assert seal["transaction_happened"] is False
    assert seal["transaction_committed"] is False
    assert seal["activation_happened"] is False
    assert seal["final_switch_happened"] is False
    assert seal["transaction_allowed"] is False
    assert seal["transaction_commit_allowed"] is False
    assert seal["activation_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["execution_allowed"] is False
    assert seal["mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False
    assert seal["all_execution_surfaces_locked"] is True
