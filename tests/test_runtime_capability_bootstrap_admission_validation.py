from __future__ import annotations
from copy import deepcopy
from core.runtime.runtime_capability_bootstrap_admission import admit_capability_bootstrap,create_admission_request,default_policy
from core.runtime.runtime_capability_bootstrap_admission_validation import validate_activation_handoff,validate_admission_decision,validate_admission_policy,validate_admission_request
from tests.test_runtime_capability_bootstrap_admission import chain
def test_contracts_validate():
 r,l,i,c=chain();q=create_admission_request(consumption_result=r,lease=l,integration=i,runtime_context=c,mode="prepare_activation_handoff");d=admit_capability_bootstrap(q,consumption_result=r,lease=l,integration=i,runtime_context=c)
 assert validate_admission_policy(default_policy()).valid and validate_admission_request(q).valid and validate_admission_decision(d).valid and validate_activation_handoff(d["activation_handoff"]).valid
def test_sensitive_metadata_and_tampering_rejected():
 r,l,i,c=chain()
 for m in ({"token":"x"},{"command":"run"}):assert not validate_admission_request(create_admission_request(consumption_result=r,lease=l,integration=i,runtime_context=c,metadata=m)).valid
 for m in ({"callback":lambda:None},{"provider":object()}):
  try:create_admission_request(consumption_result=r,lease=l,integration=i,runtime_context=c,metadata=m)
  except TypeError:pass
  else:raise AssertionError("unsafe object serialized")
 q=create_admission_request(consumption_result=r,lease=l,integration=i,runtime_context=c,mode="prepare_activation_handoff");d=admit_capability_bootstrap(q,consumption_result=r,lease=l,integration=i,runtime_context=c)
 for k in ("runtime_started","authorization_issued","token_issued"):
  x=deepcopy(d);x[k]=True;assert not validate_admission_decision(x).valid
