from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_consumption_validation import validate_bootstrap_consumption
from tests.capability_strategy_runtime_fixtures import strategy


def _artifacts():
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration))
    return wiring, consume_capability_strategy_bootstrap_wiring(wiring)


def _reidentify(value):
    return _identified({key: item for key, item in value.items() if key not in {"consumption_id", "fingerprint"}}, "consumption_id", "capability-strategy-bootstrap-consumption-")


def test_valid_consumption_and_tampering_are_detected():
    wiring, consumption = _artifacts()
    assert validate_bootstrap_consumption(consumption, wiring).valid
    fingerprint = deepcopy(consumption); fingerprint["fingerprint"] = "0" * 64
    nested = deepcopy(consumption); nested["consumer_payload"]["effective_bootstrap_options"]["worker_limit"] = 1
    nested = _reidentify(nested)
    assert not validate_bootstrap_consumption(fingerprint, wiring).valid
    assert "source_wiring_mismatch" in validate_bootstrap_consumption(nested, wiring).errors


def test_unknown_missing_contradiction_and_authority_fields_rejected():
    wiring, consumption = _artifacts()
    variants = []
    unknown = deepcopy(consumption); unknown["extra"] = True; variants.append(unknown)
    missing = deepcopy(consumption); del missing["source_wiring_id"]; variants.append(missing)
    contradiction = deepcopy(consumption); contradiction["status"] = "rejected"; variants.append(_reidentify(contradiction))
    for key in ("execution_authority", "mutation_authority", "approval_authority", "authorization_authority"):
        changed = deepcopy(consumption); changed[key] = False; variants.append(_reidentify(changed))
    assert all(not validate_bootstrap_consumption(item, wiring).valid for item in variants)


def test_linkage_and_scope_expansion_rejected_even_with_new_identity():
    wiring, consumption = _artifacts()
    linkage = deepcopy(consumption); linkage["source_strategy_id"] = "other"; linkage = _reidentify(linkage)
    expanded = deepcopy(consumption); expanded["consumer_payload"]["effective_bootstrap_options"]["worker_limit"] = 99; expanded = _reidentify(expanded)
    assert "source_wiring_mismatch" in validate_bootstrap_consumption(linkage, wiring).errors
    assert "source_wiring_mismatch" in validate_bootstrap_consumption(expanded, wiring).errors
