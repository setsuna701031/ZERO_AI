from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_verification_closure_validation import validate_capability_activation_verification_closure as validate
from tests.test_runtime_capability_activation_verification_closure import closure
def test_all_statuses_nonmutating():
 for kind in ("activated","not_activated","blocked","failed","invalid","expired"):
  x=closure(kind);y=deepcopy(x);assert validate(x).valid and x==y
 assert not validate(None).valid
@pytest.mark.parametrize("field,value",[("schema","x"),("closure_id","x"),("fingerprint","x"),("status","x"),("verified_at","naive"),("execution_authority_granted",True),("verified",False)])
def test_tamper(field,value):x=closure();x[field]=value;assert not validate(x).valid
def test_lineage_forbidden():x=closure();del x["controlled_activation_outcome_id"];assert not validate(x).valid;x=closure();x["endpoint"]="x";assert not validate(x).valid
