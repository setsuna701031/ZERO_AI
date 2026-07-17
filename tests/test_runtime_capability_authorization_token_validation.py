from copy import deepcopy
import pytest

from core.runtime.runtime_capability_authorization_token_validation import validate_capability_authorization_token
from tests.test_runtime_capability_authorization_token import create

def test_valid_record_and_non_mapping():
    assert validate_capability_authorization_token(create()).valid
    assert not validate_capability_authorization_token(None).valid

@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("status", "unknown"), ("token_id", "wrong"),
    ("fingerprint", "0" * 64), ("token_created", False),
    ("token_material_created", True), ("token_signed", True), ("token_issued", True),
    ("token_handed_off", True), ("runtime_activated", True), ("execution_authority_granted", True),
])
def test_tampering_is_rejected(field, value):
    item = deepcopy(create()); item[field] = value
    assert not validate_capability_authorization_token(item).valid

def test_secret_and_linkage_tampering_is_rejected():
    for field in ("token_value", "token_secret", "bearer_token", "signature", "credential"):
        item = deepcopy(create()); item[field] = "forged"
        assert not validate_capability_authorization_token(item).valid
    item = deepcopy(create()); del item["review_policy_id"]
    assert not validate_capability_authorization_token(item).valid
