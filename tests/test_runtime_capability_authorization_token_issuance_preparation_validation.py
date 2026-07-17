from copy import deepcopy
import pytest
from core.runtime.runtime_capability_authorization_token_issuance_preparation_validation import validate_capability_authorization_token_issuance_preparation as validate
from tests.test_runtime_capability_authorization_token_issuance_preparation import prepare
def test_valid_nonmapping_and_immutability():
 x=prepare();saved=deepcopy(x);assert validate(x).valid and not validate(None).valid and x==saved
@pytest.mark.parametrize("field,value",[("schema","x"),("preparation_id","x"),("fingerprint","0"*64),("status","x"),("prepared_at","naive"),("token_issued",True),("issuance_preparation_created",False)])
def test_tamper(field,value):x=prepare();x[field]=value;assert not validate(x).valid
def test_missing_and_secret():
 x=prepare();del x["review_policy_id"];assert not validate(x).valid
 x=prepare();x["token_secret"]="x";assert not validate(x).valid
