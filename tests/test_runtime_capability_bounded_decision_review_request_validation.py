from copy import deepcopy
from core.runtime.runtime_capability_bounded_decision_review_request_validation import validate_capability_bounded_decision_review_request as validate
from tests.test_runtime_capability_bounded_decision_review_request import review_request
def test_validation_tampering(tmp_path):
 (tmp_path/"target.txt").touch();x=review_request(tmp_path);assert validate(x).valid;y=deepcopy(x);y["decision_review_request_fingerprint"]="bad";assert not validate(y).valid;y=deepcopy(x);y["requested_permissions"]["network"]=True;assert not validate(y).valid;y=deepcopy(x);y["decision_proposal"]["proposal_id"]="";assert not validate(y).valid
