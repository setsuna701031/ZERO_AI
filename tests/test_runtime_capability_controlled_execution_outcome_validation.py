from tests.test_runtime_capability_controlled_execution_outcome import outcome
from core.runtime.runtime_capability_controlled_execution_outcome_validation import validate_capability_controlled_execution_outcome as validate
def test_validation():
    x=outcome();assert validate(x).valid;x["request_id"]="wrong";assert not validate(x).valid
