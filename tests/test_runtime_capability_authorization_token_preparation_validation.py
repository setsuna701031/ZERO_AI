from copy import deepcopy
import pytest

from core.runtime.runtime_capability_authorization_token_preparation_validation import validate_capability_authorization_token_preparation
from tests.test_runtime_capability_authorization_token_preparation import prepare
from tests.test_runtime_capability_authorization_token_eligibility import evaluate
from tests.test_runtime_capability_active_authorization import authorize, preparation


def test_all_statuses_validate():
    for source in ("approved", "denied", "blocked", "invalid"):
        assert validate_capability_authorization_token_preparation(prepare(evaluate(authorize(preparation(source))))).valid
    assert validate_capability_authorization_token_preparation(prepare(evaluate(authorize(authorized_at="2000-01-01T00:00:00Z")))).valid


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("status", "unknown"), ("preparation_id", "wrong"),
    ("fingerprint", "wrong"), ("prepared_at", "naive"),
    ("eligibility_evaluated_at", "naive"), ("authorized_at", "naive"),
    ("expires_at", "naive"), ("authorization_ttl_seconds", 0), ("authorization_ttl_seconds", 299),
    ("authorization_token_eligibility_id", None), ("active_authorization_id", None),
    ("authorization_review_decision_id", None), ("authorization_review_request_id", None),
    ("review_policy_id", None), ("capability_profile_id", None),
    ("prepared", False), ("blocked", True), ("token_preparation_created", False),
    ("token_created", True), ("token_issued", True), ("token_signed", True),
    ("token_material_created", True), ("runtime_activated", True),
    ("execution_authority_granted", True), ("reasons", "bad"), ("errors", ["Bad code"]),
])
def test_invalid_records_fail(field, value):
    item = deepcopy(prepare()); item[field] = value
    assert not validate_capability_authorization_token_preparation(item).valid


def test_extra_token_or_authority_field_nonmapping_and_no_mutation():
    for field in ("token_secret", "may_execute"):
        item = prepare(); item[field] = "forged"; saved = deepcopy(item)
        assert not validate_capability_authorization_token_preparation(item).valid and item == saved
    assert not validate_capability_authorization_token_preparation([]).valid


def test_nonprepared_creation_flag_fails():
    item = prepare(evaluate(authorize(preparation("denied"))))
    item["token_preparation_created"] = True
    assert not validate_capability_authorization_token_preparation(item).valid
