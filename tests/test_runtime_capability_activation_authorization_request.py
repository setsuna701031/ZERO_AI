from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_authorization_request import _identified,create_authorization_review_request,default_policy,review_activation_authorization
from tests.test_runtime_capability_activation_gate import admitted_chain
from core.runtime.runtime_capability_activation_gate import create_activation_gate_request,evaluate_activation_gate

def allowed_gate():
    admission,handoff,result,lease,integration,context=admitted_chain();request=create_activation_gate_request(admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context,mode="prepare_authorization_request");gate=evaluate_activation_gate(request,admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context);return gate,gate["authorization_request"]
def review(values,**kwargs):
    gate,metadata=values;request=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,**kwargs);return review_activation_authorization(request,gate_decision=gate,authorization_metadata=metadata)
def test_deterministic_review_eligibility_and_handoff():
    values=allowed_gate();one=review(values,mode="prepare_review_handoff",requested_at="one");two=review((dict(reversed(list(values[0].items()))),dict(reversed(list(values[1].items())))),mode="prepare_review_handoff",requested_at="two")
    assert one["reviewable"] and one["review_id"]==two["review_id"] and one["eligibility"]["fingerprint"]==two["eligibility"]["fingerprint"] and one["review_handoff"]["handoff_id"]==two["review_handoff"]["handoff_id"]
    assert all(one[k] is False for k in ("approval_issued","authorization_issued","token_issued","activation_performed","runtime_started","mutation_performed")) and set(one["invocation_evidence"].values())=={0}
def test_validate_only_has_no_handoff_and_gate_not_allowed_blocks():
    values=allowed_gate();validated=review(values,mode="validate_only");assert validated["review_status"]=="validated" and validated["review_handoff"] is None
    gate=deepcopy(values[0]);gate["gate_status"]="blocked";gate["allowed"]=False;gate["blockers"]=["blocked"]
    assert review((gate,values[1]))["review_status"] in {"invalid","blocked"}
def test_warnings_default_block_and_policy_can_allow():
    gate,metadata=allowed_gate();gate=deepcopy(gate);gate["warnings"]=["safe_warning"];gate.pop("decision_id");gate.pop("fingerprint")
    from core.runtime.runtime_capability_activation_gate import _identified as identify_gate
    gate=identify_gate(gate,"decision_id","capability-activation-gate-decision-",frozenset({"evaluated_at","authorization_request","authorization_request_linkage"}));metadata=deepcopy(metadata);metadata["gate_decision_linkage"]={"decision_id":gate["decision_id"],"fingerprint":gate["fingerprint"]}
    assert review((gate,metadata))["review_status"]=="blocked"
    policy=default_policy();policy.pop("policy_id");policy.pop("fingerprint");policy["allow_warnings"]=True;policy=_identified(policy,"policy_id","capability-activation-review-policy-")
    assert review((gate,metadata),policy=policy)["review_status"]=="reviewable"

@pytest.mark.parametrize("target,field",[("gate","runtime_started"),("gate","mutation_performed"),("metadata","authorization_issued"),("metadata","token_issued"),("metadata","activation_performed")])
def test_prior_execution_or_issuance_is_rejected(target,field):
    gate,metadata=allowed_gate()
    if target=="gate":
        gate=deepcopy(gate);gate[field]=True;gate.pop("decision_id");gate.pop("fingerprint")
        from core.runtime.runtime_capability_activation_gate import _identified as identify
        gate=identify(gate,"decision_id","capability-activation-gate-decision-",frozenset({"evaluated_at","authorization_request","authorization_request_linkage"}));metadata=deepcopy(metadata);metadata["gate_decision_linkage"]={"decision_id":gate["decision_id"],"fingerprint":gate["fingerprint"]}
    else:
        metadata=deepcopy(metadata);metadata[field]=True;metadata.pop("authorization_request_id");metadata.pop("fingerprint")
        from core.runtime.runtime_capability_activation_gate import _identified as identify
        metadata=identify(metadata,"authorization_request_id","capability-activation-authorization-request-",frozenset({"prepared_at","gate_decision_linkage"}))
    assert review((gate,metadata))["review_status"]=="rejected"

def test_linkage_mismatch_is_invalid_and_missing_prohibitions_rejected():
    gate,metadata=allowed_gate();wrong=deepcopy(metadata);wrong["gate_decision_linkage"]={"decision_id":"wrong","fingerprint":"wrong"}
    assert review((gate,wrong))["review_status"]=="invalid"
    unsafe=deepcopy(metadata);unsafe["prohibited_actions"]=[];unsafe.pop("authorization_request_id");unsafe.pop("fingerprint")
    from core.runtime.runtime_capability_activation_gate import _identified as identify
    unsafe=identify(unsafe,"authorization_request_id","capability-activation-authorization-request-",frozenset({"prepared_at","gate_decision_linkage"}))
    assert review((gate,unsafe))["review_status"]=="rejected"
