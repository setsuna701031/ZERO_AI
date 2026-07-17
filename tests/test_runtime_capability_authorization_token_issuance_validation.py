from copy import deepcopy
import pytest
from core.runtime.runtime_capability_authorization_token_issuance_validation import validate_capability_authorization_token_issuance as validate
from tests.test_runtime_capability_authorization_token_issuance import issue
def test_valid_safe():x=issue();y=deepcopy(x);assert validate(x).valid and not validate(None).valid and x==y
@pytest.mark.parametrize("field,value",[("schema","x"),("issuance_id","x"),("fingerprint","x"),("status","x"),("issued_at","naive"),("issuance_ttl_seconds",0),("token_signed",True),("token_issued",False)])
def test_tamper(field,value):x=issue();x[field]=value;assert not validate(x).valid
def test_linkage_secret():
 x=issue();del x["capability_profile_id"];assert not validate(x).valid
 x=issue();x["bearer_token"]="x";assert not validate(x).valid
