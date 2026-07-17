from __future__ import annotations

from core.runtime.runtime_controlled_active_limited_mode_final_readiness import (
    CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA,
    REQUIRED_FINAL_READINESS_FIELDS,
    REQUIRED_PREVIOUS_SEALS,
    SAFETY_BOUNDARY_LOCKS,
    aggregate_previous_final_readiness_seals,
    build_activation_readiness_candidate_preview,
    build_controlled_active_limited_mode_final_readiness_audit_record,
    build_controlled_active_limited_mode_final_readiness_milestone_seal,
    build_controlled_active_limited_mode_final_readiness_request,
    build_final_go_candidate_evidence,
    evaluate_final_safety_boundary_matrix,
    preview_final_readiness_ownership_chain,
    validate_controlled_active_limited_mode_final_readiness_request,
)


def _request():
    return build_controlled_active_limited_mode_final_readiness_request(
        readiness_id="readiness-1169",
        candidate_id="candidate-1169",
        activation_attempt_id="attempt-1169",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1169_contract_schema_and_required_fields_are_present():
    request = _request()

    assert request["schema"] == CONTROLLED_ACTIVE_LIMITED_MODE_FINAL_READINESS_SCHEMA
    for field in REQUIRED_FINAL_READINESS_FIELDS:
        assert field in request
    assert request["readiness_scope"] == "final_readiness_dry_run_only"


def test_1169_missing_required_field_is_rejected():
    request = _request()
    request.pop("readiness_id")

    result = validate_controlled_active_limited_mode_final_readiness_request(request)

    assert result["valid"] is False
    assert "missing_required_fields" in result["problems"]
    assert "readiness_id" in result["missing_required_fields"]


def test_1169_non_mainline_issue_reporting_is_required():
    request = _request()

    assert request["non_mainline_issue_reporting_required"] is True
    assert validate_controlled_active_limited_mode_final_readiness_request(request)[
        "audit_required"
    ] is True


def test_1170_previous_seal_aggregation_requires_all_prior_seals():
    result = aggregate_previous_final_readiness_seals(_request()["previous_seals"])

    assert result["required_seals"] == list(REQUIRED_PREVIOUS_SEALS)
    assert result["all_required_present"] is True
    assert result["all_required_closed_and_sealed"] is True
    assert result["readiness_blocked"] is False


def test_1170_missing_previous_seal_blocks_readiness():
    request = _request()
    request["previous_seals"].pop("controlled_active_limited_mode_state_dry_run")

    result = validate_controlled_active_limited_mode_final_readiness_request(request)

    assert result["valid"] is False
    assert "previous_seal_aggregation_blocked" in result["problems"]
    assert "controlled_active_limited_mode_state_dry_run" in result[
        "previous_seal_aggregation"
    ]["missing_seals"]


def test_1170_open_previous_seal_blocks_readiness():
    request = _request()
    request["previous_seals"]["controlled_active_limited_mode_execution_dry_run"][
        "closed"
    ] = False

    result = aggregate_previous_final_readiness_seals(request["previous_seals"])

    assert result["readiness_blocked"] is True
    assert "controlled_active_limited_mode_execution_dry_run" in result[
        "open_or_unsealed_seals"
    ]


def test_1171_ownership_chain_is_preview_only():
    preview = preview_final_readiness_ownership_chain(_request())

    assert preview["preview_only"] is True
    assert preview["ownership_verified"] is False
    assert preview["ownership_commit_allowed"] is False
    assert preview["runtime_state_mutated"] is False


def test_1171_ownership_commit_attempt_is_reported_and_blocked():
    request = _request()
    request["ownership_chain"]["ownership_verified"] = True
    request["ownership_chain"]["ownership_commit_allowed"] = True

    preview = preview_final_readiness_ownership_chain(request)
    result = validate_controlled_active_limited_mode_final_readiness_request(request)

    assert "ownership_commit_attempt_blocked" in preview["blockers"]
    assert "ownership_commit_attempt" in result["problems"]
    assert preview["ownership_verified"] is False
    assert preview["ownership_commit_allowed"] is False


def test_1172_activation_readiness_candidate_is_evidence_only():
    candidate = build_activation_readiness_candidate_preview(_request())

    assert candidate["activation_ready_candidate"] is True
    assert candidate["activation_ready_candidate_evidence_only"] is True
    assert candidate["activation_allowed"] is False
    assert candidate["activation_commit_allowed"] is False
    assert candidate["runtime_mode_transition_allowed"] is False


def test_1172_activation_unlock_attempt_is_reported_and_blocked():
    request = _request()
    request["readiness_candidate"]["activation_allowed"] = True
    request["readiness_candidate"]["runtime_mode_transition_allowed"] = True

    result = validate_controlled_active_limited_mode_final_readiness_request(request)

    assert result["valid"] is False
    assert "activation_unlock_attempt" in result["problems"]
    assert result["activation_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False


def test_1173_final_safety_boundary_matrix_keeps_all_locks():
    matrix = evaluate_final_safety_boundary_matrix(_request())

    for key, expected in SAFETY_BOUNDARY_LOCKS.items():
        assert matrix["locks"][key] is expected
    assert matrix["rollback_authority_required"] is True
    assert matrix["rollback_authority_live"] is False
    assert matrix["kill_switch_authority_required"] is True
    assert matrix["kill_switch_authority_live"] is False


def test_1173_any_unlock_attempt_is_reported():
    request = _request()
    request["safety_boundary_matrix"]["external_tool_execution_allowed"] = True
    request["safety_boundary_matrix"]["network_io_allowed"] = True

    matrix = evaluate_final_safety_boundary_matrix(request)

    assert matrix["unlock_attempt_reported"] is True
    assert "external_tool_execution_allowed" in matrix["unlock_attempts"]
    assert "network_io_allowed" in matrix["unlock_attempts"]
    assert matrix["external_tool_execution_allowed"] is False
    assert matrix["network_io_allowed"] is False


def test_1174_go_candidate_evidence_is_evidence_only():
    evidence = build_final_go_candidate_evidence(_request())

    assert evidence["go_candidate_created"] is True
    assert evidence["evidence_only"] is True
    assert evidence["go_allowed"] is False
    assert evidence["activation_allowed"] is False
    assert evidence["execution_allowed"] is False


def test_1174_go_candidate_unlock_attempt_is_reported_and_blocked():
    request = _request()
    request["go_candidate_evidence"]["go_allowed"] = True
    request["go_candidate_evidence"]["execution_allowed"] = True

    evidence = build_final_go_candidate_evidence(request)
    result = validate_controlled_active_limited_mode_final_readiness_request(request)

    assert "go_candidate_unlock_attempt_blocked" in evidence["blockers"]
    assert "go_candidate_unlock_attempt" in result["problems"]
    assert evidence["go_allowed"] is False
    assert evidence["execution_allowed"] is False


def test_1175_audit_seal_uses_reserved_no_final_activation_decision():
    audit = build_controlled_active_limited_mode_final_readiness_audit_record(_request())

    assert audit["decision"] == "reserved_no_controlled_active_limited_mode_final_activation"
    assert audit["activation_happened"] is False
    assert audit["activation_allowed"] is False
    assert audit["execution_allowed"] is False


def test_1175_audit_contains_all_final_readiness_sections():
    audit = build_controlled_active_limited_mode_final_readiness_audit_record(_request())

    assert audit["previous_seal_aggregation"]["aggregation"] == "previous_final_readiness_seals"
    assert audit["ownership_preview"]["preview"] == "final_readiness_ownership_chain"
    assert audit["readiness_candidate"]["preview"] == "activation_readiness_candidate"
    assert audit["safety_boundary_matrix"]["matrix"] == "final_safety_boundary"
    assert audit["go_candidate_evidence"]["evidence"] == "final_go_candidate"


def test_1175_audit_represents_non_mainline_issues():
    request = _request()
    request["safety_boundary_matrix"]["self_start_allowed"] = True

    audit = build_controlled_active_limited_mode_final_readiness_audit_record(request)

    assert audit["non_mainline_issue_reporting_required"] is True
    assert "safety_boundary_unlock_attempt" in audit["non_mainline_issues"]
    assert audit["self_start_allowed"] is False


def test_1176_final_dry_run_closure_decision_and_next_package():
    seal = build_controlled_active_limited_mode_final_readiness_milestone_seal(_request())

    assert seal["closed"] is True
    assert (
        seal["final_decision"]
        == "NO_GO_FOR_REAL_ACTIVATION_GO_FOR_FINAL_READINESS_DRY_RUN_ONLY"
    )
    assert seal["next_package"] == 1177


def test_1176_all_execution_surfaces_remain_locked():
    seal = build_controlled_active_limited_mode_final_readiness_milestone_seal(_request())

    assert seal["activation_happened"] is False
    assert seal["activation_allowed"] is False
    assert seal["activation_commit_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["execution_allowed"] is False
    assert seal["runtime_state_mutated"] is False
    assert seal["real_mutation_allowed"] is False
    assert seal["file_mutation_allowed"] is False
    assert seal["external_tool_execution_allowed"] is False
    assert seal["network_io_allowed"] is False
    assert seal["unbounded_autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False
    assert seal["all_execution_surfaces_locked"] is True
