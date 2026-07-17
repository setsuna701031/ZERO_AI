from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_closure_validation import validate_capability_observation_evidence_closure as validate
from tests.test_runtime_capability_observation_evidence_closure import closure
def test_validation_completion_and_tamper(tmp_path):
 (tmp_path/"target.txt").touch();x=closure(tmp_path);assert validate(x).valid;y=deepcopy(x);y["execution_completion_claim"]=True;assert not validate(y).valid
