from __future__ import annotations

from core.runtime.runtime_controlled_active_limited_mode_execution_dry_run import (
    BOUNDARY_LOCKS,
    CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA,
    REQUIRED_BLOCKERS,
    REQUIRED_EXECUTION_ADMISSION_FIELDS,
    build_controlled_active_limited_mode_execution_dry_run_admission,
    build_controlled_active_limited_mode_execution_dry_run_audit_record,
    build_controlled_active_limited_mode_execution_dry_run_milestone_seal,
    decide_controlled_active_limited_mode_execution_dry_run,
    preview_execution_lifecycle,
    preview_execution_result,
    preview_execution_session,
    preview_executor_ownership,
    validate_controlled_active_limited_mode_execution_dry_run_admission,
)


def _admission():
    return build_controlled_active_limited_mode_execution_dry_run_admission(
        execution_admission_id="execution-1161",
        admission_request_id="admission-1161",
        candidate_id="candidate-1161",
        activation_attempt_id="attempt-1161",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1161_contract_schema_and_required_fields_are_present():
    admission = _admission()

    assert admission["schema"] == CONTROLLED_ACTIVE_LIMITED_MODE_EXECUTION_DRY_RUN_SCHEMA
    for field in REQUIRED_EXECUTION_ADMISSION_FIELDS:
        assert field in admission
    assert admission["execution_scope"] == "dry_run_only"


def test_1161_missing_required_field_is_rejected():
    admission = _admission()
    admission.pop("execution_admission_id")

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "execution_admission_id" in result["missing_required_fields"]


def test_1161_missing_required_blocker_is_rejected():
    admission = _admission()
    admission["blockers"] = [
        blocker for blocker in REQUIRED_BLOCKERS if blocker != "execution_start_locked"
    ]

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "missing_required_blockers" in result["problems"]
    assert "execution_start_locked" in result["missing_required_blockers"]


def test_1162_execution_admission_binds_admission_no_go_decision():
    admission = _admission()

    assert admission["admission_decision"]["expected_decision"] == "NO_GO_ADMISSION_DRY_RUN_ONLY"
    assert admission["admission_decision"]["admission_allowed"] is False
    assert admission["admission_decision"]["admission_commit_allowed"] is False


def test_1162_admission_allowed_is_rejected():
    admission = _admission()
    admission["admission_decision"]["admission_allowed"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "admission_allowed" in result["problems"]


def test_1162_execution_scope_cannot_be_enabled():
    admission = _admission()
    admission["execution_scope"] = "enabled"

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "execution_scope_not_dry_run_only" in result["problems"]


def test_1163_executor_ownership_preview_does_not_verify_owner():
    result = preview_executor_ownership(_admission())

    assert result["preview_only"] is True
    assert result["executor_owner_verified"] is False
    assert result["executor_ownership_commit_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1163_executor_ownership_commit_attempt_is_blocked():
    admission = _admission()
    admission["executor_ownership"]["executor_owner_verified"] = True
    admission["executor_ownership"]["executor_ownership_commit_allowed"] = True

    result = preview_executor_ownership(admission)

    assert "executor_ownership_commit_blocked" in result["blockers"]
    assert result["executor_owner_verified"] is False
    assert result["executor_ownership_commit_allowed"] is False


def test_1163_validation_rejects_executor_owner_verified_in_dry_run():
    admission = _admission()
    admission["executor_ownership"]["executor_owner_verified"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "executor_owner_verified_in_dry_run" in result["problems"]


def test_1164_execution_session_preview_does_not_open_session():
    result = preview_execution_session(_admission())

    assert result["preview_only"] is True
    assert result["session_opened"] is False
    assert result["session_commit_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1164_execution_session_open_attempt_is_blocked():
    admission = _admission()
    admission["execution_session"]["session_opened"] = True
    admission["execution_session"]["session_commit_allowed"] = True

    result = preview_execution_session(admission)

    assert "execution_session_open_blocked" in result["blockers"]
    assert result["session_opened"] is False
    assert result["session_commit_allowed"] is False


def test_1164_validation_rejects_opened_execution_session():
    admission = _admission()
    admission["execution_session"]["session_opened"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "execution_session_opened" in result["problems"]


def test_1165_execution_lifecycle_preview_does_not_start():
    result = preview_execution_lifecycle(_admission())

    assert result["preview_only"] is True
    assert result["start_allowed"] is False
    assert result["step_execution_allowed"] is False
    assert result["completion_allowed"] is False


def test_1165_execution_lifecycle_start_attempt_is_blocked():
    admission = _admission()
    admission["execution_lifecycle"]["start_allowed"] = True
    admission["execution_lifecycle"]["step_execution_allowed"] = True

    result = preview_execution_lifecycle(admission)

    assert "execution_lifecycle_start_blocked" in result["blockers"]
    assert result["start_allowed"] is False
    assert result["step_execution_allowed"] is False


def test_1165_validation_rejects_step_execution_allowed():
    admission = _admission()
    admission["execution_lifecycle"]["step_execution_allowed"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "step_execution_allowed" in result["problems"]


def test_1166_execution_result_preview_does_not_commit_result():
    result = preview_execution_result(_admission())

    assert result["preview_only"] is True
    assert result["result_committed"] is False
    assert result["runtime_state_mutated"] is False


def test_1166_execution_result_commit_attempt_is_blocked():
    admission = _admission()
    admission["result_preview"]["result_committed"] = True
    admission["result_preview"]["runtime_state_mutated"] = True

    result = preview_execution_result(admission)

    assert "execution_result_commit_blocked" in result["blockers"]
    assert result["result_committed"] is False
    assert result["runtime_state_mutated"] is False


def test_1166_validation_rejects_result_committed():
    admission = _admission()
    admission["result_preview"]["result_committed"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "result_committed" in result["problems"]


def test_1167_execution_decision_is_no_go():
    decision = decide_controlled_active_limited_mode_execution_dry_run(_admission())

    assert decision["decision"] == "NO_GO_EXECUTION_DRY_RUN_ONLY"
    assert decision["execution_admission_allowed"] is False
    assert decision["execution_start_allowed"] is False
    assert decision["execution_commit_allowed"] is False


def test_1167_execution_decision_keeps_runtime_locked():
    decision = decide_controlled_active_limited_mode_execution_dry_run(_admission())

    assert decision["runtime_mode_transition_allowed"] is False
    assert decision["controlled_active_mode_enabled"] is False
    assert decision["runtime_state_mutated"] is False
    assert decision["real_mutation_allowed"] is False
    assert decision["external_io_allowed"] is False


def test_1167_all_boundary_locks_are_false_by_default():
    admission = _admission()

    for key, expected in BOUNDARY_LOCKS.items():
        assert admission["boundary_locks"][key] is expected


def test_1167_boundary_unlock_attempt_is_reported():
    admission = _admission()
    admission["boundary_locks"]["execution_start_allowed"] = True
    admission["boundary_locks"]["network_io_allowed"] = True

    result = validate_controlled_active_limited_mode_execution_dry_run_admission(admission)

    assert result["valid"] is False
    assert "boundary_unlock_attempt" in result["problems"]
    assert "execution_start_allowed" in result["unlock_attempts"]
    assert "network_io_allowed" in result["unlock_attempts"]


def test_1168_audit_record_uses_reserved_no_execution_decision():
    audit = build_controlled_active_limited_mode_execution_dry_run_audit_record(_admission())

    assert audit["decision"] == "reserved_no_controlled_active_limited_mode_execution"
    assert audit["execution_admission_allowed"] is False
    assert audit["execution_start_allowed"] is False
    assert audit["execution_commit_allowed"] is False


def test_1168_audit_contains_execution_preview_evidence():
    audit = build_controlled_active_limited_mode_execution_dry_run_audit_record(_admission())

    decision = audit["execution_decision"]
    assert decision["executor_ownership_preview"]["preview"] == "executor_ownership"
    assert decision["execution_session_preview"]["preview"] == "execution_session"
    assert decision["execution_lifecycle_preview"]["preview"] == "execution_lifecycle"
    assert decision["execution_result_preview"]["preview"] == "execution_result"


def test_1168_milestone_seal_closes_execution_dry_run_layer():
    seal = build_controlled_active_limited_mode_execution_dry_run_milestone_seal(_admission())

    assert seal["closed"] is True
    assert seal["final_decision"] == "NO_GO_FOR_REAL_EXECUTION_GO_FOR_DRY_RUN_REVIEW_ONLY"
    assert seal["next_package"] == 1169


def test_1168_milestone_seal_keeps_all_execution_surfaces_locked():
    seal = build_controlled_active_limited_mode_execution_dry_run_milestone_seal(_admission())

    assert seal["execution_admission_allowed"] is False
    assert seal["execution_start_allowed"] is False
    assert seal["execution_commit_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["controlled_active_mode_enabled"] is False
    assert seal["runtime_state_mutated"] is False
    assert seal["real_mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["unbounded_autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False


def test_1168_milestone_seal_preserves_non_mainline_reporting_rule():
    seal = build_controlled_active_limited_mode_execution_dry_run_milestone_seal(_admission())

    assert seal["non_mainline_issue_reporting_required"] is True
