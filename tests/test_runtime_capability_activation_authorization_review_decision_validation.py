from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_authorization_review_decision_validation import validate_capability_activation_authorization_review_decision
from tests.test_runtime_capability_activation_authorization_review_decision import build

def test_valid_decisions_validate():
    for name in ("approved","denied","blocked","invalid"):
        assert validate_capability_activation_authorization_review_decision(build(decision=name)).valid

@pytest.mark.parametrize("field,value", [("schema","wrong"),("decision","unknown"),("reviewer_id",""),("reviewed_at","not-time"),("approved",False),("token_issued",True),("runtime_activated",True),("execution_authority_granted",True),("active_authorization_created",True),("authorization_review_request_id",None)])
def test_forged_or_unsafe_records_are_rejected(field,value):
    record=deepcopy(build()); record[field]=value
    assert not validate_capability_activation_authorization_review_decision(record).valid

def test_non_mapping_is_rejected_without_exception():
    assert not validate_capability_activation_authorization_review_decision([]).valid

