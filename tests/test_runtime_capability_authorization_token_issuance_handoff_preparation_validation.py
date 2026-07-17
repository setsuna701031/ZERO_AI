from copy import deepcopy
import pytest
from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation_validation import validate_capability_authorization_token_issuance_handoff_preparation as validate
from tests.test_runtime_capability_authorization_token_issuance_handoff_preparation import prepare_handoff
def test_valid_safe():x=prepare_handoff();y=deepcopy(x);assert validate(x).valid and not validate(None).valid and x==y
@pytest.mark.parametrize("field,value",[("schema","x"),("handoff_preparation_id","x"),("fingerprint","x"),("status","x"),("prepared_at","naive"),("issuance_ttl_seconds",0),("token_handed_off",True),("handoff_preparation_created",False)])
def test_tamper(field,value):x=prepare_handoff();x[field]=value;assert not validate(x).valid
def test_linkage_transport():
 x=prepare_handoff();del x["token_issuance_id"];assert not validate(x).valid
 x=prepare_handoff();x["endpoint"]="x";assert not validate(x).valid
