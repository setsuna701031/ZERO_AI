from copy import deepcopy
from core.runtime.runtime_capability_decision_policy_evaluation_validation import validate_capability_decision_policy_evaluation as validate
from tests.test_runtime_capability_decision_policy_evaluation import policy
def test_validation_fixed_policy(tmp_path):
 (tmp_path/"target.txt").touch();x=policy(tmp_path);assert validate(x).valid;y=deepcopy(x);y["policy_id"]="other";assert not validate(y).valid;y=deepcopy(x);y["policy_version"]=True;assert not validate(y).valid;y=deepcopy(x);y["approved_permissions"]["filesystem_write"]=True;assert not validate(y).valid
