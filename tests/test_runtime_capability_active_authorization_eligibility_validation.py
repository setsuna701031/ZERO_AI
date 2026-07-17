from copy import deepcopy
import pytest
from core.runtime.runtime_capability_active_authorization_eligibility_validation import validate_capability_active_authorization_eligibility
from tests.test_runtime_capability_active_authorization_eligibility import decision,evaluate

def test_all_canonical_results_validate():
    for status in ("approved","denied","blocked","invalid"):assert validate_capability_active_authorization_eligibility(evaluate(decision(status))).valid
@pytest.mark.parametrize("field,value",[("schema","wrong"),("status","unknown"),("eligibility_id","wrong"),("fingerprint","wrong"),("evaluated_at","naive"),("authorization_review_decision_id",None),("authorization_review_request_id",None),("review_policy_id",None),("capability_profile_id",None),("eligible",False),("blocked",True),("active_authorization_created",True),("token_issued",True),("runtime_activated",True),("execution_authority_granted",True),("reasons","bad"),("errors",["Bad code"])])
def test_invalid_or_unsafe_records_fail(field,value):
    item=deepcopy(evaluate());item[field]=value;assert not validate_capability_active_authorization_eligibility(item).valid
def test_extra_authority_field_and_non_mapping_fail_without_mutation():
    item=evaluate();item["authorized"]=True;saved=deepcopy(item)
    assert not validate_capability_active_authorization_eligibility(item).valid and item==saved
    assert not validate_capability_active_authorization_eligibility([]).valid
