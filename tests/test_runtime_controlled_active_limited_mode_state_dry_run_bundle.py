from __future__ import annotations

from core.runtime.runtime_controlled_active_limited_mode_state_dry_run import (
    CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA,
    LOCKED_BOUNDARIES,
    REQUIRED_BLOCKERS,
    REQUIRED_CANDIDATE_FIELDS,
    build_controlled_active_limited_mode_state_dry_run_audit_record,
    build_controlled_active_limited_mode_state_dry_run_candidate,
    build_controlled_active_limited_mode_state_dry_run_milestone_seal,
    evaluate_dry_run_mutation_boundary,
    evaluate_internal_execution_state_preview,
    evaluate_limited_scheduler_state_preview,
    simulate_limited_runtime_state_transition,
    validate_controlled_active_limited_mode_state_dry_run_candidate,
)


def _candidate():
    return build_controlled_active_limited_mode_state_dry_run_candidate(
        candidate_id="candidate-1145",
        activation_attempt_id="attempt-1145",
        operator_id="operator-zero",
    )


def test_1145_contract_schema_and_required_fields_are_present():
    candidate = _candidate()

    assert candidate["schema"] == CONTROLLED_ACTIVE_LIMITED_MODE_STATE_DRY_RUN_SCHEMA
    for field in REQUIRED_CANDIDATE_FIELDS:
        assert field in candidate
    assert candidate["candidate_status"] == "dry_run_only"


def test_1145_missing_required_field_is_rejected():
    candidate = _candidate()
    candidate.pop("candidate_id")

    result = validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)

    assert result["valid"] is False
    assert result["status"] == "blocked"
    assert "candidate_id" in result["missing_required_fields"]


def test_1145_audit_is_required():
    candidate = _candidate()

    assert validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)[
        "audit_required"
    ] is True


def test_1146_state_scope_is_runtime_state_dry_run():
    candidate = _candidate()

    assert candidate["state_scope"] == "runtime_state_dry_run"
    assert candidate["transition_preview"]["runtime_state_mutated"] is False


def test_1146_gate_review_does_not_open_gate():
    candidate = _candidate()

    assert candidate["gate_review"]["required"] is True
    assert candidate["gate_review"]["gate_opened"] is False


def test_1146_non_mainline_issue_reporting_is_required():
    candidate = _candidate()

    assert candidate["non_mainline_issue_reporting_required"] is True


def test_1147_scheduler_preview_is_dry_run_only():
    result = evaluate_limited_scheduler_state_preview(_candidate())

    assert result["preview_only"] is True
    assert result["limited_scheduler_enabled"] is False
    assert result["dispatch_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1147_scheduler_enable_attempt_is_blocked():
    candidate = _candidate()
    candidate["scheduler_preview"]["limited_scheduler_enabled"] = True

    result = evaluate_limited_scheduler_state_preview(candidate)

    assert "limited_scheduler_enable_blocked" in result["blockers"]
    assert result["limited_scheduler_enabled"] is False


def test_1147_unbounded_scheduler_loop_attempt_is_blocked():
    candidate = _candidate()
    candidate["scheduler_preview"]["unbounded_loop_allowed"] = True

    result = evaluate_limited_scheduler_state_preview(candidate)

    assert "unbounded_scheduler_loop_blocked" in result["blockers"]
    assert result["unbounded_loop_allowed"] is False


def test_1148_internal_execution_preview_is_dry_run_only():
    result = evaluate_internal_execution_state_preview(_candidate())

    assert result["preview_only"] is True
    assert result["internal_execution_enabled"] is False
    assert result["external_execution_allowed"] is False
    assert result["tool_execution_allowed"] is False


def test_1148_internal_execution_enable_attempt_is_blocked():
    candidate = _candidate()
    candidate["execution_preview"]["internal_execution_enabled"] = True

    result = evaluate_internal_execution_state_preview(candidate)

    assert "internal_execution_enable_blocked" in result["blockers"]
    assert result["internal_execution_enabled"] is False


def test_1148_external_execution_escape_attempt_is_blocked():
    candidate = _candidate()
    candidate["execution_preview"]["external_execution_allowed"] = True
    candidate["execution_preview"]["tool_execution_allowed"] = True

    result = evaluate_internal_execution_state_preview(candidate)

    assert "external_execution_escape_blocked" in result["blockers"]
    assert result["external_execution_allowed"] is False
    assert result["tool_execution_allowed"] is False


def test_1149_transition_simulation_never_allows_transition():
    result = simulate_limited_runtime_state_transition(_candidate())

    assert result["preview_only"] is True
    assert result["transition_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_1149_transition_attempt_is_blocked():
    candidate = _candidate()
    candidate["transition_preview"]["runtime_mode_transition_allowed"] = True

    result = simulate_limited_runtime_state_transition(candidate)

    assert "runtime_state_transition_attempt_blocked" in result["blockers"]
    assert result["transition_allowed"] is False


def test_1149_runtime_state_mutation_attempt_is_blocked():
    candidate = _candidate()
    candidate["transition_preview"]["runtime_state_mutated"] = True

    result = simulate_limited_runtime_state_transition(candidate)

    assert "runtime_state_transition_attempt_blocked" in result["blockers"]
    assert result["runtime_state_mutated"] is False


def test_1150_all_boundaries_are_locked_by_default():
    candidate = _candidate()

    for key, expected in LOCKED_BOUNDARIES.items():
        assert candidate["mutation_boundary"][key] is expected


def test_1150_unlock_attempts_are_reported():
    candidate = _candidate()
    candidate["mutation_boundary"]["network_io_allowed"] = True
    candidate["mutation_boundary"]["real_file_mutation_allowed"] = True

    result = evaluate_dry_run_mutation_boundary(candidate)

    assert "network_io_allowed" in result["unlock_attempts"]
    assert "real_file_mutation_allowed" in result["unlock_attempts"]
    assert result["network_io_allowed"] is False
    assert result["real_file_mutation_allowed"] is False


def test_1150_validation_reports_unlock_attempts():
    candidate = _candidate()
    candidate["mutation_boundary"]["runtime_mode_transition_allowed"] = True

    result = validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)

    assert result["valid"] is False
    assert "boundary_unlock_attempt" in result["problems"]
    assert "runtime_mode_transition_allowed" in result["unlock_attempts"]


def test_1151_audit_record_uses_reserved_no_transition_decision():
    audit = build_controlled_active_limited_mode_state_dry_run_audit_record(_candidate())

    assert (
        audit["decision"]
        == "reserved_no_controlled_active_limited_mode_state_transition"
    )
    assert audit["runtime_mode_transition_allowed"] is False
    assert audit["runtime_state_mutated"] is False


def test_1151_audit_contains_scheduler_execution_transition_and_mutation_evidence():
    audit = build_controlled_active_limited_mode_state_dry_run_audit_record(_candidate())

    assert audit["scheduler_preview"]["preview"] == "limited_scheduler_state"
    assert audit["execution_preview"]["preview"] == "internal_execution_state"
    assert audit["transition_preview"]["preview"] == "limited_runtime_state_transition"
    assert audit["mutation_boundary"]["preview"] == "dry_run_mutation_boundary"


def test_1151_audit_preserves_no_external_io():
    audit = build_controlled_active_limited_mode_state_dry_run_audit_record(_candidate())

    assert audit["external_io_allowed"] is False
    assert audit["real_mutation_allowed"] is False
    assert audit["audit_required"] is True


def test_1152_milestone_seal_closes_dry_run_state_layer():
    seal = build_controlled_active_limited_mode_state_dry_run_milestone_seal(_candidate())

    assert seal["closed"] is True
    assert seal["final_decision"] == "GO_FOR_DRY_RUN_STATE_REVIEW_ONLY"
    assert seal["next_package"] == 1153


def test_1152_milestone_seal_keeps_all_execution_surfaces_locked():
    seal = build_controlled_active_limited_mode_state_dry_run_milestone_seal(_candidate())

    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["controlled_active_mode_enabled"] is False
    assert seal["limited_scheduler_enabled"] is False
    assert seal["internal_execution_enabled"] is False
    assert seal["runtime_state_mutated"] is False
    assert seal["real_mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["unbounded_autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False


def test_1152_milestone_seal_preserves_non_mainline_reporting_rule():
    seal = build_controlled_active_limited_mode_state_dry_run_milestone_seal(_candidate())

    assert seal["non_mainline_issue_reporting_required"] is True


def test_missing_required_blocker_is_rejected():
    candidate = _candidate()
    candidate["blockers"] = [blocker for blocker in REQUIRED_BLOCKERS if blocker != "network_io_locked"]

    result = validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)

    assert result["valid"] is False
    assert "missing_required_blockers" in result["problems"]
    assert "network_io_locked" in result["missing_required_blockers"]


def test_candidate_status_must_remain_dry_run_only():
    candidate = _candidate()
    candidate["candidate_status"] = "enabled"

    result = validate_controlled_active_limited_mode_state_dry_run_candidate(candidate)

    assert result["valid"] is False
    assert "candidate_not_dry_run_only" in result["problems"]


def test_validation_accepts_default_candidate_without_enabling_runtime():
    result = validate_controlled_active_limited_mode_state_dry_run_candidate(_candidate())

    assert result["valid"] is True
    assert result["runtime_mode_transition_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["real_mutation_allowed"] is False
    assert result["external_io_allowed"] is False
