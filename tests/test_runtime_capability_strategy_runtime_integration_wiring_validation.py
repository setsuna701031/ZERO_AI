from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_wiring import wire_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_wiring_validation import validate_runtime_integration_wiring
from tests.test_runtime_capability_strategy_runtime_integration_wiring import decision
def _fp(v):return _identified({k:x for k,x in v.items() if k not in {"wiring_id","fingerprint"}},"wiring_id","capability-strategy-runtime-integration-wiring-")
def test_wiring_validator_source_binding_and_tamper_rejection():
 d=decision();w=wire_runtime_integration(d);assert validate_runtime_integration_wiring(w,d).valid
 bad=deepcopy(w);bad["wiring_payload"]["target_bootstrap_stage"]="consumer";assert not validate_runtime_integration_wiring(_fp(bad),d).valid
 bad=deepcopy(w);bad["source_decision_id"]="changed";assert not validate_runtime_integration_wiring(_fp(bad),d).valid
def test_wiring_validator_rejects_live_material():
 w=wire_runtime_integration(decision());w["wiring_payload"]["runtime_handle"]="live";assert not validate_runtime_integration_wiring(_fp(w)).valid
