from copy import deepcopy
from core.runtime.runtime_capability_read_only_observation_result_validation import validate_capability_read_only_observation_result as validate
from tests.test_runtime_capability_read_only_observation_result import result
def test_validation_side_effect_and_bool(tmp_path):
 (tmp_path/"target.txt").touch();x=result(tmp_path);assert validate(x).valid;y=deepcopy(x);y["side_effects_performed"]=["write"];assert not validate(y).valid;y=deepcopy(x);y["bytes_read"]=True;assert not validate(y).valid
