from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
from core.runtime.runtime_capability_executor_bridge_verification_closure_validation import validate_capability_executor_bridge_verification_closure as validate
def test_validation():x=bridge_closure();assert validate(x).valid;x["bridge_closure_fingerprint"]="x";assert not validate(x).valid
