from core.runtime.runtime_capability_runtime_activation_admission_handoff_validation import validate_capability_runtime_activation_admission_handoff as validate
from tests.test_runtime_capability_runtime_activation_admission_handoff import admission_handoff
def test_validation():
 assert validate(admission_handoff()).valid and not validate({}).valid;x=admission_handoff();x["endpoint"]="x";assert not validate(x).valid
