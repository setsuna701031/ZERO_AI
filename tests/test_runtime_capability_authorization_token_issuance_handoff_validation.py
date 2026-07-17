from copy import deepcopy
import pytest
from core.runtime.runtime_capability_authorization_token_issuance_handoff_validation import validate_capability_authorization_token_issuance_handoff as validate
from tests.test_runtime_capability_authorization_token_issuance_handoff import handoff
def test_valid_safe():x=handoff();y=deepcopy(x);assert validate(x).valid and not validate(None).valid and x==y
@pytest.mark.parametrize("field,value",[("schema","x"),("handoff_id","x"),("fingerprint","x"),("status","x"),("handed_off_at","naive"),("recipient_id","https://host"),("token_handed_off",False),("handoff_delivered",True)])
def test_tamper(field,value):x=handoff();x[field]=value;assert not validate(x).valid
def test_linkage_secret_transport():
 x=handoff();del x["token_issuance_handoff_preparation_id"];assert not validate(x).valid
 for n in ("token_secret","endpoint"):
  x=handoff();x[n]="x";assert not validate(x).valid
