from copy import deepcopy
from core.runtime.runtime_capability_activation_authorization_request import create_authorization_review_request
from core.runtime.runtime_capability_activation_authorization_review_decision import _hash as decision_hash, build_capability_activation_authorization_review_decision
from core.runtime.runtime_capability_active_authorization_eligibility import evaluate_capability_active_authorization_eligibility
from tests.test_runtime_capability_activation_authorization_request import allowed_gate

NOW="2026-07-17T06:00:00Z"
def decision(status="approved"):
    gate,metadata=allowed_gate();request=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata)
    value=build_capability_activation_authorization_review_decision(authorization_review_request=request,decision=status,reviewer_id="reviewer",decision_reason="review complete",reviewed_at=NOW)
    for prefix in ("review_handoff","review","eligibility","activation_proposal","capability_profile","capability_strategy"):
        value[prefix+"_id"]=prefix+"-id";value[prefix+"_fingerprint"]=(prefix[0]*64)
    payload={k:v for k,v in value.items() if k not in {"decision_id","fingerprint"}};fp=decision_hash(payload)
    value["decision_id"]="capability-activation-authorization-review-decision-"+fp[:24];value["fingerprint"]=fp
    return value
def evaluate(value=None,**kwargs):return evaluate_capability_active_authorization_eligibility(decision() if value is None else value,evaluated_at=kwargs.get("evaluated_at",NOW))

def test_decision_status_mapping_and_no_authority():
    expected={"approved":"eligible","denied":"ineligible","blocked":"blocked","invalid":"invalid"}
    for source,target in expected.items():
        result=evaluate(decision(source));assert result["status"]==target and result[target]
        assert all(result[k] is False for k in ("active_authorization_created","token_issued","runtime_activated","execution_authority_granted"))
def test_stable_identity_timestamp_and_detachment():
    source=decision();saved=deepcopy(source);one=evaluate(source);two=evaluate(dict(reversed(list(source.items()))))
    source["decision_reason"]="changed"
    assert one==two and saved!=source
    assert evaluate(saved,evaluated_at="2026-07-17T07:00:00Z")["fingerprint"]!=one["fingerprint"]
def test_linkages_are_preserved():
    source=decision();result=evaluate(source)
    for output,input_name in (("authorization_review_request","authorization_review_request"),("review_policy","review_policy"),("review_eligibility","eligibility"),("capability_profile","capability_profile"),("capability_strategy","capability_strategy"),("activation_proposal","activation_proposal")):
        assert result[output+"_id"]==source[input_name+"_id"] and result[output+"_fingerprint"]==source[input_name+"_fingerprint"]
def test_malformed_fingerprint_and_authority_fail_closed():
    assert evaluate({})["status"]=="invalid"
    forged=decision();forged["fingerprint"]="0"*64;assert evaluate(forged)["status"]=="invalid"
    authority=decision();authority["token_issued"]=True;assert evaluate(authority)["status"]=="invalid" and "authority_flag_violation" in evaluate(authority)["errors"]
