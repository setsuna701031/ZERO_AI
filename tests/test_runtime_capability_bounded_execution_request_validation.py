from tests.test_runtime_capability_bounded_execution_request import request
from core.runtime.runtime_capability_bounded_execution_request_validation import validate_capability_bounded_execution_request as validate
def test_validation():
    x=request();assert validate(x).valid;x["fingerprint"]="0"*64;assert not validate(x).valid
