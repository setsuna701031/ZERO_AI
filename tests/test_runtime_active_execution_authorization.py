from __future__ import annotations
import copy
import pytest
from core.runtime.runtime_active_execution_authorization import RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT, authorize_active_execution
from core.runtime.runtime_controlled_execution_activation import activate_controlled_execution
from tests.test_runtime_executor_admission_token import NOW, inputs

def records(tmp_path):
    p,r,q=inputs(tmp_path); activation=activate_controlled_execution(p,r,q,target_root=tmp_path,now=NOW)
    auth={"contract":RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT,"authorization_id":"auth-one",
        "controlled_execution_result_id":activation["activation_id"],"token_id":activation["token"]["token_id"],
        "plan_id":activation["plan_id"],"review_result_id":activation["review_result_id"],
        "operator_execution_request_id":activation["operator_request_id"],"operator_id":activation["token"]["operator_id"],
        "decision":"authorized","authorized_mode":"prepared_active_execution","authorized_at":NOW,
        "expires_at":"2026-07-10T12:10:00+00:00","acknowledged_scope":copy.deepcopy(activation["token"]["allowed_files"]),
        "acknowledged_snapshot_manifest_id":activation["snapshot_manifest"]["manifest_id"],
        "acknowledged_validation_evidence_id":activation["validation_evidence"]["validation_evidence_id"],
        "acknowledged_rollback_state_id":activation["rollback_prepared_state"]["rollback_state_id"],
        "acknowledged_risks":["manual_active_boundary_required"],"acknowledged_no_automatic_commit":True,
        "acknowledged_manual_rollback_authority":True}
    return activation,auth

def test_authorized_is_deterministic_pure_prepared_but_never_ready(tmp_path):
    activation,auth=records(tmp_path); before=copy.deepcopy((activation,auth))
    first=authorize_active_execution(activation,auth,now=NOW); second=authorize_active_execution(activation,auth,now=NOW)
    assert first["authorization_status"]=="authorized" and first["active_execution_prepared"] is True
    assert first["authorization_result_id"]==second["authorization_result_id"] and (activation,auth)==before
    for key in ("active_execution_ready","execution_allowed","file_mutation_allowed","patch_application_allowed",
                "validation_execution_allowed","rollback_execution_allowed","commit_allowed"): assert first[key] is False
    assert first["required_next_boundary"]=="active_executor_invocation_gate"

def test_rejected_is_valid_not_prepared(tmp_path):
    activation,auth=records(tmp_path); auth["decision"]="rejected"
    result=authorize_active_execution(activation,auth,now=NOW)
    assert result["authorization_status"]=="rejected" and result["authorization_valid"] is True
    assert result["active_execution_prepared"] is False

@pytest.mark.parametrize(("target","updates","reason"),[
    ("auth",{"decision":"yes"},"invalid_decision"),("auth",{"authorized_mode":"live"},"invalid_authorized_mode"),
    ("auth",{"operator_id":""},"operator_id_required"),("auth",{"authorization_id":""},"authorization_id_required"),
    ("auth",{"expires_at":NOW},"invalid_authorization_expiration_order"),
    ("auth",{"expires_at":"2026-07-10T12:11:00+00:00"},"authorization_lifetime_exceeds_ten_minutes"),
    ("activation",{"activation_status":"blocked"},"controlled_dry_run_not_completed"),
    ("activation",{"dry_run_completed":False},"controlled_dry_run_not_completed"),
    ("activation",{"execution_allowed":True},"unsafe_upstream_execution_state"),
    ("activation",{"file_mutation_performed":True},"unsafe_upstream_execution_state"),
    ("activation",{"patch_applied":True},"unsafe_upstream_execution_state"),
    ("activation",{"validation_executed":True},"unsafe_upstream_execution_state"),
    ("activation",{"rollback_executed":True},"unsafe_upstream_execution_state"),
    ("activation",{"commit_performed":True},"unsafe_upstream_execution_state"),
    ("auth",{"plan_id":"wrong"},"plan_id_mismatch"),("auth",{"review_result_id":"wrong"},"review_result_id_mismatch"),
    ("auth",{"operator_execution_request_id":"wrong"},"operator_execution_request_id_mismatch"),
    ("auth",{"token_id":"wrong"},"token_id_mismatch"),
    ("auth",{"controlled_execution_result_id":"wrong"},"controlled_execution_result_id_mismatch"),
    ("auth",{"acknowledged_scope":[]},"acknowledged_scope_mismatch"),
    ("auth",{"acknowledged_snapshot_manifest_id":"wrong"},"acknowledged_snapshot_manifest_id_mismatch"),
    ("auth",{"acknowledged_validation_evidence_id":"wrong"},"acknowledged_validation_evidence_id_mismatch"),
    ("auth",{"acknowledged_rollback_state_id":"wrong"},"acknowledged_rollback_state_id_mismatch"),
    ("auth",{"acknowledged_risks":[]},"acknowledged_risks_required"),
    ("auth",{"acknowledged_no_automatic_commit":False},"no_automatic_commit_not_acknowledged"),
    ("auth",{"acknowledged_manual_rollback_authority":False},"manual_rollback_authority_not_acknowledged"),
])
def test_fail_closed(tmp_path,target,updates,reason):
    activation,auth=records(tmp_path); {"activation":activation,"auth":auth}[target].update(updates)
    result=authorize_active_execution(activation,auth,now=NOW)
    assert result["authorization_status"]=="invalid" and reason in result["reasons"]
    assert result["active_execution_prepared"] is False and result["execution_allowed"] is False

def test_expired_upstream_token_is_rejected(tmp_path):
    activation,auth=records(tmp_path)
    result=authorize_active_execution(activation,auth,now="2026-07-10T12:16:00+00:00")
    assert "upstream_token_expired" in result["reasons"]

