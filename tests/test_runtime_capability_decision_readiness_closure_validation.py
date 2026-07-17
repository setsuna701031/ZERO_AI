from copy import deepcopy
from core.runtime.runtime_capability_decision_readiness_closure_validation import validate_capability_decision_readiness_closure as validate
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def test_validation_claims_limitations_and_tamper(tmp_path):
 (tmp_path/"target.txt").touch();x=decision_closure(tmp_path);assert validate(x).valid;y=deepcopy(x);y["decision_made_claim"]=True;assert not validate(y).valid;y=deepcopy(x);y["limitations"]=[object()];assert not validate(y).valid
