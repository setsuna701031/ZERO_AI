from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_authorization_request import create_authorization_review_request,review_activation_authorization
from core.runtime.runtime_capability_activation_authorization_request_validation import validate_authorization_review,validate_authorization_review_handoff,validate_authorization_review_policy,validate_authorization_review_request,validate_review_eligibility
from tests.test_runtime_capability_activation_authorization_request import allowed_gate
def artifacts(mode="prepare_review_handoff"):
    gate,metadata=allowed_gate();request=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,mode=mode);review=review_activation_authorization(request,gate_decision=gate,authorization_metadata=metadata);return request,review
def test_all_contracts_validate():
    request,review=artifacts();assert validate_authorization_review_policy(request["policy"]).valid and validate_authorization_review_request(request).valid and validate_review_eligibility(review["eligibility"]).valid and validate_authorization_review(review).valid and validate_authorization_review_handoff(review["review_handoff"]).valid
def test_tampering_sensitive_fields_and_objects_rejected():
    request,_=artifacts();bad=deepcopy(request);bad["gate_decision_fingerprint"]="wrong";assert not validate_authorization_review_request(bad).valid
    gate,metadata=allowed_gate()
    for caller in ({"token":"secret"},{"command":"approve"},{"callable":object()}):
        try:candidate=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,caller_metadata=caller)
        except (TypeError,ValueError):continue
        assert not validate_authorization_review_request(candidate).valid
def test_unknown_values_fail_closed():
    gate,metadata=allowed_gate();request=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,mode="approve");review=review_activation_authorization(request,gate_decision=gate,authorization_metadata=metadata);assert review["review_status"]=="unsupported" and not review["reviewable"]

@pytest.mark.parametrize("field,value",[("reviewer_class","arbitrary_reviewer"),("future_consumer","arbitrary_consumer")])
def test_unknown_symbolic_classes_are_unsupported(field,value):
    gate,metadata=allowed_gate();kwargs={field:value};request=create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,**kwargs);review=review_activation_authorization(request,gate_decision=gate,authorization_metadata=metadata);assert review["review_status"]=="unsupported"

def test_wrong_gate_and_authorization_fingerprints_are_invalid():
    gate,metadata=allowed_gate();bad_gate=deepcopy(gate);bad_gate["fingerprint"]="wrong";request=create_authorization_review_request(gate_decision=bad_gate,authorization_metadata=metadata);assert review_activation_authorization(request,gate_decision=bad_gate,authorization_metadata=metadata)["review_status"]=="invalid"
    bad_metadata=deepcopy(metadata);bad_metadata["fingerprint"]="wrong";request=create_authorization_review_request(gate_decision=gate,authorization_metadata=bad_metadata);assert review_activation_authorization(request,gate_decision=gate,authorization_metadata=bad_metadata)["review_status"]=="invalid"
