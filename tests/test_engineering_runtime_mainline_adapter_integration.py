from copy import deepcopy
from core.engineering.engineering_runtime_execution_coordination import coordinate_engineering_runtime_execution
from core.engineering.engineering_runtime_adapter_execution_capability import build_runtime_adapter_execution_capability
from core.engineering.engineering_runtime_workspace_root_admission import admit_workspace_root
from core.engineering.engineering_workspace_mutation_executor_common import workspace_fingerprint
from tests.engineering_workspace_mutation_executor_fixtures import handoff as mutation_handoff

def art(**values): return {"fingerprint":"f-"+next(iter(values)),**values}

def context(tmp_path):
    admission=admit_workspace_root(tmp_path,"ws")
    request={"execution_requested":True,"fingerprint":"request-fp"}
    session={"session_id":"session-1","workspace_id":"ws","workspace_root_fingerprint":admission["workspace_root_fingerprint"]}
    phase={"phase":"execution_ready"}; transaction={"status":"ready","fingerprint":"transaction-fp"}
    execution_request={"adapter_id":"zero.engineering.read_only_workspace","adapter_version":"1","allowed_operation":{"operation_id":"workspace_exists"},"approved_scope":["."],"execution_session_id":"session-1"}
    capability=build_runtime_adapter_execution_capability(adapter_id="zero.engineering.read_only_workspace",adapter_version="1",supported_operation_names=["workspace_exists"],supported_input_contract_identifiers=["input"],supported_output_contract_identifiers=["zero.engineering.runtime_workspace_observation_output.v1"],supported_execution_modes=["controlled_read_only"],supported_cancellation_modes=["cooperative"],supported_timeout_bounds={"max":1000},supported_resource_dimensions=["memory"],supported_isolation_levels=["in_process_restricted"])
    flow={"execution_class":"read_only","execution_request":execution_request,"capability":capability,"approved_scope":["."],"authorization_scope":["."],
      "adapter_admission":art(admission_status="admitted"),"adapter_preparation":art(preparation_status="prepared"),"preparation_review":art(review_status="approved"),"activation_eligibility":art(eligibility_status="eligible"),"activation_authorization":art(authorization_status="authorized"),
      "activation_token":{"fingerprint":"token-fp","issuance_status":"issued","consumed":False,"current_uses":0},"activation_token_verification":art(verification_status="verified"),"invocation_handoff":art(eligible_for_concrete_adapter_execution=True),
      "environment_admission":art(environment_admission_status="admitted"),"resource_budget":art(resource_budget_status="bounded"),"timeout_policy":art(timeout_policy_status="bounded"),"isolation_policy":art(isolation_policy_status="valid"),"execution_readiness":art(execution_readiness_status="ready"),
      "executor_handoff":{"executor_handoff_id":"h","fingerprint":"hf"},"integration_closure":{"closure_id":"c","fingerprint":"cf"},"workspace_request":{"operation":"workspace_exists"}}
    return request,session,phase,transaction,flow

def run(tmp_path,change=None,execute=True,confirmed=True):
    request,session,phase,transaction,flow=context(tmp_path)
    if change: change(request,session,phase,transaction,flow)
    return coordinate_engineering_runtime_execution(request,session,phase,transaction,flow["executor_handoff"],tmp_path,execute,confirmed,controlled_flow=flow)

def test_complete_read_only_adapter_flow(tmp_path):
    out=run(tmp_path); assert out["status"]=="succeeded"; assert out["binding_reference"]["fingerprint"]
def test_execution_disabled_by_default(tmp_path): assert run(tmp_path,execute=False)["status"]=="rejected"
def test_missing_confirmation_blocks(tmp_path): assert "execute_confirmation_required" in run(tmp_path,confirmed=False)["reason_codes"]
def test_unknown_adapter_fails_safely(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["execution_request"].update(adapter_id="unknown")); assert out["status"]=="rejected"
def test_invalid_descriptor_fingerprint_fails(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["capability"].update(fingerprint="bad")); assert "adapter_descriptor_invalid" in out["reason_codes"]
def test_unsupported_operation_fails(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["execution_request"]["allowed_operation"].update(operation_id="delete")); assert "adapter_binding_not_resolved" in out["reason_codes"]
def test_workspace_identity_mismatch_blocks(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:s.update(workspace_root_fingerprint="wrong")); assert "workspace_identity_mismatch" in out["reason_codes"]
def test_approved_scope_mismatch_blocks(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f.update(approved_scope=["src"])); assert "approved_scope_mismatch" in out["reason_codes"]
def test_consumed_token_blocks(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["activation_token"].update(consumed=True,current_uses=1)); assert "activation_token_invalid_or_consumed" in out["reason_codes"]
def test_readiness_failure_prevents_invocation(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["execution_readiness"].update(execution_readiness_status="not_ready")); assert "execution_not_ready" in out["reason_codes"]
def test_read_only_adapter_cannot_mutate(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f.update(execution_class="mutation")); assert "read_only_adapter_mutation_forbidden" in out["reason_codes"]
def test_duplicate_completed_execution_suppressed(tmp_path):
    r,s,p,t,f=context(tmp_path); out=coordinate_engineering_runtime_execution(r,s,p,t,f["executor_handoff"],tmp_path,True,True,{"status":"succeeded"},f); assert out["status"]=="duplicate_suppressed"
def test_failure_is_bounded(tmp_path):
    out=run(tmp_path,lambda r,s,p,t,f:f["environment_admission"].update(environment_admission_status="not_admitted")); assert out["status"]=="rejected" and "exception" not in str(out).lower()

def mutation_context(tmp_path):
    (tmp_path/"seed.txt").write_text("seed",encoding="utf-8")
    request,session,phase,transaction,flow=context(tmp_path); session.update(workspace_id="ws1",workspace_root_fingerprint=workspace_fingerprint(tmp_path)); flow["execution_class"]="mutation"; flow["approved_scope"]=["out.txt"]; flow["authorization_scope"]=["out.txt"]
    flow["operator_approval"]={"decision":"approved","operator_id":"operator-1","automated_decision":False,"fingerprint":"approval-fp"}; flow["mutation_authorization"]={"decision":"authorized","authorizer_id":"authorizer-1","automated_decision":False,"fingerprint":"authorization-fp"}
    flow["execution_request"].update(adapter_id="zero.engineering.governed_workspace_mutation",adapter_version="1",approved_scope=["out.txt"],allowed_operation={"operation_id":"mutate"})
    flow["capability"]=build_runtime_adapter_execution_capability(adapter_id="zero.engineering.governed_workspace_mutation",adapter_version="1",supported_operation_names=["mutate"],supported_input_contract_identifiers=["mutation"],supported_output_contract_identifiers=["result"],supported_execution_modes=["governed"],supported_cancellation_modes=["cooperative"],supported_timeout_bounds={"max":1000},supported_resource_dimensions=["memory"],supported_isolation_levels=["in_process_restricted"])
    return request,session,phase,transaction,flow

def test_complete_authorized_mutation_flow(tmp_path):
    r,s,p,t,f=mutation_context(tmp_path); out=coordinate_engineering_runtime_execution(r,s,p,t,mutation_handoff(tmp_path),tmp_path,True,True,controlled_flow=f); assert out["status"]=="succeeded"; assert (tmp_path/"out.txt").read_text()=="hello\n"
def test_missing_operator_approval_blocks_mutation(tmp_path):
    r,s,p,t,f=mutation_context(tmp_path); f.pop("operator_approval"); out=coordinate_engineering_runtime_execution(r,s,p,t,mutation_handoff(tmp_path),tmp_path,True,True,controlled_flow=f); assert "operator_approval_not_explicit" in out["reason_codes"] and not (tmp_path/"out.txt").exists()
def test_authorization_scope_mismatch_blocks_mutation(tmp_path):
    r,s,p,t,f=mutation_context(tmp_path); f["authorization_scope"]=["other.txt"]; out=coordinate_engineering_runtime_execution(r,s,p,t,mutation_handoff(tmp_path),tmp_path,True,True,controlled_flow=f); assert "authorization_scope_mismatch" in out["reason_codes"]
