from copy import deepcopy
from core.runtime.runtime_capability_bounded_observation_request_validation import validate_capability_bounded_observation_request as validate
from tests.test_runtime_capability_bounded_observation_request import observation_request
def test_validation_and_bool_counter():
 assert validate(observation_request()).valid;x=deepcopy(observation_request());x["limits"]["max_file_bytes"]=True;assert not validate(x).valid
