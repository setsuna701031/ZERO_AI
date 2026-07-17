from copy import deepcopy
from core.runtime.runtime_capability_safe_target_resolution_validation import validate_capability_safe_target_resolution as validate
from tests.test_runtime_capability_safe_target_resolution import resolution
def test_validation_and_tamper(tmp_path):
 (tmp_path/"target.txt").touch();x=resolution(tmp_path);assert validate(x).valid;y=deepcopy(x);y["containment_verified"]=False;assert not validate(y).valid
