from __future__ import annotations

from core.runtime.runtime_controlled_active_limited_mode_admission_dry_run import (
    BOUNDARY_LOCKS,
    CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA,
    REQUIRED_ADMISSION_REQUEST_FIELDS,
    REQUIRED_BLOCKERS,
    build_controlled_active_limited_mode_admission_dry_run_audit_record,
    build_controlled_active_limited_mode_admission_dry_run_no_go_seal,
    build_controlled_active_limited_mode_admission_dry_run_request,
    decide_controlled_active_limited_mode_admission_dry_run,
    preview_operator_approval,
    preview_runtime_ownership_verification,
    validate_controlled_active_limited_mode_admission_dry_run_request,
)


def _request():
    return build_controlled_active_limited_mode_admission_dry_run_request(
        request_id="admission-1153",
        candidate_id="candidate-1153",
        activation_attempt_id="attempt-1153",
        operator_id="operator-zero",
    )


def test_1153_contract_schema_and_required_fields_are_present():
    request = _request()

    assert request["schema"] == CONTROLLED_ACTIVE_LIMITED_MODE_ADMISSION_DRY_RUN_SCHEMA
    for field in REQUIRED_ADMISSION_REQUEST_FIELDS:
        assert field in request
    assert request["admission_scope"] == "dry_run_only"


def test_1153_missing_required_field_is_rejected():
    request = _request()
    request.pop("request_id")

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "request_id" in result["missing_required_fields"]


def test_1153_missing_required_blocker_is_rejected():
    request = _request()
    request["blockers"] = [
        blocker for blocker in REQUIRED_BLOCKERS if blocker != "admission_commit_locked"
    ]

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "missing_required_blockers" in result["problems"]
    assert "admission_commit_locked" in result["missing_required_blockers"]


def test_1154_admission_request_is_dry_run_only():
    request = _request()

    assert request["requested_mode"] == "controlled_active_limited"
    assert request["source_layer"] == "controlled_active_limited_mode_state_dry_run"
    assert request["admission_scope"] == "dry_run_only"


def test_1154_admission_scope_cannot_be_enabled():
    request = _request()
    request["admission_scope"] = "enabled"

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "admission_scope_not_dry_run_only" in result["problems"]


def test_1154_state_dry_run_review_must_be_sealed():
    request = _request()
    request["state_dry_run_review"]["review_sealed"] = False

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "state_dry_run_review_not_sealed" in result["problems"]


def test_1155_runtime_ownership_preview_does_not_verify_owner():
    result = preview_runtime_ownership_verification(_request())

    assert result["preview_only"] is True
    assert result["runtime_owner_verified"] is False
    assert result["ownership_commit_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1155_runtime_ownership_commit_attempt_is_blocked():
    request = _request()
    request["ownership_verification"]["runtime_owner_verified"] = True
    request["ownership_verification"]["ownership_commit_allowed"] = True

    result = preview_runtime_ownership_verification(request)

    assert "runtime_ownership_commit_blocked" in result["blockers"]
    assert result["runtime_owner_verified"] is False
    assert result["ownership_commit_allowed"] is False


def test_1155_validation_rejects_runtime_owner_verified_in_dry_run():
    request = _request()
    request["ownership_verification"]["runtime_owner_verified"] = True

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "runtime_owner_verified_in_dry_run" in result["problems"]


def test_1156_operator_approval_preview_does_not_approve():
    result = preview_operator_approval(_request())

    assert result["preview_only"] is True
    assert result["operator_approved"] is False
    assert result["approval_commit_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1156_operator_approval_commit_attempt_is_blocked():
    request = _request()
    request["operator_approval"]["operator_approved"] = True
    request["operator_approval"]["approval_commit_allowed"] = True

    result = preview_operator_approval(request)

    assert "operator_approval_commit_blocked" in result["blockers"]
    assert result["operator_approved"] is False
    assert result["approval_commit_allowed"] is False


def test_1156_validation_rejects_operator_approved_in_dry_run():
    request = _request()
    request["operator_approval"]["operator_approved"] = True

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "operator_approved_in_dry_run" in result["problems"]


def test_1157_admission_decision_is_no_go():
    decision = decide_controlled_active_limited_mode_admission_dry_run(_request())

    assert decision["decision"] == "NO_GO_ADMISSION_DRY_RUN_ONLY"
    assert decision["admission_allowed"] is False
    assert decision["admission_commit_allowed"] is False


def test_1157_admission_decision_keeps_runtime_locked():
    decision = decide_controlled_active_limited_mode_admission_dry_run(_request())

    assert decision["runtime_mode_transition_allowed"] is False
    assert decision["controlled_active_mode_enabled"] is False
    assert decision["runtime_state_mutated"] is False
    assert decision["real_mutation_allowed"] is False
    assert decision["external_io_allowed"] is False


def test_1157_admission_decision_contains_required_blocker():
    decision = decide_controlled_active_limited_mode_admission_dry_run(_request())

    assert "admission_commit_locked" in decision["blockers"]


def test_1158_all_boundary_locks_are_false_by_default():
    request = _request()

    for key, expected in BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected


def test_1158_boundary_unlock_attempt_is_reported():
    request = _request()
    request["boundary_locks"]["network_io_allowed"] = True
    request["boundary_locks"]["admission_commit_allowed"] = True

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "boundary_unlock_attempt" in result["problems"]
    assert "network_io_allowed" in result["unlock_attempts"]
    assert "admission_commit_allowed" in result["unlock_attempts"]


def test_1158_state_mutation_attempt_is_rejected():
    request = _request()
    request["state_dry_run_review"]["runtime_state_mutated"] = True

    result = validate_controlled_active_limited_mode_admission_dry_run_request(request)

    assert result["valid"] is False
    assert "runtime_state_mutated" in result["problems"]


def test_1159_audit_record_uses_reserved_no_admission_decision():
    audit = build_controlled_active_limited_mode_admission_dry_run_audit_record(_request())

    assert audit["decision"] == "reserved_no_controlled_active_limited_mode_admission"
    assert audit["admission_allowed"] is False
    assert audit["admission_commit_allowed"] is False


def test_1159_audit_contains_admission_decision_payload():
    audit = build_controlled_active_limited_mode_admission_dry_run_audit_record(_request())

    assert audit["admission_decision"]["decision"] == "NO_GO_ADMISSION_DRY_RUN_ONLY"
    assert audit["admission_decision"]["ownership_preview"]["preview"] == "runtime_ownership_verification"
    assert audit["admission_decision"]["operator_approval_preview"]["preview"] == "operator_approval"


def test_1159_audit_preserves_no_effect_boundary():
    audit = build_controlled_active_limited_mode_admission_dry_run_audit_record(_request())

    assert audit["runtime_mode_transition_allowed"] is False
    assert audit["controlled_active_mode_enabled"] is False
    assert audit["runtime_state_mutated"] is False
    assert audit["real_mutation_allowed"] is False
    assert audit["external_io_allowed"] is False


def test_1160_no_go_seal_closes_admission_dry_run_layer():
    seal = build_controlled_active_limited_mode_admission_dry_run_no_go_seal(_request())

    assert seal["closed"] is True
    assert (
        seal["final_decision"]
        == "NO_GO_FOR_REAL_ADMISSION_GO_FOR_DRY_RUN_REVIEW_ONLY"
    )
    assert seal["next_package"] == 1161


def test_1160_no_go_seal_keeps_all_execution_surfaces_locked():
    seal = build_controlled_active_limited_mode_admission_dry_run_no_go_seal(_request())

    assert seal["admission_allowed"] is False
    assert seal["admission_commit_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["controlled_active_mode_enabled"] is False
    assert seal["runtime_state_mutated"] is False
    assert seal["real_mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["unbounded_autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False


def test_1160_no_go_seal_preserves_non_mainline_reporting_rule():
    seal = build_controlled_active_limited_mode_admission_dry_run_no_go_seal(_request())

    assert seal["non_mainline_issue_reporting_required"] is True


def test_validation_accepts_default_request_without_enabling_admission():
    result = validate_controlled_active_limited_mode_admission_dry_run_request(_request())

    assert result["valid"] is True
    assert result["admission_commit_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False
    assert result["controlled_active_mode_enabled"] is False
    assert result["runtime_state_mutated"] is False


def test_audit_is_required_for_default_request():
    result = validate_controlled_active_limited_mode_admission_dry_run_request(_request())

    assert result["audit_required"] is True
