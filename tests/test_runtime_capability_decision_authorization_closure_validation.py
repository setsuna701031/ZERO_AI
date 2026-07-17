from copy import deepcopy
from core.runtime.runtime_capability_decision_authorization_closure_validation import validate_capability_decision_authorization_closure as validate
from tests.test_runtime_capability_decision_authorization_closure import authorization_closure
def test_validation_fail_safe(tmp_path):
 (tmp_path/"target.txt").touch();x=authorization_closure(tmp_path);assert validate(x).valid
 for field in ("execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim","decision_executed_claim"):
  y=deepcopy(x);y[field]=True;assert not validate(y).valid
 y=deepcopy(x);y["decision_question"]={"opaque":object()};assert not validate(y).valid
