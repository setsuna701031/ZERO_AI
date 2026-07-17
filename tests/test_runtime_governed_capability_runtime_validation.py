from copy import deepcopy
import pytest

from core.runtime.runtime_governed_capability_runtime_validation import validate_governed_capability_runtime_input
from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime
import core.runtime.runtime_governed_capability_runtime as runtime_module
import core.runtime.runtime_capability_decision_transaction_preparation as transaction_module
from tests.test_runtime_governed_capability_runtime import completed_input, runtime_input
from tests.test_runtime_capability_activation_verification_closure import closure as activation_closure


def test_input_is_exact_json_safe_and_dry_run(tmp_path):
    value = runtime_input(tmp_path)
    assert validate_governed_capability_runtime_input(value).valid
    bad = deepcopy(value); bad["runtime_options"]["allow_mutation"] = True
    assert not validate_governed_capability_runtime_input(bad).valid
    bad = deepcopy(value); bad["explicit_inputs"]["decision_question"] = {"opaque": {1}}
    assert not validate_governed_capability_runtime_input(bad).valid


def _assert_blocked(value):
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "blocked"
    assert result["runtime_orchestration_closure"]["verification_status"] != "verified_closed"
    assert result["prepared_transaction_handoff"] is None
    assert result["audit_summary"]["reasons"]
    return result


def test_upstream_contract_fingerprint_lineage_and_stage_injection_fail_closed(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path); value["contract"] = "unknown"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["capability_profile"]["schema"] = "unknown"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["capability_strategy"]["fingerprint"] = "0" * 64
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["dry_run_bridge_closure"]["authority_id"] = "replacement"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["resume_from"] = "runtime_closed"
    _assert_blocked(value)


def test_activation_execution_bridge_and_dry_run_fail_closed(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path); value["upstream_artifacts"]["activation_verification_closure"] = activation_closure("blocked")
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["execution_request"]["target_descriptor"] = {"resource": "expanded"}
    _assert_blocked(value)
    value = completed_input(tmp_path); value["runtime_options"]["dry_run_only"] = False
    _assert_blocked(value)
    value = completed_input(tmp_path); value["upstream_artifacts"]["dry_run_bridge_closure"]["closed"] = False
    _assert_blocked(value)


def test_observation_evidence_and_decision_fail_closed(tmp_path):
    (tmp_path / "target.txt").write_bytes(b"x" * 32)
    value = completed_input(tmp_path); value["explicit_inputs"]["relative_target"] = "../escape"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"].update({"observation_kind": "text_preview",
        "observation_limits": {"max_file_bytes": 1, "max_preview_bytes": 1, "max_directory_entries": 1, "max_name_bytes": 1}})
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["decision_question"]["question_type"] = "target_metadata_available"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["sufficiency_requirements"]["require_target_type"] = "yes"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["requested_permissions"]["network"] = True
    _assert_blocked(value)


def test_transaction_review_token_activation_and_scope_fail_closed(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path); value["explicit_inputs"]["operator_review"]["decision"] = "rejected"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["operator_review"]["expires_at"] = "2026-07-10T11:59:00+00:00"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["active_authorization_request"]["decision"] = "rejected"
    _assert_blocked(value)
    value = completed_input(tmp_path); value["explicit_inputs"]["execution_intent"]["dry_run"] = False
    _assert_blocked(value)


def test_non_json_input_and_result_detachment(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path); value["explicit_inputs"]["decision_question"] = {"opaque": {1}}
    result = _assert_blocked(value)
    assert "traceback" not in str(result).lower()
    value = completed_input(tmp_path)
    result = run_governed_capability_runtime(value)
    saved = deepcopy(result)
    value["explicit_inputs"]["relative_target"] = "changed"
    assert result == saved


def test_prepared_handoff_and_integration_tampering_fail_closed(monkeypatch, tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    original = runtime_module.prepare_capability_decision_transaction

    def tampered_handoff(*args, **kwargs):
        result = original(*args, **kwargs)
        result["prepared_handoff"]["target_boundary"] = {"relative_target": "replacement"}
        return result

    monkeypatch.setattr(runtime_module, "prepare_capability_decision_transaction", tampered_handoff)
    _assert_blocked(value)
    monkeypatch.setattr(runtime_module, "prepare_capability_decision_transaction", original)

    def tampered_closure(*args, **kwargs):
        result = original(*args, **kwargs)
        result["integration_closure"]["closed"] = False
        return result

    monkeypatch.setattr(runtime_module, "prepare_capability_decision_transaction", tampered_closure)
    result = run_governed_capability_runtime(completed_input(tmp_path))
    assert result["runtime_state"]["runtime_status"] == "blocked"
    assert result["runtime_orchestration_closure"]["verification_status"] != "verified_closed"


def test_resume_target_limitation_permission_and_claim_tampering(tmp_path):
    from tests.test_runtime_governed_capability_runtime import resumed_input
    (tmp_path / "target.txt").touch()
    for field, replacement in (("target_reference", {"relative_target": "replacement"}),
                               ("limitations", ["replacement"]),
                               ("mutation_authorization_claim", True)):
        value = resumed_input(tmp_path, "decision_authorization_closed")
        value["upstream_artifacts"]["decision_authorization_closure"][field] = replacement
        _assert_blocked(value)
    value = resumed_input(tmp_path, "decision_authorization_closed")
    value["explicit_inputs"]["requested_scope"] = {**value["explicit_inputs"]["requested_scope"], "expanded": True}
    _assert_blocked(value)


def test_symlink_or_reparse_observation_is_blocked(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.txt")
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink unavailable")
    value = completed_input(tmp_path)
    value["explicit_inputs"]["relative_target"] = "link.txt"
    value["explicit_inputs"]["decision_question"]["target_reference"] = {"relative_target": "link.txt"}
    _assert_blocked(value)


def test_token_activation_and_active_scope_seam_tampering(monkeypatch, tmp_path):
    (tmp_path / "target.txt").touch()
    original_token = transaction_module.issue_executor_admission_token
    original_activation = transaction_module.activate_controlled_execution
    original_authorization = transaction_module.authorize_active_execution

    def expired_token(*args, **kwargs):
        value = original_token(*args, **kwargs)
        value["expires_at"] = "2000-01-01T00:00:00+00:00"
        value["token_status"] = "expired"
        value["audit_record"]["token_status"] = "expired"
        return value

    monkeypatch.setattr(transaction_module, "issue_executor_admission_token", expired_token)
    _assert_blocked(completed_input(tmp_path))
    monkeypatch.setattr(transaction_module, "issue_executor_admission_token", original_token)

    def mismatched_activation(*args, **kwargs):
        value = original_activation(*args, **kwargs)
        value["plan_id"] = "replacement"
        return value

    monkeypatch.setattr(transaction_module, "activate_controlled_execution", mismatched_activation)
    _assert_blocked(completed_input(tmp_path))
    monkeypatch.setattr(transaction_module, "activate_controlled_execution", original_activation)

    def expanded_authorization(*args, **kwargs):
        value = original_authorization(*args, **kwargs)
        value["authorized_scope"] = ["expanded"]
        return value

    monkeypatch.setattr(transaction_module, "authorize_active_execution", expanded_authorization)
    _assert_blocked(completed_input(tmp_path))
