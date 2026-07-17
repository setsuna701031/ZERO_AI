from copy import deepcopy
from core.runtime.runtime_capability_decision_transaction_preparation import prepare_capability_decision_transaction as build
from core.runtime.runtime_capability_prepared_transaction_handoff_validation import validate_capability_prepared_transaction_handoff
from core.runtime.runtime_capability_transaction_preparation_integration_closure_validation import validate_capability_transaction_preparation_integration_closure
from core.runtime.runtime_capability_decision_review_eligibility import build_capability_decision_review_eligibility
from core.runtime.runtime_capability_decision_policy_evaluation import build_capability_decision_policy_evaluation
from core.runtime.runtime_capability_decision_authorization import build_capability_decision_authorization
from core.runtime.runtime_capability_decision_authorization_closure import close_capability_decision_authorization
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_observation_evidence_closure import closure as observation_closure
from tests.test_runtime_apply_execution_plan_builder import proposal,lineage
NOW="2026-07-10T12:00:00+00:00"
def decision(root):
 c=decision_closure(root);r=review_request(root,"prepare_execution_plan_review","future_execution_plan_review");e=build_capability_decision_review_eligibility(r,c);p=build_capability_decision_policy_evaluation(e,r,c);a=build_capability_decision_authorization(p,e,r,c);return close_capability_decision_authorization(authority(),request(),observation_closure(root),c,r,e,p,a)
def intent():return {"intent_id":"intent-1","intent_type":"control_plane_preparation","target_descriptor":{"relative_target":"target.txt"},"requested_operations":["prepare","validate"],"expected_effects":[],"prohibited_effects":["filesystem_mutation","process_creation","network_access","model_invocation","transaction_commit","external_side_effect"],"validation_requirements":[],"dry_run":True}
def inputs(root):
 pp,ap,ad=lineage(proposal());rv={"review_id":"review-1","operator_id":"operator-1","decision":"approved","reviewed_at":NOW,"expires_at":"2026-07-10T12:30:00+00:00"};oq={"request_id":"operator-request-1","requested_at":NOW,"expires_at":"2026-07-10T12:20:00+00:00"};az={"authorization_id":"active-auth-1","decision":"authorized","authorized_at":NOW,"expires_at":"2026-07-10T12:10:00+00:00","acknowledged_risks":["manual_active_boundary_required"],"acknowledged_no_automatic_commit":True,"acknowledged_manual_rollback_authority":True};return dict(decision_closure=decision(root),execution_intent=intent(),proposal=pp,approval_record=ap,admission_record=ad,operator_review=rv,operator_execution_request=oq,active_authorization_request=az,target_root=root,now=NOW)
def test_complete_zero_side_effect_integration(tmp_path):
 (tmp_path/"target.txt").write_bytes(b"unchanged");before=[(p.relative_to(tmp_path).as_posix(),p.read_bytes() if p.is_file() else None) for p in tmp_path.rglob("*")];x=build(**inputs(tmp_path));after=[(p.relative_to(tmp_path).as_posix(),p.read_bytes() if p.is_file() else None) for p in tmp_path.rglob("*")];assert before==after;assert x["transaction_preparation"]["prepared"];assert validate_capability_prepared_transaction_handoff(x["prepared_handoff"]).valid;assert validate_capability_transaction_preparation_integration_closure(x["integration_closure"]).valid;assert x["integration_closure"]["verification_status"]=="verified_closed"
def test_intent_and_decision_fail_closed(tmp_path):
 (tmp_path/"target.txt").touch();v=inputs(tmp_path);v["execution_intent"]["dry_run"]=False;assert build(**v)["integration_closure"]["verification_status"]=="blocked";v=inputs(tmp_path);v["decision_closure"]["authorized_next_stage"]="invalid";assert build(**v)["transaction_preparation"]["prepared"] is False
