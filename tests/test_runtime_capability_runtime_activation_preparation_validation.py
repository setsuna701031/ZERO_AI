from core.runtime.runtime_capability_runtime_activation_preparation_validation import validate_capability_runtime_activation_preparation as validate
from tests.test_runtime_capability_runtime_activation_preparation import preparation
def test_validation():
 assert validate(preparation()).valid and not validate({}).valid;x=preparation();x["runtime_admission_created"]=True;assert not validate(x).valid
