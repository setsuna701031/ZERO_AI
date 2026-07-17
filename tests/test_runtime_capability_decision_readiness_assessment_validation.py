from copy import deepcopy
from core.runtime.runtime_capability_decision_readiness_assessment_validation import validate_capability_decision_readiness_assessment as validate
from tests.test_runtime_capability_decision_readiness_assessment import readiness
def test_validation_forbidden_claim(tmp_path):
 (tmp_path/"target.txt").touch();x=readiness(tmp_path);assert validate(x).valid;y=deepcopy(x);y["authorization_claim"]=True;assert not validate(y).valid
