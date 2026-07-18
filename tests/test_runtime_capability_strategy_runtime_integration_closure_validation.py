from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_closure import close_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_closure_validation import validate_runtime_integration_closure
from tests.test_runtime_capability_strategy_runtime_integration_closure import verification
def _fp(v):return _identified({k:x for k,x in v.items() if k not in {"closure_id","fingerprint"}},"closure_id","capability-strategy-runtime-integration-closure-")
def test_closure_validator_binds_verification_and_rejects_refingerprinted_tamper():
 v=verification();c=close_runtime_integration(v);assert validate_runtime_integration_closure(c,v).valid
 bad=deepcopy(c);bad["closure_payload"]["passive_integration_payload"]["target_bootstrap_stage"]="consumer";assert not validate_runtime_integration_closure(_fp(bad),v).valid
def test_closure_rejects_authority_and_unknown_fields():
 c=close_runtime_integration(verification());c["boundary"]["authority_granted"]=True;assert not validate_runtime_integration_closure(_fp(c)).valid
 c=close_runtime_integration(verification());c["extra"]=1;assert not validate_runtime_integration_closure(c).valid
