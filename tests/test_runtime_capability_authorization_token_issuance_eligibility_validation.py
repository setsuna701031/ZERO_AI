from copy import deepcopy
import pytest

from core.runtime.runtime_capability_authorization_token_issuance_eligibility_validation import (
    validate_capability_authorization_token_issuance_eligibility,
)
from tests.test_runtime_capability_authorization_token_issuance_eligibility import evaluate, token_with_status

def test_all_canonical_statuses_and_non_mapping():
    assert validate_capability_authorization_token_issuance_eligibility(evaluate()).valid
    for status in ("not_created", "blocked", "invalid", "expired"):
        assert validate_capability_authorization_token_issuance_eligibility(evaluate(token_with_status(status))).valid
    assert not validate_capability_authorization_token_issuance_eligibility(None).valid

@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("status", "unknown"), ("eligibility_id", "wrong"),
    ("fingerprint", "0" * 64), ("evaluated_at", "naive"),
    ("token_created_at", "naive"), ("token_expires_at", "naive"),
    ("token_ttl_seconds", 0), ("issuance_eligibility_confirmed", False),
    ("issuance_preparation_created", True), ("token_issued", True),
    ("token_signed", True), ("token_handed_off", True),
    ("token_material_created", True), ("runtime_activated", True),
    ("execution_authority_granted", True),
])
def test_tampering_is_rejected(field, value):
    item = deepcopy(evaluate()); item[field] = value
    assert not validate_capability_authorization_token_issuance_eligibility(item).valid

def test_linkage_secret_flags_and_structures_are_rejected_without_mutation():
    for field in ("authorization_token_id", "authorization_token_preparation_id", "authorization_token_eligibility_id", "active_authorization_id", "authorization_review_decision_id", "authorization_review_request_id", "review_policy_id", "capability_profile_id"):
        item = deepcopy(evaluate()); del item[field]
        assert not validate_capability_authorization_token_issuance_eligibility(item).valid
    for field in ("token_value", "token_secret", "signature", "bearer", "credential", "may_execute"):
        item = deepcopy(evaluate()); item[field] = "forged"
        assert not validate_capability_authorization_token_issuance_eligibility(item).valid
    for field, value in (("reasons", "bad"), ("errors", ["UPPER"])):
        item = deepcopy(evaluate()); item[field] = value
        assert not validate_capability_authorization_token_issuance_eligibility(item).valid
    original = evaluate(); saved = deepcopy(original)
    validate_capability_authorization_token_issuance_eligibility(original)
    assert original == saved
