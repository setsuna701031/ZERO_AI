from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from core.runtime.runtime_capability_executor_adapter_admission_validation import validate_capability_executor_adapter_admission as validate
def test_validation_tamper():x=adapter_admission();assert validate(x).valid;x["request_fingerprint"]="x";assert not validate(x).valid
