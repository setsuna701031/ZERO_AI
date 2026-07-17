from copy import deepcopy
from core.runtime.runtime_capability_bounded_decision_review_request import build_capability_bounded_decision_review_request as build,PERMISSION_FIELDS
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def proposal(c,ptype="confirm_observation",outcome="observation_confirmed"):
 q=c["decision_question"];return {"proposal_id":"proposal-1","proposal_type":ptype,"target_reference":deepcopy(q["target_reference"]),"proposed_outcome":outcome,"rationale_references":[{"artifact_id":c["decision_readiness_closure_id"],"artifact_fingerprint":c["decision_readiness_closure_fingerprint"]}],"limitations_acknowledged":deepcopy(c["limitations"])}
def permissions(**changes):p={k:False for k in PERMISSION_FIELDS};p.update(changes);return p
def review_request(root,ptype="confirm_observation",effect="none"):
 c=decision_closure(root);return build(c,proposal(c,ptype,{"confirm_observation":"observation_confirmed","request_additional_observation":"additional_observation_required","accept_no_further_action":"no_further_action","prepare_execution_plan_review":"execution_plan_review_requested"}[ptype]),requested_scope=c["decision_question"]["decision_scope"],requested_effect_class=effect,requested_permissions=permissions())
def test_review_request_boundaries(tmp_path):
 (tmp_path/"target.txt").touch();x=review_request(tmp_path);assert x["review_status"]=="accepted" and x==review_request(tmp_path)
 c=decision_closure(tmp_path);p=proposal(c);p["proposal_type"]="execute";assert build(c,p,requested_scope=c["decision_question"]["decision_scope"],requested_effect_class="none",requested_permissions=permissions())["review_status"]=="invalid"
 assert build(c,proposal(c),requested_scope=c["decision_question"]["decision_scope"],requested_effect_class="none",requested_permissions=permissions(network=True))["review_status"]=="blocked"
