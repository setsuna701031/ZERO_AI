from copy import deepcopy
from core.runtime.runtime_capability_decision_review_eligibility_validation import validate_capability_decision_review_eligibility as validate
from tests.test_runtime_capability_decision_review_eligibility import eligibility
def test_validation_checks(tmp_path):
 (tmp_path/"target.txt").touch();x=eligibility(tmp_path);assert validate(x).valid;y=deepcopy(x);y["scope_checks"]={"valid":False};assert not validate(y).valid;y=deepcopy(x);y["eligibility_status"]="unknown";assert not validate(y).valid
