from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_verification import verify_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_verification_validation import validate_runtime_integration_verification
from tests.test_runtime_capability_strategy_runtime_integration_verification import chain
def _fp(v):return _identified({k:x for k,x in v.items() if k not in {"verification_id","fingerprint"}},"verification_id","capability-strategy-runtime-integration-verification-")
def test_verification_validator_binds_entire_chain():
 c,d,w=chain();v=verify_runtime_integration(c,d,w);assert validate_runtime_integration_verification(v,c,d,w).valid
 bad=deepcopy(v);bad["source_integration_wiring_fingerprint"]="other";assert not validate_runtime_integration_verification(_fp(bad),c,d,w).valid
def test_verified_status_cannot_hide_failed_evidence():
 c,d,w=chain();v=verify_runtime_integration(c,d,w);v["evidence"]["authority_absent"]=False;assert not validate_runtime_integration_verification(_fp(v)).valid
