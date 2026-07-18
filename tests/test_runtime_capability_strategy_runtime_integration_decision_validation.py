from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_decision import decide_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import validate_runtime_integration_decision
from tests.test_runtime_capability_strategy_runtime_integration_decision import configuration

def _refingerprint(v): return _identified({k:x for k,x in v.items() if k not in {"decision_id","fingerprint"}},"decision_id","capability-strategy-runtime-integration-decision-")
def test_validator_accepts_chain_and_rejects_nested_or_linkage_tamper():
    source=configuration(); value=decide_runtime_integration(source);assert validate_runtime_integration_decision(value,source).valid
    for mutate in (lambda x:x["decision_payload"]["effective_bootstrap_options"].update(worker_limit=999),lambda x:x.update(source_configuration_id="other")):
        bad=deepcopy(value);mutate(bad);assert not validate_runtime_integration_decision(_refingerprint(bad),source).valid
def test_validator_rejects_unknown_missing_wrong_type_and_forbidden_values():
    value=decide_runtime_integration(configuration())
    variants=[]
    x=deepcopy(value);x["extra"]=1;variants.append(x)
    x=deepcopy(value);del x["status"];variants.append(x)
    x=deepcopy(value);x["boundary"]["runtime_activation"]=True;variants.append(_refingerprint(x))
    x=deepcopy(value);x["decision_payload"]["command"]="go | now";variants.append(_refingerprint(x))
    assert all(not validate_runtime_integration_decision(x).valid for x in variants)
