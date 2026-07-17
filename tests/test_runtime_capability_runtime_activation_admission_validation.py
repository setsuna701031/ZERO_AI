from core.runtime.runtime_capability_runtime_activation_admission_validation import validate_capability_runtime_activation_admission as validate
from tests.test_runtime_capability_runtime_activation_admission import admission
def test_validation():
 assert validate(admission()).valid and not validate(None).valid;x=admission();x["admission_ttl_seconds"]=1;assert not validate(x).valid
