from copy import deepcopy
from core.runtime.runtime_capability_runtime_activation_eligibility_validation import validate_capability_runtime_activation_eligibility as validate
from tests.test_runtime_capability_runtime_activation_eligibility import eligibility
def test_validation():
 x=eligibility();y=deepcopy(x);assert validate(x).valid and x==y and not validate(None).valid
 for n,v in (("schema","x"),("fingerprint","x"),("runtime_activated",True)):
  x=eligibility();x[n]=v;assert not validate(x).valid
