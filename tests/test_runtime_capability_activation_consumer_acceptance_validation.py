from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_consumer_acceptance_validation import validate_capability_activation_consumer_acceptance as validate
from tests.test_runtime_capability_activation_consumer_acceptance import acceptance
def test_valid_nonmutating():x=acceptance();y=deepcopy(x);assert validate(x).valid and x==y and not validate(None).valid
@pytest.mark.parametrize("field,value",[("schema","x"),("acceptance_id","x"),("fingerprint","x"),("accepted_at","naive"),("activation_command_created",True),("accepted",False)])
def test_tamper(field,value):x=acceptance();x[field]=value;assert not validate(x).valid
def test_missing_lineage_forbidden():
 x=acceptance();del x["capability_profile_id"];assert not validate(x).valid
 for n in ("command","endpoint","stdout","private_key"):
  x=acceptance();x[n]="x";assert not validate(x).valid
