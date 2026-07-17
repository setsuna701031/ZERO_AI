from copy import deepcopy
import pytest
from core.runtime.runtime_capability_controlled_activation_preparation_validation import validate_capability_controlled_activation_preparation as validate
from tests.test_runtime_capability_controlled_activation_preparation import preparation
def test_valid_nonmutating():x=preparation();y=deepcopy(x);assert validate(x).valid and x==y and not validate(None).valid
@pytest.mark.parametrize("field,value",[("schema","x"),("preparation_id","x"),("fingerprint","x"),("prepared_at","naive"),("activation_attempted",True),("prepared",False)])
def test_tamper(field,value):x=preparation();x[field]=value;assert not validate(x).valid
def test_missing_forbidden():x=preparation();del x["runtime_activation_admission_id"];assert not validate(x).valid
