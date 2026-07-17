from copy import deepcopy
import pytest

from core.runtime.runtime_capability_active_authorization_preparation_validation import validate_capability_active_authorization_preparation
from tests.test_runtime_capability_active_authorization_preparation import eligibility, prepare


def test_all_canonical_results_validate():
    for status in ("approved", "denied", "blocked", "invalid"):
        assert validate_capability_active_authorization_preparation(prepare(eligibility(status))).valid


@pytest.mark.parametrize("field,value", [("schema", "wrong"), ("status", "unknown"), ("preparation_id", "wrong"), ("fingerprint", "wrong"), ("prepared_at", "naive"), ("active_authorization_eligibility_id", None), ("authorization_review_decision_id", None), ("authorization_review_request_id", None), ("review_policy_id", None), ("capability_profile_id", None), ("prepared", False), ("blocked", True), ("active_authorization_created", True), ("authorization_granted", True), ("token_issued", True), ("runtime_activated", True), ("execution_authority_granted", True), ("reasons", "bad"), ("errors", ["Bad code"])])
def test_invalid_or_unsafe_records_fail(field, value):
    item = deepcopy(prepare()); item[field] = value
    assert not validate_capability_active_authorization_preparation(item).valid


def test_extra_authority_field_and_non_mapping_fail_without_mutation():
    item = prepare(); item["authorized"] = True; saved = deepcopy(item)
    assert not validate_capability_active_authorization_preparation(item).valid and item == saved
    assert not validate_capability_active_authorization_preparation([]).valid
