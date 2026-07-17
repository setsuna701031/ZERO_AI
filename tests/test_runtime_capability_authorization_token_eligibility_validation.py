from copy import deepcopy
import pytest

from core.runtime.runtime_capability_authorization_token_eligibility_validation import validate_capability_authorization_token_eligibility
from tests.test_runtime_capability_authorization_token_eligibility import evaluate
from tests.test_runtime_capability_active_authorization import authorize, preparation


def test_all_statuses_validate():
    for source in ("approved", "denied", "blocked", "invalid"):
        assert validate_capability_authorization_token_eligibility(evaluate(authorize(preparation(source)))).valid
    assert validate_capability_authorization_token_eligibility(evaluate(authorize(authorized_at="2000-01-01T00:00:00Z"))).valid


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("status", "unknown"), ("eligibility_id", "wrong"),
    ("fingerprint", "wrong"), ("evaluated_at", "naive"), ("authorized_at", "naive"),
    ("expires_at", "naive"), ("authorization_ttl_seconds", 0),
    ("active_authorization_id", None), ("active_authorization_preparation_id", None),
    ("authorization_review_decision_id", None), ("review_policy_id", None),
    ("capability_profile_id", None), ("eligible", False), ("blocked", True),
    ("token_eligibility_confirmed", False), ("token_preparation_created", True),
    ("token_created", True), ("token_issued", True), ("token_signed", True),
    ("runtime_activated", True), ("execution_authority_granted", True),
    ("reasons", "bad"), ("errors", ["Bad code"]),
])
def test_invalid_records_fail(field, value):
    item = deepcopy(evaluate()); item[field] = value
    assert not validate_capability_authorization_token_eligibility(item).valid


def test_extra_authority_field_nonmapping_and_no_mutation():
    item = evaluate(); item["token_secret"] = "secret"; saved = deepcopy(item)
    assert not validate_capability_authorization_token_eligibility(item).valid and item == saved
    assert not validate_capability_authorization_token_eligibility([]).valid


def test_noneligible_confirmation_fails():
    item = evaluate(authorize(preparation("denied"))); item["token_eligibility_confirmed"] = True
    assert not validate_capability_authorization_token_eligibility(item).valid
