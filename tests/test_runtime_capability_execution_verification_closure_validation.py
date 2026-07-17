from tests.test_runtime_capability_execution_verification_closure import closure
from core.runtime.runtime_capability_execution_verification_closure_validation import validate_capability_execution_verification_closure as validate
def test_validation():
    x=closure();assert validate(x).valid;x["closed"]=False;assert not validate(x).valid
