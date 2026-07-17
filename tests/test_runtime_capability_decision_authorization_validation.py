from copy import deepcopy
from core.runtime.runtime_capability_decision_authorization_validation import validate_capability_decision_authorization as validate
from tests.test_runtime_capability_decision_authorization import authorization
def test_validation_claims_and_mapping(tmp_path):
 (tmp_path/"target.txt").touch();x=authorization(tmp_path);assert validate(x).valid;y=deepcopy(x);y["authorized_next_stage"]="execution_plan_review_admission";assert not validate(y).valid;y=deepcopy(x);y["external_execution_authorization_claim"]=True;assert not validate(y).valid
