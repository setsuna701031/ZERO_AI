from __future__ import annotations

from core.runtime.runtime_controlled_activation_commit_gate import (
    COMMIT_GATE_BOUNDARY_LOCKS,
    CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA,
    REQUIRED_COMMIT_GATE_FIELDS,
    build_controlled_activation_commit_gate_audit_record,
    build_controlled_activation_commit_gate_no_go_seal,
    build_controlled_activation_commit_gate_request,
    preview_commit_window,
    preview_limited_runtime_opening_gate,
    review_activation_commit_token,
    review_post_commit_rollback_binding,
    review_transaction_commit_authority,
    validate_controlled_activation_commit_gate_request,
)


def _request():
    return build_controlled_activation_commit_gate_request(
        commit_gate_id="commit-gate-1193",
        transaction_dry_run_id="transaction-1193",
        switch_authority_id="switch-1193",
        candidate_id="candidate-1193",
        activation_attempt_id="attempt-1193",
        operator_id="operator-zero",
        executor_id="executor-zero",
    )


def test_1193_contract_schema_and_required_fields_are_present():
    request = _request()

    assert request["schema"] == CONTROLLED_ACTIVATION_COMMIT_GATE_SCHEMA
    for field in REQUIRED_COMMIT_GATE_FIELDS:
        assert field in request
    assert request["gate_scope"] == "commit_gate_review_only"


def test_1193_missing_required_field_is_rejected():
    request = _request()
    request.pop("commit_gate_id")

    result = validate_controlled_activation_commit_gate_request(request)

    assert result["valid"] is False
    assert "missing_required_fields" in result["problems"]
    assert "commit_gate_id" in result["missing_required_fields"]


def test_1193_all_hard_boundary_flags_are_false():
    request = _request()

    for key, expected in COMMIT_GATE_BOUNDARY_LOCKS.items():
        assert request["boundary_locks"][key] is expected
    assert request["non_mainline_issue_reporting_required"] is True


def test_1194_transaction_commit_authority_is_review_only():
    authority = review_transaction_commit_authority(_request())

    assert authority["review_only"] is True
    assert authority["authority_candidate"] is True
    assert authority["transaction_commit_allowed"] is False
    assert authority["authority_commit_allowed"] is False


def test_1194_transaction_commit_authority_attempt_is_blocked():
    request = _request()
    request["transaction_commit_authority"]["transaction_commit_allowed"] = True

    result = validate_controlled_activation_commit_gate_request(request)

    assert "transaction_commit_authority_attempt" in result["problems"]
    assert result["transaction_commit_allowed"] is False


def test_1195_activation_commit_token_is_review_only():
    token = review_activation_commit_token(_request())

    assert token["review_only"] is True
    assert token["token_candidate"] is True
    assert token["token_verified"] is False
    assert token["activation_commit_allowed"] is False
    assert token["token_commit_allowed"] is False


def test_1195_activation_commit_token_attempt_is_blocked():
    request = _request()
    request["activation_commit_token"]["token_verified"] = True
    request["activation_commit_token"]["activation_commit_allowed"] = True

    result = validate_controlled_activation_commit_gate_request(request)

    assert "activation_commit_token_attempt" in result["problems"]
    assert result["activation_commit_allowed"] is False


def test_1196_commit_window_is_preview_only():
    window = preview_commit_window(_request())

    assert window["preview_only"] is True
    assert window["window_candidate"] is True
    assert window["commit_gate_allowed"] is False
    assert window["transaction_commit_allowed"] is False
    assert window["activation_commit_allowed"] is False


def test_1196_commit_window_open_attempt_is_blocked():
    request = _request()
    request["commit_window"]["commit_gate_allowed"] = True
    request["commit_window"]["activation_commit_allowed"] = True

    result = validate_controlled_activation_commit_gate_request(request)

    assert "commit_window_open_attempt" in result["problems"]
    assert result["commit_gate_allowed"] is False
    assert result["activation_commit_allowed"] is False


def test_1197_post_commit_rollback_binding_is_review_only():
    binding = review_post_commit_rollback_binding(_request())

    assert binding["review_only"] is True
    assert binding["rollback_binding_candidate"] is True
    assert binding["rollback_binding_live"] is False
    assert binding["rollback_binding_commit_allowed"] is False


def test_1197_post_commit_rollback_live_attempt_is_blocked():
    request = _request()
    request["post_commit_rollback_binding"]["rollback_binding_live"] = True

    result = validate_controlled_activation_commit_gate_request(request)

    assert "post_commit_rollback_binding_live_attempt" in result["problems"]
    assert result["post_commit_rollback_binding"]["rollback_binding_live"] is False


def test_1198_limited_runtime_opening_gate_is_preview_only():
    gate = preview_limited_runtime_opening_gate(_request())

    assert gate["preview_only"] is True
    assert gate["opening_candidate"] is True
    assert gate["limited_runtime_open_allowed"] is False
    assert gate["runtime_mode_transition_allowed"] is False
    assert gate["execution_allowed"] is False
    assert gate["mutation_allowed"] is False


def test_1198_limited_runtime_open_attempt_is_blocked():
    request = _request()
    request["limited_runtime_opening_gate"]["limited_runtime_open_allowed"] = True
    request["limited_runtime_opening_gate"]["runtime_mode_transition_allowed"] = True

    result = validate_controlled_activation_commit_gate_request(request)

    assert "limited_runtime_open_attempt" in result["problems"]
    assert result["limited_runtime_open_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False


def test_1199_audit_contains_commit_gate_evidence():
    audit = build_controlled_activation_commit_gate_audit_record(_request())

    assert audit["decision"] == "reserved_no_controlled_activation_commit_gate"
    assert audit["transaction_commit_authority"]["review"] == "transaction_commit_authority"
    assert audit["activation_commit_token"]["review"] == "activation_commit_token"
    assert audit["commit_window"]["preview"] == "commit_window"
    assert audit["post_commit_rollback_binding"]["review"] == "post_commit_rollback_binding"
    assert audit["limited_runtime_opening_gate"]["preview"] == "limited_runtime_opening_gate"


def test_1199_audit_proves_no_commit_or_opening_happened():
    audit = build_controlled_activation_commit_gate_audit_record(_request())

    assert audit["commit_gate_happened"] is False
    assert audit["transaction_committed"] is False
    assert audit["activation_committed"] is False
    assert audit["activation_happened"] is False
    assert audit["limited_runtime_opened"] is False


def test_1199_audit_represents_non_mainline_issues():
    request = _request()
    request["boundary_locks"]["external_io_allowed"] = True

    audit = build_controlled_activation_commit_gate_audit_record(request)

    assert audit["non_mainline_issue_reporting_required"] is True
    assert "boundary_unlock_attempt" in audit["non_mainline_issues"]
    assert audit["external_io_allowed"] is False


def test_1200_no_go_seal_closes_commit_gate_review():
    seal = build_controlled_activation_commit_gate_no_go_seal(_request())

    assert seal["closed"] is True
    assert seal["final_decision"] == "NO_GO_FOR_REAL_COMMIT_GATE_GO_FOR_REVIEW_ONLY"
    assert seal["next_package"] == 1201
    assert seal["audit_decision"] == "reserved_no_controlled_activation_commit_gate"


def test_1200_no_go_seal_keeps_all_surfaces_locked():
    seal = build_controlled_activation_commit_gate_no_go_seal(_request())

    assert seal["commit_gate_happened"] is False
    assert seal["transaction_committed"] is False
    assert seal["activation_committed"] is False
    assert seal["activation_happened"] is False
    assert seal["limited_runtime_opened"] is False
    assert seal["commit_gate_allowed"] is False
    assert seal["transaction_commit_allowed"] is False
    assert seal["activation_commit_allowed"] is False
    assert seal["activation_allowed"] is False
    assert seal["limited_runtime_open_allowed"] is False
    assert seal["runtime_mode_transition_allowed"] is False
    assert seal["execution_allowed"] is False
    assert seal["mutation_allowed"] is False
    assert seal["external_io_allowed"] is False
    assert seal["autonomy_allowed"] is False
    assert seal["self_start_allowed"] is False
    assert seal["all_execution_surfaces_locked"] is True
