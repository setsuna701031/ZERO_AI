from tests.test_runtime_capability_execution_session_admission import admission
from core.runtime.runtime_capability_execution_session_admission_validation import validate_capability_execution_session_admission as validate
def test_validation_and_tamper():
    x=admission();assert validate(x).valid;x["status"]="blocked";assert not validate(x).valid
