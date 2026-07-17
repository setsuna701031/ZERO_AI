from copy import deepcopy
import pytest
from core.runtime.runtime_capability_active_authorization_validation import validate_capability_active_authorization
from tests.test_runtime_capability_active_authorization import authorize, preparation

def test_all_results_validate():
    for source in ("approved", "denied", "blocked", "invalid"): assert validate_capability_active_authorization(authorize(preparation(source))).valid
    assert validate_capability_active_authorization(authorize(authorized_at="2000-01-01T00:00:00Z")).valid

@pytest.mark.parametrize("field,value", [("schema", "wrong"), ("status", "unknown"), ("authorization_id", "wrong"), ("fingerprint", "wrong"), ("authorized_at", "naive"), ("expires_at", "naive"), ("authorization_ttl_seconds", 0), ("active_authorization_preparation_id", None), ("active_authorization_eligibility_id", None), ("authorization_review_decision_id", None), ("review_policy_id", None), ("capability_profile_id", None), ("active", False), ("blocked", True), ("active_authorization_created", False), ("authorization_granted", False), ("token_issued", True), ("runtime_activated", True), ("execution_authority_granted", True), ("reasons", "bad"), ("errors", ["Bad code"])])
def test_invalid_records_fail(field, value):
    item = deepcopy(authorize()); item[field] = value; assert not validate_capability_active_authorization(item).valid

def test_nonactive_authority_forgery_extra_field_and_nonmapping_fail():
    item = authorize(preparation("denied")); item["authorization_granted"] = True; assert not validate_capability_active_authorization(item).valid
    item = authorize(); item["may_execute"] = True; saved = deepcopy(item)
    assert not validate_capability_active_authorization(item).valid and item == saved
    assert not validate_capability_active_authorization([]).valid
