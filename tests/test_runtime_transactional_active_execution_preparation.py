from copy import deepcopy
from core.runtime.runtime_transactional_active_execution import prepare_transactional_active_plan
from core.runtime.runtime_transactional_active_execution_preparation_validation import validate_transactional_active_plan_preparation as validate
from tests.test_runtime_active_execution_authorization import records
from tests.test_runtime_executor_admission_token import inputs,NOW
def intent():return {"intent_id":"intent-1","intent_type":"control_plane_preparation","target_descriptor":{"kind":"bounded_target"},"requested_operations":["prepare","validate"],"expected_effects":[],"prohibited_effects":["filesystem_mutation","process_creation","network_access","model_invocation","transaction_commit","external_side_effect"],"validation_requirements":[],"dry_run":True}
def test_preparation_is_pure_deterministic_and_fail_closed(tmp_path):
 plan,review,request=inputs(tmp_path);activation,auth_request=records(tmp_path);token=activation["token"]
 from core.runtime.runtime_active_execution_authorization import authorize_active_execution
 auth=authorize_active_execution(activation,auth_request,now=NOW)
 before=sorted((p.relative_to(tmp_path).as_posix(),p.read_bytes() if p.is_file() else None) for p in tmp_path.rglob("*"))
 x=prepare_transactional_active_plan(plan,review,token,activation,auth,intent(),limitations=[])
 after=sorted((p.relative_to(tmp_path).as_posix(),p.read_bytes() if p.is_file() else None) for p in tmp_path.rglob("*"))
 assert x==prepare_transactional_active_plan(plan,review,token,activation,auth,intent(),limitations=[]);assert validate(x).valid;assert x["preparation_status"]=="prepared";assert before==after
 bad=intent();bad["dry_run"]=False;assert prepare_transactional_active_plan(plan,review,token,activation,auth,bad)["preparation_status"]=="blocked"
 y=deepcopy(x);y["transaction_committed_claim"]=True;assert not validate(y).valid
