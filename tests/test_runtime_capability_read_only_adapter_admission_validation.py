from copy import deepcopy
from core.runtime.runtime_capability_read_only_adapter_admission_validation import validate_capability_read_only_adapter_admission as validate
from tests.test_runtime_capability_read_only_adapter_admission import admission
def test_validation_and_tamper():
 assert validate(admission()).valid;x=deepcopy(admission());x["adapter_mode"]="live";assert not validate(x).valid
